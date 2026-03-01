from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from core.apps.models import AppManifest, AppRuntimeState
from core.apps.script_hooks import ScriptHookError, ScriptHookRunner
from core.apps.systemd_runtime import SystemdRuntimeBackend
from core.apps.versioning import VersioningService
from core.config.service import ConfigService
from core.db.connection import db_conn
from core.errors import (
    AppNotInstalledError,
    AppRuntimeError,
    NotFoundError,
)
from core.paths import APP_LOG_DIR
from core.paths import PROJECT_ROOT


class RuntimeService:
    """App lifecycle management — start / stop / autostart / version switch.

    Manifest is always read from the app_installation DB table.
    """

    def __init__(
        self,
        versioning: VersioningService,
        config_service: ConfigService,
    ) -> None:
        self._versioning = versioning
        self._config = config_service
        self._systemd = SystemdRuntimeBackend(PROJECT_ROOT)
        self._script_hooks = ScriptHookRunner()

    # ------------------------------------------------------------------ #
    #  Manifest from DB
    # ------------------------------------------------------------------ #

    def _get_manifest(self, app_id: str, version: str | None = None) -> AppManifest:
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

    def get_runtime_state(self, app_id: str) -> AppRuntimeState:
        with db_conn() as conn:
            row = conn.execute(
                "SELECT running, autostart, pid, last_started_at, last_stopped_at "
                "FROM app_runtime WHERE app_id = ?",
                (app_id,),
            ).fetchone()
        if not row:
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
        autostart = bool(row["autostart"])
        stopped_at = row["last_stopped_at"]

        scope = self._systemd_scope()
        using_systemd = False
        if self._should_use_systemd(scope):
            try:
                live = self._systemd.get_state(app_id, scope)
                using_systemd = True
                running = live.running
                pid = live.pid
                autostart = live.enabled
                self._sync_runtime_row(
                    app_id,
                    running=running,
                    pid=pid,
                    autostart=autostart,
                    last_stopped_at=int(time.time()) if not running else None,
                )
            except (subprocess.SubprocessError, OSError):
                using_systemd = False

        if (not using_systemd) and running and (not pid or not self._is_pid_alive(int(pid))):
            stopped_at = int(time.time())
            self._mark_stopped_if_pid_matches(app_id, pid, stopped_at)
            running = False
            pid = None

        return AppRuntimeState(
            app_id=app_id,
            running=running,
            autostart=autostart,
            pid=pid,
            last_started_at=row["last_started_at"],
            last_stopped_at=stopped_at,
        )

    def get_detail(self, app_id: str) -> dict[str, Any]:
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
        cfg = self._config.get_app_config(app_id)

        # Include manifest for the active version
        manifest_info: dict[str, Any] | None = None
        try:
            m = self._get_manifest(app_id, active_ver)
            manifest_info = m.to_dict()
        except Exception:
            pass

        runtime_state = self.get_runtime_state(app_id)

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
            "config": {"version": cfg.version, "updated_at": cfg.updated_at},
            "manifest": manifest_info,
        }

    def get_installed_list(self) -> list[dict[str, Any]]:
        """List all installed apps with runtime state and active version."""
        with db_conn() as conn:
            rows = conn.execute(
                """
                SELECT i.app_id, i.version, i.install_path, i.status, i.installed_at,
                       r.running, r.autostart, r.pid,
                       r.last_started_at, r.last_stopped_at
                FROM app_installation i
                LEFT JOIN app_runtime r ON r.app_id = i.app_id
                ORDER BY i.installed_at DESC
                """
            ).fetchall()

        # Group by app_id, return one entry per app with version list
        seen: dict[str, dict] = {}
        for row in rows:
            aid = row["app_id"]
            if aid not in seen:
                active_ver = self._versioning.active_version(aid)
                # Attempt to read manifest name
                name = aid
                try:
                    m = self._get_manifest(aid, active_ver)
                    name = m.name
                except Exception:
                    pass
                runtime_state = self.get_runtime_state(aid)
                seen[aid] = {
                    "app_id": aid,
                    "name": name,
                    "active_version": active_ver,
                    "versions": [],
                    "install_path": str(self._versioning.active_link(aid)),
                    "status": row["status"],
                    "installed_at": row["installed_at"],
                    "running": runtime_state.running,
                    "autostart": runtime_state.autostart,
                    "pid": runtime_state.pid,
                    "last_started_at": runtime_state.last_started_at,
                    "last_stopped_at": runtime_state.last_stopped_at,
                }
            seen[aid]["versions"].append(row["version"])

        return list(seen.values())

    # ------------------------------------------------------------------ #
    #  Lifecycle: start / stop / restart
    # ------------------------------------------------------------------ #

    def start(self, app_id: str) -> dict[str, Any]:
        manifest = self._get_manifest(app_id)
        now = int(time.time())

        install_path = self._versioning.active_install_path(app_id)
        if install_path is None:
            raise AppNotInstalledError(f"{app_id} has no active version")

        runtime_state = self.get_runtime_state(app_id)

        command = self._build_exec_command(manifest, install_path)
        log_path = self._app_log_path(app_id)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        scope = self._systemd_scope()
        if self._should_use_systemd(scope):
            try:
                self._systemd.write_unit(
                    app_id=app_id,
                    scope=scope,
                    command=command,
                    working_dir=install_path,
                    log_path=log_path,
                    description=f"AivudaOS app {manifest.name} ({app_id})",
                )
                self._systemd.daemon_reload(scope)
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

        try:
            with log_path.open("wb") as log_file:
                proc = subprocess.Popen(
                    command,
                    cwd=str(install_path),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        except OSError as exc:
            raise AppRuntimeError(f"启动 {app_id} 失败，无法写入日志: {exc}") from exc

        self._sync_runtime_row(
            app_id,
            running=True,
            pid=proc.pid,
            autostart=runtime_state.autostart,
            last_started_at=now,
        )

        watcher = threading.Thread(
            target=self._watch_process_exit,
            args=(app_id, proc),
            daemon=True,
        )
        watcher.start()

        return {"ok": True, "app_id": app_id, "running": True}

    def stop(self, app_id: str) -> dict[str, Any]:
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

        if runtime_state.pid:
            try:
                os.kill(runtime_state.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        self._sync_runtime_row(
            app_id,
            running=False,
            pid=None,
            autostart=runtime_state.autostart,
            last_stopped_at=now,
        )

        return {"ok": True, "app_id": app_id, "running": False}

    def restart(self, app_id: str) -> dict[str, Any]:
        """Stop then start an app."""
        scope = self._systemd_scope()
        if self._should_use_systemd(scope):
            if not self._versioning.list_versions(app_id):
                raise AppNotInstalledError(f"{app_id} is not installed")
            now = int(time.time())
            try:
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

    def set_autostart(self, app_id: str, enabled: bool) -> dict[str, Any]:
        install_path = self._versioning.active_install_path(app_id)
        if install_path is None:
            raise AppNotInstalledError(f"{app_id} is not installed")

        scope = self._systemd_scope()
        if self._should_use_systemd(scope):
            manifest = self._get_manifest(app_id)
            command = self._build_exec_command(manifest, install_path)
            log_path = self._app_log_path(app_id)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._systemd.write_unit(
                    app_id=app_id,
                    scope=scope,
                    command=command,
                    working_dir=install_path,
                    log_path=log_path,
                    description=f"AivudaOS app {manifest.name} ({app_id})",
                )
                self._systemd.daemon_reload(scope)
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
    ) -> dict[str, Any]:
        """Switch active version. Optionally stop old and start new."""
        current_active = self._versioning.active_version(app_id)
        runtime_state = self.get_runtime_state(app_id)

        if runtime_state.running and restart:
            self.stop(app_id)

        self._versioning.activate_version(app_id, version)

        if runtime_state.running and restart:
            self.start(app_id)

        return {
            "ok": True,
            "app_id": app_id,
            "previous_version": current_active,
            "active_version": version,
        }

    def update_version(self, app_id: str, version: str) -> dict[str, Any]:
        versions = self._versioning.list_versions(app_id)
        if not versions:
            raise AppNotInstalledError(f"{app_id} is not installed")
        if version not in versions:
            raise NotFoundError(
                f"Version {version} is not installed for {app_id}"
            )

        manifest = self._get_manifest(app_id, version)
        install_path = self._versioning.version_dir(app_id, version)
        executed = self._run_manifest_hook(
            app_id=app_id,
            manifest=manifest,
            hook_name="update_version",
            root_dir=install_path,
        )

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
        version: str | None = None,
        purge: bool = False,
    ) -> dict[str, Any]:
        """Uninstall a specific version or the entire app."""
        runtime_state = self.get_runtime_state(app_id)

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
                self._run_manifest_hook(
                    app_id=app_id,
                    manifest=manifest,
                    hook_name="pre_uninstall",
                    root_dir=self._versioning.version_dir(app_id, hook_version),
                )

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
            self._run_manifest_hook(
                app_id=app_id,
                manifest=manifest,
                hook_name="pre_uninstall",
                root_dir=self._versioning.version_dir(app_id, version),
            )

            active = self._versioning.active_version(app_id)
            if active == version and runtime_state.running:
                self.stop(app_id)
            self._versioning.remove_version(app_id, version)
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

        return {"ok": True, "app_id": app_id, "version": version, "purge": purge}

    def start_autostart_apps(self) -> dict[str, Any]:
        scope = self._systemd_scope()
        if self._should_use_systemd(scope):
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

        started: list[str] = []
        skipped: list[str] = []
        failed: list[dict[str, str]] = []

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

    def _should_use_systemd(self, scope: str | None = None) -> bool:
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
    ) -> list[str]:
        entrypoint = manifest.run.get("entrypoint")
        if not entrypoint:
            raise AppRuntimeError("app run.entrypoint 未配置")
        entry = Path(entrypoint)
        resolved = (
            (install_path / entry).resolve() if not entry.is_absolute() else entry
        )
        args = manifest.run.get("args", [])
        return [str(resolved), *[str(x) for x in args]]

    def _app_log_path(self, app_id: str) -> Path:
        return APP_LOG_DIR / app_id / "current.log"

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        else:
            return True

    def _watch_process_exit(self, app_id: str, proc: subprocess.Popen[Any]) -> None:
        try:
            proc.wait()
        except Exception:
            return

        stopped_at = int(time.time())
        self._mark_stopped_if_pid_matches(app_id, proc.pid, stopped_at)

    def _mark_stopped_if_pid_matches(
        self, app_id: str, pid: int | None, stopped_at: int
    ) -> None:
        if pid is None:
            return

        with db_conn() as conn:
            conn.execute(
                "UPDATE app_runtime "
                "SET running=0, pid=NULL, last_stopped_at=? "
                "WHERE app_id=? AND pid=?",
                (stopped_at, app_id, pid),
            )
            conn.commit()

    def _sync_runtime_row(
        self,
        app_id: str,
        *,
        running: bool,
        pid: int | None,
        autostart: bool,
        last_started_at: int | None = None,
        last_stopped_at: int | None = None,
    ) -> None:
        with db_conn() as conn:
            conn.execute(
                "INSERT INTO app_runtime "
                "(app_id, running, autostart, pid, last_started_at, last_stopped_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(app_id) DO UPDATE SET "
                "running=excluded.running, autostart=excluded.autostart, pid=excluded.pid, "
                "last_started_at=COALESCE(excluded.last_started_at, app_runtime.last_started_at), "
                "last_stopped_at=COALESCE(excluded.last_stopped_at, app_runtime.last_stopped_at)",
                (
                    app_id,
                    1 if running else 0,
                    1 if autostart else 0,
                    pid,
                    last_started_at,
                    last_stopped_at,
                ),
            )
            conn.commit()

    def read_logs(
        self, app_id: str, offset: int = 0, limit: int = 65536
    ) -> dict[str, Any]:
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
        read_offset = 0 if reset else safe_offset

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
    ) -> bool:
        script_path = getattr(manifest, hook_name, None)
        if not script_path:
            return False

        try:
            self._script_hooks.run(
                app_id=app_id,
                hook_name=hook_name,
                script_path=str(script_path),
                root_dir=root_dir,
            )
        except ScriptHookError as exc:
            raise AppRuntimeError(f"{hook_name} 执行失败: {exc}") from exc
        return True
