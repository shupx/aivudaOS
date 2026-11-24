from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from weakref import WeakValueDictionary

from aivudaos.core.apps.pipeline_config import PipelineStore
from aivudaos.core.apps.process_cleanup import process_stat, processes, remember, terminate
from aivudaos.core.apps.caddy_config import CaddyConfigService
from aivudaos.core.apps.config_validation import validate_config_data
from aivudaos.core.apps.magnet import MagnetService
from aivudaos.core.apps.models import AppManifest, AppRuntimeState
from aivudaos.core.apps.script_hooks import ScriptHookError, ScriptHookRunner
from aivudaos.core.apps.systemd_runtime import SystemdRuntimeBackend
from aivudaos.core.apps.versioning import VersioningService
from aivudaos.core.config.filelock import atomic_write_text
from aivudaos.core.config.ros_domain import effective_domain, has_ros2
from aivudaos.core.config.service import ConfigService
from aivudaos.core.db.connection import db_conn
from aivudaos.core.errors import (
    AppNotInstalledError,
    InvalidConfigError,
    AppRuntimeError,
    NotFoundError,
    OperationCanceledError,
)
from aivudaos.core.paths import APP_LOG_DIR, CONFIG_DIR
from aivudaos.core.paths import SHELL_HELPERS_DIR
from aivudaos.core.paths import SYSTEMD_RUNTIME_DIR
from aivudaos.core.paths import UI_DEFAULT_ICON_PATH
from aivudaos.core.paths import UI_FALLBACK_ICON_PATH


@lru_cache(maxsize=256)
def _cached_icon_digest(path: Path, inode: int, ctime_ns: int, size: int) -> str:
    # The stat fields invalidate the digest when an installer replaces the same path.
    digest = hashlib.sha256()
    with path.open("rb") as icon:
        for chunk in iter(lambda: icon.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _icon_revision(path: Path) -> Optional[str]:
    try:
        stat = path.stat()
        return _cached_icon_digest(path, stat.st_ino, stat.st_ctime_ns, stat.st_size)
    except OSError:
        # An overwrite can briefly remove the active file between polls.
        return None


@lru_cache(maxsize=1)
def _boot_id() -> str:
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    if not boot:
        raise AppRuntimeError("Cannot identify the current Linux boot")
    return boot


def _process_identity(pid: Optional[int]) -> Optional[str]:
    if not pid or pid <= 0:
        return None
    try:
        stat = process_stat(Path("/proc") / str(pid) / "stat")
    except (FileNotFoundError, ProcessLookupError):
        return None
    return "{}:{}".format(_boot_id(), stat[2]) if stat else None


class RuntimeService:
    """App lifecycle management — start / stop / autostart / version switch.

    Manifest is always read from the app_installation DB table.
    """

    def __init__(
        self,
        versioning: VersioningService,
        config_service: ConfigService,
        magnet_service: MagnetService,
    ) -> None:
        self._versioning = versioning
        self._config = config_service
        self._magnet = magnet_service
        self._systemd = SystemdRuntimeBackend(SHELL_HELPERS_DIR, SYSTEMD_RUNTIME_DIR)
        self._script_hooks = ScriptHookRunner()
        self._caddy = CaddyConfigService(versioning=versioning)
        self._owned_processes = {}
        self._process_lock = threading.RLock()
        self._autostart_lock = threading.RLock()
        self._pipeline_autostart = False
        self._app_locks = WeakValueDictionary()
        self._guardian = None
        self._closing = False
        self._snapshot_lock = threading.Lock()
        self._process_snapshot = (0, {})

    def _app_lock(self, app_id: str):
        # Serialize lifecycle operations for one app without blocking other apps' shutdown.
        with self._process_lock:
            lock = self._app_locks.get(app_id)
            if lock is None:
                lock = threading.RLock()
                self._app_locks[app_id] = lock
            return lock

    def _ensure_guardian(self) -> None:
        if self._guardian is not None:
            if self._guardian.poll() is not None:
                raise AppRuntimeError("Application guardian exited")
            return
        self._guardian = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("process_cleanup.py"))],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            start_new_session=True, close_fds=True,
        )

    def _guardian_message(self, action: str, pid: int, stamp: str) -> None:
        if self._guardian is None or self._guardian.stdin.closed:
            return
        self._guardian.stdin.write((json.dumps({"action": action, "pid": pid, "stamp": stamp}) + "\n").encode())
        self._guardian.stdin.flush()

    def shutdown(self) -> None:
        """Stop only Popen applications owned by this runtime; leave systemd alone."""
        from concurrent.futures import ThreadPoolExecutor
        with self._process_lock:
            self._closing = True
            app_ids = list(self._owned_processes)
        errors = []
        with ThreadPoolExecutor(max_workers=max(1, len(app_ids))) as pool:
            for future in [pool.submit(self.stop, app_id) for app_id in app_ids]:
                try:
                    future.result()
                except Exception as exc:
                    errors.append(str(exc))
        if self._guardian is not None:
            with self._process_lock:
                self._guardian.stdin.close()
            self._guardian.wait(timeout=10)
        if errors:
            raise AppRuntimeError("Application shutdown failed: " + "; ".join(errors))

    # ------------------------------------------------------------------ #
    #  Manifest from DB
    # ------------------------------------------------------------------ #

    def _get_manifest(self, app_id: str, version: Optional[str] = None) -> AppManifest:
        """Load the manifest for a specific (or active) version from DB."""
        if version is None:
            version = self._versioning.active_version(app_id)
        if version is None:
            raise AppNotInstalledError(f"{app_id} 未安装或无激活版本")

        with db_conn() as conn:
            row = conn.execute(
                "SELECT manifest FROM app_installation WHERE app_id = ? AND version = ?",
                (app_id, version),
            ).fetchone()

        if not row or not row["manifest"]:
            raise AppNotInstalledError(
                f"未找到 {app_id}@{version} 的 manifest 信息"
            )
        raw = json.loads(row["manifest"])
        return AppManifest.from_dict(app_id, raw)

    # ------------------------------------------------------------------ #
    #  Query helpers
    # ------------------------------------------------------------------ #

    def get_runtime_state(
        self, app_id: str, *, backend: Optional[Tuple[str, bool]] = None
    ) -> AppRuntimeState:
        with db_conn() as conn:
            row = conn.execute(
                "SELECT running, autostart, pid, process_identity, last_started_at, last_stopped_at "
                "FROM app_runtime WHERE app_id = ?",
                (app_id,),
            ).fetchone()
        return self._state_from_row(app_id, row, backend)

    def _state_from_row(self, app_id, row, backend, live_states=None):
        if not row or row["running"] is None:
            return AppRuntimeState(
                app_id=app_id,
                running=False,
                autostart=False,
                pid=None,
                last_started_at=None,
                last_stopped_at=None,
            )

        running = bool(row["running"])
        pid = row["pid"]
        identity = row["process_identity"]
        autostart = bool(row["autostart"])
        stopped_at = row["last_stopped_at"]

        if backend is None:
            scope = self._systemd_scope()
            using_systemd = self._should_use_systemd(scope)
        else:
            scope, using_systemd = backend
        if using_systemd:
            try:
                live = self._systemd.get_state(app_id, scope) if live_states is None else live_states.get(app_id)
                if live is None:
                    raise OSError("No live unit snapshot")
                running = live.running
                pid = live.pid
                identity = None  # Unit state is authoritative; this is not a Popen PID.
                if not self._pipeline_autostart:
                    autostart = live.enabled
                if (running, pid, autostart, identity) != (
                        bool(row["running"]), row["pid"], bool(row["autostart"]), row["process_identity"]):
                    if row["running"] and not running:
                        stopped_at = int(time.time())
                    self._sync_runtime_row(app_id, running=running, pid=pid, autostart=autostart,
                                           last_stopped_at=stopped_at)
            except (subprocess.SubprocessError, OSError):
                # A failed systemd query is not evidence that its unit has stopped.
                pass

        if not using_systemd and running and (not identity or identity != _process_identity(pid)):
            owned = self._owned_processes.get(app_id)
            table = processes() if owned is not None else {}
            descendants_alive = owned is not None and any(
                child in table and table[child][2] == stamp
                for child, stamp in list(owned[2].items())
            )
            if not descendants_alive:
                stopped_at = int(time.time())
                self._mark_stopped_if_pid_matches(app_id, pid, identity, stopped_at)
                running = False
                pid = None
                identity = None

        return AppRuntimeState(
            app_id=app_id,
            running=running,
            autostart=autostart,
            pid=pid,
            last_started_at=row["last_started_at"],
            last_stopped_at=stopped_at,
            process_identity=identity,
        )

    def get_detail(self, app_id: str) -> Dict[str, Any]:
        """Full detail: installation info + runtime state + active version."""
        with db_conn() as conn:
            install_rows = conn.execute(
                "SELECT app_id, version, install_path, status, installed_at "
                "FROM app_installation WHERE app_id = ? ORDER BY installed_at DESC",
                (app_id,),
            ).fetchall()
        if not install_rows:
            raise AppNotInstalledError(f"{app_id} is not installed")

        active_ver = self._versioning.active_version(app_id)
        cfg = self._config.get_app_config(app_id, active_ver) if active_ver else None

        # Include manifest for the active version
        manifest: Optional[AppManifest] = None
        manifest_info: Optional[Dict[str, Any]] = None
        try:
            manifest = self._get_manifest(app_id, active_ver)
            manifest_info = manifest.to_dict()
        except Exception:
            pass

        runtime_state = self.get_runtime_state(app_id)
        install_path = self._versioning.active_install_path(app_id)
        built_in_ui_entry = self._resolve_app_ui_entry_path(install_path, manifest)
        panelhub_mountable = bool(
            manifest and manifest.is_panelhub_mountable(built_in_ui_entry is not None)
        )

        return {
            "app_id": app_id,
            "installed": True,
            "active_version": active_ver,
            "versions": [dict(r) for r in install_rows],
            "runtime": {
                "app_id": runtime_state.app_id,
                "running": int(runtime_state.running),
                "autostart": int(runtime_state.autostart),
                "pid": runtime_state.pid,
                "last_started_at": runtime_state.last_started_at,
                "last_stopped_at": runtime_state.last_stopped_at,
            },
            "config": {
                "version": cfg.version if cfg else 0,
                "updated_at": cfg.updated_at if cfg else None,
                "app_version": active_ver,
            },
            "manifest": manifest_info,
            "has_builtin_ui": built_in_ui_entry is not None,
            "panelhub_mountable": panelhub_mountable,
        }

    def get_installed_list(self) -> List[Dict[str, Any]]:
        """List all installed apps with runtime state and active version."""
        with db_conn() as conn:
            rows = conn.execute(
                """
                SELECT i.app_id, i.version, i.install_path, i.status, i.installed_at,
                       r.running, r.autostart, r.pid, r.process_identity,
                       r.last_started_at, r.last_stopped_at
                FROM app_installation i
                LEFT JOIN app_runtime r ON r.app_id = i.app_id
                ORDER BY i.installed_at DESC
                """
            ).fetchall()

        # Group by app_id, return one entry per app with version list
        scope = self._systemd_scope()
        backend = (scope, self._should_use_systemd(scope))
        live_states = None
        if backend[1]:
            try:
                live_states = self._systemd.get_states({r["app_id"] for r in rows}, scope)
            except (subprocess.SubprocessError, OSError):
                live_states = {}
        seen: Dict[str, dict] = {}
        for row in rows:
            aid = row["app_id"]
            if aid not in seen:
                active_ver = self._versioning.active_version(aid)
                # Attempt to read manifest name
                name = aid
                manifest: Optional[AppManifest] = None
                try:
                    manifest = self._get_manifest(aid, active_ver)
                    name = manifest.name
                except Exception:
                    pass
                runtime_state = self._state_from_row(aid, row, backend, live_states)
                install_path = self._versioning.active_install_path(aid)
                built_in_ui_entry = self._resolve_app_ui_entry_path(install_path, manifest)
                panelhub_mountable = bool(
                    manifest and manifest.is_panelhub_mountable(built_in_ui_entry is not None)
                )
                seen[aid] = {
                    "app_id": aid,
                    "name": name,
                    "active_version": active_ver,
                    "versions": [],
                    "install_path": str(self._versioning.active_link(aid)),
                    "status": row["status"],
                    "installed_at": row["installed_at"],
                    "icon_revision": _icon_revision(self._resolve_app_icon(install_path, manifest)),
                    "running": runtime_state.running,
                    "autostart": runtime_state.autostart,
                    "pid": runtime_state.pid,
                    "last_started_at": runtime_state.last_started_at,
                    "last_stopped_at": runtime_state.last_stopped_at,
                    "has_builtin_ui": built_in_ui_entry is not None,
                    "panelhub_mountable": panelhub_mountable,
                }
            seen[aid]["versions"].append(row["version"])

        return list(seen.values())

    # ------------------------------------------------------------------ #
    #  Lifecycle: start / stop / restart
    # ------------------------------------------------------------------ #

    def start(self, app_id: str) -> Dict[str, Any]:
        with self._app_lock(app_id):
            return self._start(app_id)

    def _start(self, app_id: str) -> Dict[str, Any]:
        scope = self._systemd_scope()
        using_systemd = self._should_use_systemd(scope)
        runtime_state = self.get_runtime_state(app_id, backend=(scope, using_systemd))
        if not using_systemd:
            owned = self._owned_processes.get(app_id)
            if runtime_state.running or (owned is not None and owned[0].poll() is None):
                return {"ok": True, "app_id": app_id, "running": True}
            if owned is not None:
                # The root exited before its watcher finished. Retire its guardian entry.
                self.stop(app_id)

        active_version = self._versioning.active_version(app_id)
        if active_version is None:
            raise AppNotInstalledError(f"{app_id} has no active version")

        manifest = self._get_manifest(app_id, active_version)
        now = int(time.time())

        install_path = self._versioning.active_install_path(app_id)
        if install_path is None:
            raise AppNotInstalledError(f"{app_id} has no active version")

        command = self._build_exec_command(manifest, install_path)
        command = self._decorate_command_for_realtime_logs(command)
        config_env = self._build_config_env(
            app_id,
            active_version,
            manifest,
            install_path=install_path,
        )
        runtime_env = {**self._build_runtime_env(), **config_env}
        log_path = self._app_log_path(app_id)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        if using_systemd:
            try:
                self._write_systemd_unit(
                    app_id=app_id,
                    scope=scope,
                    manifest=manifest,
                    install_path=install_path,
                    command=command,
                    runtime_env=runtime_env,
                    log_path=log_path,
                )
                self._systemd.reload_changed_units(scope)
                self._systemd.start(app_id, scope)
                live = self._systemd.get_state(app_id, scope)
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                raise AppRuntimeError(f"启动 {app_id} 失败（systemd）: {exc}") from exc

            self._sync_runtime_row(
                app_id,
                running=live.running,
                pid=live.pid,
                autostart=live.enabled or runtime_state.autostart,
                last_started_at=now,
            )
            return {"ok": True, "app_id": app_id, "running": live.running}

        with self._process_lock:
            if self._closing:
                raise AppRuntimeError("Runtime is shutting down")
            self._ensure_guardian()
            try:
                log_path.with_suffix(".exit").unlink(missing_ok=True)
                with log_path.open("wb") as log_file:
                    proc = subprocess.Popen(
                        command,
                        cwd=str(install_path),
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        env={**os.environ, **runtime_env},
                        start_new_session=True,
                    )
            except OSError as exc:
                raise AppRuntimeError(f"启动 {app_id} 失败，无法写入日志: {exc}") from exc

            try:
                identity = _process_identity(proc.pid)
                if identity is None:
                    if proc.poll() is None:
                        raise AppRuntimeError("Cannot identify the launched application process")
                    self._record_exit(app_id, proc.returncode)
                    self._sync_runtime_row(
                        app_id, running=False, pid=None, autostart=runtime_state.autostart,
                        last_started_at=now, last_stopped_at=int(time.time()),
                    )
                    return {"ok": True, "app_id": app_id, "running": False}
            except (OSError, ValueError, AppRuntimeError) as exc:
                proc.kill()
                proc.wait(timeout=2)
                raise AppRuntimeError("Cannot identify the launched application process") from exc

            stamp = identity.split(":", 1)[1]
            owned = (proc, stamp, {proc.pid: stamp})
            self._owned_processes[app_id] = owned
            try:
                self._guardian_message("add", proc.pid, stamp)
                self._sync_runtime_row(
                    app_id, running=True, pid=proc.pid, process_identity=identity,
                    autostart=runtime_state.autostart, last_started_at=now,
                )
            except Exception as exc:
                terminate(owned[2], proc.pid, stamp)
                proc.wait(timeout=2)
                self._owned_processes.pop(app_id, None)
                try:
                    self._guardian_message("remove", proc.pid, stamp)
                except (OSError, ValueError):
                    pass
                raise AppRuntimeError("Application process registration failed") from exc

            watcher = threading.Thread(
                target=self._watch_process_exit,
                args=(app_id, owned, identity),
                daemon=True,
            )
            watcher.start()

        return {"ok": True, "app_id": app_id, "running": True}

    def stop(self, app_id: str) -> Dict[str, Any]:
        with self._app_lock(app_id):
            return self._stop(app_id)

    def _stop(self, app_id: str) -> Dict[str, Any]:
        now = int(time.time())
        runtime_state = self.get_runtime_state(app_id)

        if not self._versioning.list_versions(app_id):
            raise AppNotInstalledError(f"{app_id} is not installed")

        scope = self._systemd_scope()
        if self._should_use_systemd(scope):
            try:
                self._systemd.stop(app_id, scope)
            except subprocess.CalledProcessError as exc:
                if "not loaded" not in (exc.stderr or "") and "not found" not in (
                    exc.stderr or ""
                ):
                    pass
            except OSError:
                pass

        if runtime_state.pid or app_id in self._owned_processes:
            try:
                owned = self._owned_processes.get(app_id)
                if owned is not None:
                    proc, stamp, tree = owned
                    terminate(tree, proc.pid, stamp)
                    proc.wait(timeout=2)
                    with self._process_lock:
                        if self._owned_processes.get(app_id) is owned:
                            self._guardian_message("remove", proc.pid, stamp)
                            self._owned_processes.pop(app_id, None)
                elif runtime_state.process_identity and runtime_state.process_identity == _process_identity(runtime_state.pid):
                    # Pass the launch-time stamp, not a new stamp taken from a possibly reused PID.
                    stamp = runtime_state.process_identity.split(":", 1)[1]
                    terminate({runtime_state.pid: stamp}, runtime_state.pid, stamp)
            except ProcessLookupError:
                pass
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                raise AppRuntimeError("Application cleanup failed: " + str(exc)) from exc

        self._app_log_path(app_id).with_suffix(".exit").unlink(missing_ok=True)
        self._sync_runtime_row(
            app_id,
            running=False,
            pid=None,
            autostart=runtime_state.autostart,
            last_stopped_at=now,
        )

        return {"ok": True, "app_id": app_id, "running": False}

    def restart(self, app_id: str) -> Dict[str, Any]:
        """Stop then start an app."""
        with self._app_lock(app_id):
            return self._restart(app_id)

    def _restart(self, app_id: str) -> Dict[str, Any]:
        scope = self._systemd_scope()
        if self._should_use_systemd(scope):
            if not self._versioning.list_versions(app_id):
                raise AppNotInstalledError(f"{app_id} is not installed")
            now = int(time.time())
            try:
                active_version = self._versioning.active_version(app_id)
                if active_version is None:
                    raise AppNotInstalledError(f"{app_id} has no active version")
                manifest = self._get_manifest(app_id, active_version)
                install_path = self._versioning.active_install_path(app_id)
                if install_path is None:
                    raise AppNotInstalledError(f"{app_id} has no active version")
                command = self._build_exec_command(manifest, install_path)
                command = self._decorate_command_for_realtime_logs(command)
                runtime_env = {
                    **self._build_runtime_env(),
                    **self._build_config_env(
                        app_id,
                        active_version,
                        manifest,
                        install_path=install_path,
                    ),
                }
                log_path = self._app_log_path(app_id)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                self._write_systemd_unit(
                    app_id=app_id,
                    scope=scope,
                    manifest=manifest,
                    install_path=install_path,
                    command=command,
                    runtime_env=runtime_env,
                    log_path=log_path,
                )
                self._systemd.reload_changed_units(scope)
                self._systemd.restart(app_id, scope)
                live = self._systemd.get_state(app_id, scope)
            except (subprocess.SubprocessError, OSError):
                runtime_state = self.get_runtime_state(app_id)
                if runtime_state.running:
                    self.stop(app_id)
                return self.start(app_id)

            self._sync_runtime_row(
                app_id,
                running=live.running,
                pid=live.pid,
                autostart=live.enabled,
                last_started_at=now,
                last_stopped_at=None,
            )
            return {"ok": True, "app_id": app_id, "running": live.running}

        runtime_state = self.get_runtime_state(app_id)
        if runtime_state.running:
            self.stop(app_id)
        return self.start(app_id)

    # ------------------------------------------------------------------ #
    #  Autostart
    # ------------------------------------------------------------------ #

    def configure_pipeline_autostart(self, takeover: bool) -> None:
        """Reconcile boot ownership without starting/stopping apps or losing preferences."""
        with self._autostart_lock:
            self._pipeline_autostart = takeover
            scope = self._systemd_scope()
            if not self._should_use_systemd(scope):
                if self._runtime_mode() == 'systemd':
                    raise AppRuntimeError('Cannot reconcile boot ownership: systemd is unavailable')
                return
            if not takeover:
                if self._reconcile_systemd_units(scope):
                    raise AppRuntimeError('Could not restore individual systemd autostart settings')
                return
            # Disable already-installed units at SAVE time, before the next boot.
            # An app which has never had a unit cannot be enabled independently.
            try:
                for app_id in self.list_installed_app_ids():
                    if self._systemd.unit_file_path(app_id, scope).exists():
                        self._systemd.set_enabled(app_id, scope, False, defer_reload=True)
                self._systemd.daemon_reload(scope)
            except (OSError, subprocess.SubprocessError) as exc:
                raise AppRuntimeError('Could not disable individual systemd autostart units') from exc

    def set_autostart(self, app_id: str, enabled: bool) -> Dict[str, Any]:
        with self._autostart_lock:
            return self._set_autostart(app_id, enabled)

    def _set_autostart(self, app_id: str, enabled: bool) -> Dict[str, Any]:
        install_path = self._versioning.active_install_path(app_id)
        if install_path is None:
            raise AppNotInstalledError(f"{app_id} is not installed")

        scope = self._systemd_scope()
        if not self._pipeline_autostart and self._should_use_systemd(scope):
            manifest = self._get_manifest(app_id)
            command = self._build_exec_command(manifest, install_path)
            command = self._decorate_command_for_realtime_logs(command)
            active_version = self._versioning.active_version(app_id)
            if active_version is None:
                raise AppNotInstalledError(f"{app_id} has no active version")
            runtime_env = {
                **self._build_runtime_env(),
                **self._build_config_env(
                    app_id,
                    active_version,
                    manifest,
                    install_path=install_path,
                ),
            }
            log_path = self._app_log_path(app_id)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._write_systemd_unit(
                    app_id=app_id,
                    scope=scope,
                    manifest=manifest,
                    install_path=install_path,
                    command=command,
                    runtime_env=runtime_env,
                    log_path=log_path,
                )
                self._systemd.reload_changed_units(scope)
                self._systemd.set_enabled(app_id, scope, enabled)
            except (subprocess.SubprocessError, OSError, ValueError):
                pass

        with db_conn() as conn:
            conn.execute(
                "UPDATE app_runtime SET autostart=? WHERE app_id=?",
                (1 if enabled else 0, app_id),
            )
            conn.commit()

        return {"ok": True, "app_id": app_id, "autostart": enabled}

    # ------------------------------------------------------------------ #
    #  Version management
    # ------------------------------------------------------------------ #

    def switch_version(
        self, app_id: str, version: str, restart: bool = False
    ) -> Dict[str, Any]:
        """Switch active version. Optionally stop old and start new."""
        current_active = self._versioning.active_version(app_id)
        runtime_state = self.get_runtime_state(app_id)

        try:
            manifest = self._get_manifest(app_id, version)
        except AppNotInstalledError as exc:
            raise NotFoundError(str(exc)) from exc

        try:
            self._caddy.validate_candidate(
                app_id,
                manifest,
                self._versioning.version_dir(app_id, version),
            )
        except InvalidConfigError as exc:
            raise AppRuntimeError(f"switch_version validation failed: {exc}") from exc

        source_data = {}
        if current_active:
            source_config = self._config.get_app_config(app_id, current_active)
            source_data = source_config.data if source_config.version > 0 else self._config.get_app_default_config(
                app_id, current_active, fallback=self._get_manifest(app_id, current_active).default_config,
            )
        migration = self._config.migrate_app_config(
            app_id, version, source_data,
            self._config.get_app_default_config(app_id, version, fallback=manifest.default_config),
            manifest.config_schema,
        )

        if runtime_state.running and restart:
            self.stop(app_id)

        self._versioning.activate_version(app_id, version)
        if migration["config_valid"]:
            self._magnet.recompute(updated_by="system")
        try:
            self._caddy.sync_and_reload()
        except InvalidConfigError as exc:
            if current_active and current_active != version:
                self._versioning.activate_version(app_id, current_active)
                self._magnet.recompute(updated_by="system")
                try:
                    self._caddy.sync_and_reload()
                except InvalidConfigError:
                    pass
            raise AppRuntimeError(f"switch_version failed while reloading caddy: {exc}") from exc

        if runtime_state.running and restart and migration["config_valid"]:
            self.start(app_id)

        return {
            "ok": True,
            "app_id": app_id,
            "previous_version": current_active,
            "active_version": version,
            **migration,
        }

    def update_this_version(
        self,
        app_id: str,
        version: str,
        event_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        interactive: bool = False,
        read_input: Optional[Callable[[float], Optional[str]]] = None,
        cancel_requested: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        def emit(event_type: str, **payload: Any) -> None:
            if event_cb:
                event_cb(event_type, payload)

        versions = self._versioning.list_versions(app_id)
        if not versions:
            raise AppNotInstalledError(f"{app_id} is not installed")
        if version not in versions:
            raise NotFoundError(
                f"Version {version} is not installed for {app_id}"
            )

        emit(
            "status",
            phase="prepare",
            status="running",
            message="准备执行 update_this_version",
            app_id=app_id,
            version=version,
        )
        manifest = self._get_manifest(app_id, version)
        install_path = self._versioning.version_dir(app_id, version)
        executed = self._run_manifest_hook(
            app_id=app_id,
            manifest=manifest,
            hook_name="update_this_version",
            root_dir=install_path,
            event_cb=event_cb,
            interactive=interactive,
            read_input=read_input,
            cancel_requested=cancel_requested,
        )

        emit(
            "status",
            phase="completed",
            status="completed",
            message="update_this_version 执行完成",
            app_id=app_id,
            version=version,
            executed=executed,
        )

        self._magnet.recompute(updated_by="system")

        return {
            "ok": True,
            "app_id": app_id,
            "version": version,
            "executed": executed,
            "skipped": not executed,
        }

    # ------------------------------------------------------------------ #
    #  Uninstall
    # ------------------------------------------------------------------ #

    def uninstall(
        self,
        app_id: str,
        version: Optional[str] = None,
        purge: bool = False,
        event_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        interactive: bool = False,
        read_input: Optional[Callable[[float], Optional[str]]] = None,
        cancel_requested: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Uninstall a specific version or the entire app."""
        def emit(event_type: str, **payload: Any) -> None:
            if event_cb:
                event_cb(event_type, payload)

        def _parse_confirmation(value: Optional[str]) -> Optional[bool]:
            raw = str(value or "").strip().lower()
            if raw in {"y", "yes", "1", "true", "continue", "ok", "继续", "是"}:
                return True
            if raw in {"n", "no", "0", "false", "cancel", "停止", "否"}:
                return False
            return None

        def run_pre_uninstall_hook(manifest: AppManifest, target_version: str) -> None:
            try:
                self._run_manifest_hook(
                    app_id=app_id,
                    manifest=manifest,
                    hook_name="pre_uninstall",
                    root_dir=self._versioning.version_dir(app_id, target_version),
                    event_cb=event_cb,
                    interactive=interactive,
                    read_input=read_input,
                    cancel_requested=cancel_requested,
                )
            except AppRuntimeError as exc:
                error_message = str(exc)
                emit(
                    "status",
                    phase="pre_uninstall",
                    status="warning",
                    message="pre_uninstall 执行失败，继续卸载",
                    app_id=app_id,
                    version=target_version,
                    error=error_message,
                )

                if not interactive or read_input is None:
                    return

                emit(
                    "status",
                    phase="pre_uninstall",
                    status="awaiting_confirmation",
                    message="pre_uninstall 失败，请确认是否继续卸载",
                    app_id=app_id,
                    version=target_version,
                    error=error_message,
                    confirm_input_hint="输入 y 继续，输入 n 取消",
                )

                while True:
                    if cancel_requested and cancel_requested():
                        raise OperationCanceledError("Operation canceled by user")

                    user_input = read_input(1.0)
                    decision = _parse_confirmation(user_input)
                    if decision is True:
                        emit(
                            "status",
                            phase="pre_uninstall",
                            status="warning",
                            message="已确认继续卸载",
                            app_id=app_id,
                            version=target_version,
                        )
                        return

                    if decision is False:
                        raise OperationCanceledError(
                            "Uninstall canceled by user after pre_uninstall failure"
                        )

                    if user_input is None:
                        continue

                    emit(
                        "status",
                        phase="pre_uninstall",
                        status="awaiting_confirmation",
                        message="无效输入，请输入 y 继续，输入 n 取消",
                        app_id=app_id,
                        version=target_version,
                    )

        runtime_state = self.get_runtime_state(app_id)
        emit("status", phase="prepare", status="running", message="准备卸载", app_id=app_id)

        if version is None:
            # Uninstall ALL versions
            if runtime_state.running:
                self.stop(app_id)

            all_versions = self._versioning.list_versions(app_id)
            hook_version = self._versioning.active_version(app_id)
            if hook_version is None and all_versions:
                hook_version = all_versions[0]
            if hook_version is not None:
                manifest = self._get_manifest(app_id, hook_version)
                run_pre_uninstall_hook(manifest, hook_version)

            emit("status", phase="remove", status="running", message="删除应用目录", app_id=app_id)
            self._versioning.remove_app_entirely(app_id)
            with db_conn() as conn:
                conn.execute(
                    "DELETE FROM app_runtime WHERE app_id = ?", (app_id,)
                )
                conn.commit()
            if purge:
                self._config.delete_app_config(app_id)
        else:
            # Uninstall specific version
            manifest = self._get_manifest(app_id, version)
            run_pre_uninstall_hook(manifest, version)

            active = self._versioning.active_version(app_id)
            if active == version and runtime_state.running:
                self.stop(app_id)
            emit(
                "status",
                phase="remove",
                status="running",
                message="删除版本",
                app_id=app_id,
                version=version,
            )
            self._versioning.remove_version(app_id, version)
            self._config.delete_app_config(app_id, version)
            # If we removed the active version, try to activate another
            remaining = self._versioning.list_versions(app_id)
            if active == version and remaining:
                self._versioning.activate_version(app_id, remaining[0])
            elif not remaining:
                with db_conn() as conn:
                    conn.execute(
                        "DELETE FROM app_runtime WHERE app_id = ?", (app_id,)
                    )
                    conn.commit()
                if purge:
                    self._config.delete_app_config(app_id)

        if version is None or not remaining:
            PipelineStore(CONFIG_DIR / "startup_pipeline.yaml").detach_app(app_id)

        scope = self._systemd_scope()
        if self._should_use_systemd(scope):
            try:
                self._systemd.set_enabled(app_id, scope, False)
            except subprocess.SubprocessError:
                pass
            except OSError:
                pass
            try:
                self._systemd.remove_unit(app_id, scope)
            except OSError:
                pass

        emit("status", phase="completed", status="completed", message="卸载完成", app_id=app_id)
        self._magnet.recompute(updated_by="system")
        try:
            self._caddy.sync_and_reload()
        except InvalidConfigError as exc:
            raise AppRuntimeError(f"uninstall failed while reloading caddy: {exc}") from exc

        return {"ok": True, "app_id": app_id, "version": version, "purge": purge}

    def start_autostart_apps(self) -> Dict[str, Any]:
        # only for popen mode, systemd will manage autostart itself and we skip replay to avoid conflicts
        scope = self._systemd_scope()
        if self._should_use_systemd(scope):
            self._reconcile_systemd_units(scope)
            return {
                "started": [],
                "skipped": [],
                "failed": [],
                "mode": "systemd",
            }

        with db_conn() as conn:
            rows = conn.execute(
                "SELECT app_id FROM app_runtime WHERE autostart = 1 ORDER BY app_id"
            ).fetchall()

        started: List[str] = []
        skipped: List[str] = []
        failed: List[Dict[str, str]] = []

        for row in rows:
            app_id = row["app_id"]
            state = self.get_runtime_state(app_id)
            if state.running:
                skipped.append(app_id)
                continue
            try:
                self.start(app_id)
                started.append(app_id)
            except Exception as exc:
                failed.append({"app_id": app_id, "error": str(exc)})

        return {
            "started": started,
            "skipped": skipped,
            "failed": failed,
            "mode": "popen",
        }

    def restart_autostart_apps(self) -> Dict[str, Any]:
        app_ids = self._list_autostart_app_ids()
        restarted: List[str] = []
        failed: List[Dict[str, str]] = []

        for app_id in app_ids:
            try:
                self.restart(app_id)
                restarted.append(app_id)
            except Exception as exc:
                failed.append({"app_id": app_id, "error": str(exc)})

        return {
            "ok": len(failed) == 0,
            "message": "Autostart apps restart completed.",
            "requested_count": len(app_ids),
            "restarted": restarted,
            "skipped": [],
            "failed": failed,
        }

    def start_autostart_apps_if_needed(self) -> Dict[str, Any]:
        app_ids = self._list_autostart_app_ids()
        started: List[str] = []
        skipped: List[str] = []
        failed: List[Dict[str, str]] = []

        for app_id in app_ids:
            try:
                state = self.get_runtime_state(app_id)
                if state.running:
                    skipped.append(app_id)
                    continue
                self.start(app_id)
                started.append(app_id)
            except Exception as exc:
                failed.append({"app_id": app_id, "error": str(exc)})

        return {
            "ok": len(failed) == 0,
            "message": "Autostart apps start completed.",
            "requested_count": len(app_ids),
            "started": started,
            "skipped": skipped,
            "failed": failed,
        }

    def stop_all_apps(self) -> Dict[str, Any]:
        app_ids = self.list_installed_app_ids()
        stopped: List[str] = []
        skipped: List[str] = []
        failed: List[Dict[str, str]] = []

        for app_id in app_ids:
            try:
                state = self.get_runtime_state(app_id)
                if not state.running:
                    skipped.append(app_id)
                    continue
                self.stop(app_id)
                stopped.append(app_id)
            except Exception as exc:
                failed.append({"app_id": app_id, "error": str(exc)})

        return {
            "ok": len(failed) == 0,
            "message": "All apps stop completed.",
            "requested_count": len(app_ids),
            "stopped": stopped,
            "skipped": skipped,
            "failed": failed,
        }

    def _list_autostart_app_ids(self) -> List[str]:
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT app_id FROM app_runtime WHERE autostart = 1 ORDER BY app_id"
            ).fetchall()
        return [str(row["app_id"]) for row in rows]

    def list_installed_app_ids(self) -> List[str]:
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT app_id FROM app_installation ORDER BY app_id"
            ).fetchall()
        return [str(row["app_id"]) for row in rows]

    def _reconcile_systemd_units(self, scope: str) -> List[str]:
        """Refresh systemd unit files for installed apps to keep runtime wrappers/env in sync."""
        errors: List[str] = []
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT app_id, autostart FROM app_runtime ORDER BY app_id"
            ).fetchall()

        common_env = None
        for row in rows:
            app_id = str(row["app_id"])
            enabled = bool(row["autostart"]) and not self._pipeline_autostart
            try:
                install_path = self._versioning.active_install_path(app_id)
                if install_path is None:
                    continue
                manifest = self._get_manifest(app_id)
                command = self._build_exec_command(manifest, install_path)
                command = self._decorate_command_for_realtime_logs(command)
                active_version = self._versioning.active_version(app_id)
                if active_version is None:
                    continue
                if common_env is None:
                    common_env = self._build_runtime_env()
                runtime_env = {
                    **common_env,
                    **self._build_config_env(
                        app_id,
                        active_version,
                        manifest,
                        install_path=install_path,
                    ),
                }
                log_path = self._app_log_path(app_id)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                self._write_systemd_unit(
                    app_id=app_id,
                    scope=scope,
                    manifest=manifest,
                    install_path=install_path,
                    command=command,
                    runtime_env=runtime_env,
                    log_path=log_path,
                )
                self._systemd.set_enabled(app_id, scope, enabled, defer_reload=True)
            except Exception as exc:
                # Reconciliation is best-effort: one broken app must not block other units.
                errors.append("{}: {}".format(app_id, exc))
                continue

        try:
            self._systemd.daemon_reload(scope)
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append("daemon-reload: {}".format(exc))
        return errors

    def _write_systemd_unit(
        self,
        app_id: str,
        scope: str,
        manifest: AppManifest,
        install_path: Path,
        command: List[str],
        runtime_env: Dict[str, str],
        log_path: Path,
    ) -> None:
        self._systemd.write_unit(
            app_id=app_id,
            scope=scope,
            command=command,
            working_dir=install_path,
            log_path=log_path,
            description=f"AivudaOS app {manifest.name} ({app_id})",
            environment=runtime_env,
        )

    def _runtime_mode(self) -> str:
        raw = str(self._config.get_os_setting("runtime_process_manager", "auto"))
        mode = raw.strip().lower()
        if mode not in {"auto", "systemd", "popen"}:
            return "auto"
        return mode

    def _systemd_scope(self) -> str:
        raw = str(self._config.get_os_setting("runtime_systemd_scope", "user"))
        scope = raw.strip().lower()
        if scope not in {"user", "system"}:
            return "user"
        return scope

    def _should_use_systemd(self, scope: Optional[str] = None) -> bool:
        mode = self._runtime_mode()
        selected_scope = scope or self._systemd_scope()

        if mode == "popen":
            return False

        available = self._systemd.is_available(selected_scope)
        if mode == "systemd":
            return available
        return available

    # ------------------------------------------------------------------ #
    #  Process helpers
    # ------------------------------------------------------------------ #

    def _build_exec_command(
        self, manifest: AppManifest, install_path: Path
    ) -> List[str]:
        entrypoint = manifest.run.get("entrypoint")
        if not entrypoint:
            raise AppRuntimeError("app run.entrypoint 未配置")
        entry = Path(entrypoint)
        resolved = (
            (install_path / entry).resolve() if not entry.is_absolute() else entry
        )
        args = manifest.run.get("args", [])
        return [str(resolved), *[str(x) for x in args]]

    def _build_config_env(
        self,
        app_id: str,
        app_version: str,
        manifest: AppManifest,
        *,
        install_path: Optional[Path] = None,
    ) -> Dict[str, str]:
        self._ensure_version_config_ready(app_id, app_version, manifest)

        config_path = self._config.app_config_path(app_id, app_version)
        install_path = install_path or self._versioning.version_dir(app_id, app_version)
        runtime_data_path = self._versioning.ensure_version_runtime_data_dir(
            app_id,
            app_version,
        )
        helpers_entry_path = (SHELL_HELPERS_DIR / "aivuda_app_helpers.sh").resolve()
        return {
            "AIVUDA_APP_ID": app_id,
            "AIVUDA_APP_VERSION": app_version,
            "AIVUDA_APP_INSTALL_PATH": str(install_path.resolve()),
            "AIVUDA_APP_RUNTIME_DATA_PATH": str(runtime_data_path.resolve()),
            "AIVUDA_APP_CONFIG_PATH": str(config_path.resolve()),
            "AIVUDA_APP_HELPERS_ENTRY_PATH": str(helpers_entry_path),
        }

    def _ensure_version_config_ready(
        self,
        app_id: str,
        app_version: str,
        manifest: AppManifest,
    ) -> None:
        cfg = self._config.get_app_config(app_id, app_version)
        saved = cfg.data if cfg.version > 0 else None
        data = saved if saved is not None else manifest.default_config
        try:
            validate_config_data(
                data,
                manifest.config_schema,
                previous_data=saved,
                context=f"switch config {app_id}@{app_version}",
            )
        except InvalidConfigError as exc:
            raise AppRuntimeError(str(exc)) from exc
        if cfg.version == 0:
            self._config.init_app_config(app_id, app_version, manifest.default_config)

    def _build_runtime_env(self) -> Dict[str, str]:
        from aivudaos.core.config.runtime_environment import DEFAULT_RUNTIME_ENVIRONMENT, validate_runtime_environment

        settings = self._config.get_os_config().data
        overrides = settings.get("runtime_environment", DEFAULT_RUNTIME_ENVIRONMENT)
        if has_ros2() and isinstance(overrides, dict):
            domain = effective_domain(self._config.get_sys_config().data, overrides)
            overrides = {**overrides, "ROS_DOMAIN_ID": str(domain)}
        return {
            "PYTHONUNBUFFERED": "1",
            "ROSCONSOLE_STDOUT_LINE_BUFFERED": "1",
            "TERM": "xterm-256color",
            "CLICOLOR_FORCE": "1",
            "FORCE_COLOR": "1",
            "PY_COLORS": "1",
            **validate_runtime_environment(overrides),
            "AIVUDA_OS_AVAHI_HOSTNAME": str(settings.get("avahi_hostname") or "").strip().lower(),
        }

    def readiness_state_reader(self, app_id):
        """Pin the selected backend for one probe and read systemd liveness directly."""
        scope = self._systemd_scope()
        if self._should_use_systemd(scope):
            return lambda app: self._systemd.get_state(app, scope)
        return lambda app: self.get_runtime_state(app, backend=(scope, False))

    def readiness_context(self, app_id: str) -> Tuple[dict, dict, dict, dict]:
        """Launch environment and active config inputs for a readiness command."""
        version = self._versioning.active_version(app_id)
        if not version:
            raise AppNotInstalledError(f"{app_id} has no active version")
        manifest = self._get_manifest(app_id, version)
        env = {**os.environ, **self._build_runtime_env(),
               **self._build_config_env(app_id, version, manifest)}
        if not has_ros2():  # A command or an app-specific PATH may still use ROS.
            env["ROS_DOMAIN_ID"] = str(effective_domain(self._config.get_sys_config().data, env))
        config = self._config.get_app_config(app_id, version)
        return env, config.data, manifest.default_config, manifest.config_schema

    def refresh_runtime_environment(self) -> List[str]:
        """Refresh persisted units; running processes receive changes on restart."""
        with self._autostart_lock:
            scope = self._systemd_scope()
            if self._should_use_systemd(scope):
                return self._reconcile_systemd_units(scope)
            return []

    @staticmethod
    def _decorate_command_for_realtime_logs(command: List[str]) -> List[str]:
        if not command:
            return command

        decorated = list(command)
        executable = os.path.basename(decorated[0])
        if executable == "roslaunch" and "--screen" not in decorated:
            decorated = [decorated[0], "--screen", *decorated[1:]]

        stdbuf = shutil.which("stdbuf")
        if not stdbuf:
            return decorated
        return [stdbuf, "-oL", "-eL", *decorated]

    def _app_log_path(self, app_id: str) -> Path:
        return APP_LOG_DIR / app_id / "current.log"

    def get_app_icon_path(self, app_id: str) -> Path:
        install_path = self._versioning.active_install_path(app_id)
        try:
            manifest = self._get_manifest(app_id) if install_path is not None else None
        except AppNotInstalledError:
            manifest = None
        return self._resolve_app_icon(install_path, manifest)

    def _resolve_app_icon(
        self, install_path: Optional[Path], manifest: Optional[AppManifest],
    ) -> Path:
        if install_path is not None and manifest and manifest.icon:
            icon_path = self._resolve_manifest_relative_file(install_path, manifest.icon)
            if icon_path is not None:
                return icon_path

        if UI_DEFAULT_ICON_PATH.exists() and UI_DEFAULT_ICON_PATH.is_file():
            return UI_DEFAULT_ICON_PATH
        return UI_FALLBACK_ICON_PATH

    def get_app_ui_entry_path(self, app_id: str) -> Optional[Path]:
        install_path = self._versioning.active_install_path(app_id)
        if install_path is None:
            return None

        try:
            manifest = self._get_manifest(app_id)
        except AppNotInstalledError:
            return None

        return self._resolve_app_ui_entry_path(install_path, manifest)

    def _resolve_app_ui_entry_path(
        self,
        install_path: Optional[Path],
        manifest: Optional[AppManifest],
    ) -> Optional[Path]:
        if install_path is None or manifest is None:
            return None

        return self._resolve_manifest_relative_file(
            install_path,
            manifest.ui_index_path,
        )

    def get_app_ui_asset_path(self, app_id: str, asset_relative_path: str) -> Optional[Path]:
        entry_path = self.get_app_ui_entry_path(app_id)
        if entry_path is None:
            return None

        raw = (asset_relative_path or "").strip()
        if not raw:
            return entry_path

        if raw.startswith("/"):
            return None

        ui_root = entry_path.parent.resolve()
        candidate = Path(raw)
        if candidate.is_absolute():
            return None

        resolved = (ui_root / candidate).resolve()
        if resolved != ui_root and ui_root not in resolved.parents:
            return None
        if not resolved.exists() or not resolved.is_file():
            return None
        return resolved

    @staticmethod
    def _resolve_manifest_relative_file(
        install_path: Path,
        relative_path: str,
    ) -> Optional[Path]:
        raw = (relative_path or "").strip()
        if not raw:
            return None

        candidate = Path(raw)
        if candidate.is_absolute():
            return None

        resolved_root = install_path.resolve()
        resolved = (resolved_root / candidate).resolve()
        if resolved_root != resolved and resolved_root not in resolved.parents:
            return None
        if not resolved.exists() or not resolved.is_file():
            return None
        return resolved

    def _record_exit(self, app_id, code):
        atomic_write_text(self._app_log_path(app_id).with_suffix(".exit"), f"exited {code} popen\n")

    def exit_result(self, app_id):
        try:
            fields = self._app_log_path(app_id).with_suffix(".exit").read_text().split()
        except FileNotFoundError:
            return None
        if len(fields) != 3:
            return None
        return 0 if fields[0:2] == ["exited", "0"] and fields[2] in ("success", "popen") else " ".join(fields)

    def _watch_process_exit(self, app_id: str, owned: tuple, identity: str) -> None:
        proc, stamp, tree = owned
        try:
            while proc.poll() is None:
                with self._snapshot_lock:
                    when, table = self._process_snapshot
                    if time.monotonic() - when >= .09:
                        table = processes()
                        self._process_snapshot = (time.monotonic(), table)
                remember(tree, proc.pid, stamp, table)
                time.sleep(0.1)
            with self._app_lock(app_id):
                if self._owned_processes.get(app_id) is not owned:
                    return  # A stop or restart has already retired this launch.
                terminate(tree, proc.pid, stamp)
                with self._process_lock:
                    self._guardian_message("remove", proc.pid, stamp)
                    self._owned_processes.pop(app_id, None)
                self._record_exit(app_id, proc.returncode)
                self._mark_stopped_if_pid_matches(app_id, proc.pid, identity, int(time.time()))
        except Exception:
            # Keep the tracked PID/state until cleanup can be retried.
            return

    def _mark_stopped_if_pid_matches(
        self, app_id: str, pid: Optional[int], identity: Optional[str], stopped_at: int
    ) -> None:
        with db_conn() as conn:
            conn.execute(
                "UPDATE app_runtime "
                "SET running=0, pid=NULL, process_identity=NULL, last_stopped_at=? "
                "WHERE app_id=? AND pid IS ? AND process_identity IS ?",
                (stopped_at, app_id, pid, identity),
            )
            conn.commit()

    def _sync_runtime_row(
        self,
        app_id: str,
        *,
        running: bool,
        pid: Optional[int],
        autostart: bool,
        process_identity: Optional[str] = None,
        last_started_at: Optional[int] = None,
        last_stopped_at: Optional[int] = None,
    ) -> None:
        with db_conn() as conn:
            conn.execute(
                "INSERT INTO app_runtime "
                "(app_id, running, autostart, pid, process_identity, last_started_at, last_stopped_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(app_id) DO UPDATE SET "
                "running=excluded.running, pid=excluded.pid, "
                "autostart=CASE WHEN ? THEN app_runtime.autostart ELSE excluded.autostart END, "
                "process_identity=excluded.process_identity, "
                "last_started_at=COALESCE(excluded.last_started_at, app_runtime.last_started_at), "
                "last_stopped_at=COALESCE(excluded.last_stopped_at, app_runtime.last_stopped_at)",
                (
                    app_id,
                    1 if running else 0,
                    1 if autostart else 0,
                    pid,
                    process_identity,
                    last_started_at,
                    last_stopped_at,
                    self._pipeline_autostart,
                ),
            )
            conn.commit()

    def read_logs(
        self, app_id: str, offset: int = 0, limit: int = 65536, from_end: bool = False
    ) -> Dict[str, Any]:
        if not self._versioning.list_versions(app_id):
            raise AppNotInstalledError(f"{app_id} is not installed")

        safe_offset = max(0, int(offset))
        safe_limit = max(1024, min(int(limit), 262144))

        log_path = self._app_log_path(app_id)
        if not log_path.exists():
            return {
                "app_id": app_id,
                "offset": 0,
                "next_offset": 0,
                "eof": True,
                "reset": safe_offset > 0,
                "chunk": "",
                "size": 0,
            }

        try:
            file_size = log_path.stat().st_size
        except OSError as exc:
            raise AppRuntimeError(f"读取日志大小失败: {exc}") from exc

        reset = safe_offset > file_size
        read_offset = file_size if from_end else (0 if reset else safe_offset)
        tail_aligned = read_offset + safe_limit < file_size
        if tail_aligned:
            read_offset = file_size - safe_limit
            reset = True

        raw = b""
        if not from_end:
            try:
                with log_path.open("rb") as f:
                    f.seek(read_offset)
                    raw = f.read(safe_limit)
            except OSError as exc:
                raise AppRuntimeError(f"读取日志失败: {exc}") from exc

        next_offset = read_offset + len(raw)
        eof = next_offset >= file_size

        return {
            "app_id": app_id,
            "offset": read_offset,
            "next_offset": next_offset,
            "eof": eof,
            "reset": reset,
            "tail_aligned": tail_aligned,
            "chunk": raw.decode("utf-8", errors="replace"),
            "size": file_size,
        }

    def _run_manifest_hook(
        self,
        *,
        app_id: str,
        manifest: AppManifest,
        hook_name: str,
        root_dir: Path,
        event_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        interactive: bool = False,
        read_input: Optional[Callable[[float], Optional[str]]] = None,
        cancel_requested: Optional[Callable[[], bool]] = None,
    ) -> bool:
        def emit(event_type: str, **payload: Any) -> None:
            if event_cb:
                event_cb(event_type, payload)

        script_path = getattr(manifest, hook_name, None)
        if not script_path:
            return False

        if cancel_requested and cancel_requested():
            raise OperationCanceledError("Operation canceled by user")

        emit(
            "status",
            phase=hook_name,
            status="running",
            message=f"执行 {hook_name}",
            app_id=app_id,
        )
        try:
            if interactive:
                self._script_hooks.run_interactive(
                    app_id=app_id,
                    hook_name=hook_name,
                    script_path=str(script_path),
                    root_dir=root_dir,
                    on_output=lambda chunk: emit(
                        "log",
                        phase=hook_name,
                        hook=hook_name,
                        chunk=chunk,
                        app_id=app_id,
                    ),
                    read_input=read_input,
                    cancel_requested=cancel_requested,
                )
            else:
                self._script_hooks.run(
                    app_id=app_id,
                    hook_name=hook_name,
                    script_path=str(script_path),
                    root_dir=root_dir,
                    on_output=lambda line: emit(
                        "log",
                        phase=hook_name,
                        hook=hook_name,
                        line=line,
                        app_id=app_id,
                    ),
                )
        except ScriptHookError as exc:
            if cancel_requested and cancel_requested():
                raise OperationCanceledError("Operation canceled by user") from exc
            raise AppRuntimeError(f"{hook_name} 执行失败: {exc}") from exc

        if cancel_requested and cancel_requested():
            raise OperationCanceledError("Operation canceled by user")
        return True
