from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from aivudaos.core.apps.caddy_config import CaddyConfigService
from aivudaos.core.apps.config_validation import validate_config_data
from aivudaos.core.apps.magnet import MagnetService
from aivudaos.core.apps.models import AppManifest, AppRuntimeState
from aivudaos.core.apps.script_hooks import ScriptHookError, ScriptHookRunner
from aivudaos.core.apps.systemd_runtime import SystemdRuntimeBackend
from aivudaos.core.apps.versioning import VersioningService
from aivudaos.core.config.service import ConfigService
from aivudaos.core.db.connection import db_conn
from aivudaos.core.errors import (
    AppNotInstalledError,
    InvalidConfigError,
    AppRuntimeError,
    NotFoundError,
    OperationCanceledError,
)
from aivudaos.core.paths import APP_LOG_DIR
from aivudaos.core.paths import SHELL_HELPERS_DIR
from aivudaos.core.paths import SYSTEMD_RUNTIME_DIR
from aivudaos.core.paths import UI_DEFAULT_ICON_PATH
from aivudaos.core.paths import UI_FALLBACK_ICON_PATH


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
        manifest_info: Optional[Dict[str, Any]] = None
        try:
            m = self._get_manifest(app_id, active_ver)
            manifest_info = m.to_dict()
        except Exception:
            pass

        runtime_state = self.get_runtime_state(app_id)
        built_in_ui_entry = self.get_app_ui_entry_path(app_id)

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
        }

    def get_installed_list(self) -> List[Dict[str, Any]]:
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
        seen: Dict[str, dict] = {}
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
                built_in_ui_entry = self.get_app_ui_entry_path(aid)
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
                    "has_builtin_ui": built_in_ui_entry is not None,
                }
            seen[aid]["versions"].append(row["version"])

        return list(seen.values())

    # ------------------------------------------------------------------ #
    #  Lifecycle: start / stop / restart
    # ------------------------------------------------------------------ #

    def start(self, app_id: str) -> Dict[str, Any]:
        active_version = self._versioning.active_version(app_id)
        if active_version is None:
            raise AppNotInstalledError(f"{app_id} has no active version")

        manifest = self._get_manifest(app_id, active_version)
        now = int(time.time())

        install_path = self._versioning.active_install_path(app_id)
        if install_path is None:
            raise AppNotInstalledError(f"{app_id} has no active version")

        runtime_state = self.get_runtime_state(app_id)

        command = self._build_exec_command(manifest, install_path)
        command = self._decorate_command_for_realtime_logs(command)
        config_env = self._build_config_env(
            app_id,
            active_version,
            manifest,
            install_path=install_path,
        )
        runtime_env = {**self._runtime_log_env(), **config_env}
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
                    environment=runtime_env,
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
                    env={**os.environ, **runtime_env},
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

    def stop(self, app_id: str) -> Dict[str, Any]:
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

    def restart(self, app_id: str) -> Dict[str, Any]:
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

    def set_autostart(self, app_id: str, enabled: bool) -> Dict[str, Any]:
        install_path = self._versioning.active_install_path(app_id)
        if install_path is None:
            raise AppNotInstalledError(f"{app_id} is not installed")

        scope = self._systemd_scope()
        if self._should_use_systemd(scope):
            manifest = self._get_manifest(app_id)
            command = self._build_exec_command(manifest, install_path)
            command = self._decorate_command_for_realtime_logs(command)
            active_version = self._versioning.active_version(app_id)
            if active_version is None:
                raise AppNotInstalledError(f"{app_id} has no active version")
            runtime_env = {
                **self._runtime_log_env(),
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
                self._systemd.write_unit(
                    app_id=app_id,
                    scope=scope,
                    command=command,
                    working_dir=install_path,
                    log_path=log_path,
                    description=f"AivudaOS app {manifest.name} ({app_id})",
                    environment=runtime_env,
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
    ) -> Dict[str, Any]:
        """Switch active version. Optionally stop old and start new."""
        current_active = self._versioning.active_version(app_id)
        runtime_state = self.get_runtime_state(app_id)

        try:
            manifest = self._get_manifest(app_id, version)
        except AppNotInstalledError as exc:
            raise NotFoundError(str(exc)) from exc

        self._ensure_version_config_ready(app_id, version, manifest)
        try:
            self._caddy.validate_candidate(
                app_id,
                manifest,
                self._versioning.version_dir(app_id, version),
            )
        except InvalidConfigError as exc:
            raise AppRuntimeError(f"switch_version validation failed: {exc}") from exc

        if runtime_state.running and restart:
            self.stop(app_id)

        self._versioning.activate_version(app_id, version)
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

        if runtime_state.running and restart:
            self.start(app_id)

        return {
            "ok": True,
            "app_id": app_id,
            "previous_version": current_active,
            "active_version": version,
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

    def _reconcile_systemd_units(self, scope: str) -> None:
        """Refresh systemd unit files for installed apps to keep runtime wrappers/env in sync."""
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT app_id, autostart FROM app_runtime ORDER BY app_id"
            ).fetchall()

        for row in rows:
            app_id = str(row["app_id"])
            enabled = bool(row["autostart"])
            install_path = self._versioning.active_install_path(app_id)
            if install_path is None:
                continue
            try:
                manifest = self._get_manifest(app_id)
                command = self._build_exec_command(manifest, install_path)
                command = self._decorate_command_for_realtime_logs(command)
                runtime_env = self._runtime_log_env()
                active_version = self._versioning.active_version(app_id)
                if active_version is None:
                    continue
                runtime_env = {
                    **runtime_env,
                    **self._build_config_env(
                        app_id,
                        active_version,
                        manifest,
                        install_path=install_path,
                    ),
                }
                log_path = self._app_log_path(app_id)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                self._systemd.write_unit(
                    app_id=app_id,
                    scope=scope,
                    command=command,
                    working_dir=install_path,
                    log_path=log_path,
                    description=f"AivudaOS app {manifest.name} ({app_id})",
                    environment=runtime_env,
                )
                self._systemd.set_enabled(app_id, scope, enabled)
            except (AppNotInstalledError, OSError, subprocess.SubprocessError, ValueError):
                continue

        try:
            self._systemd.daemon_reload(scope)
        except (OSError, subprocess.SubprocessError):
            pass

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
        cfg = self._config.get_app_config(app_id, app_version)
        default_data = self._config.get_app_default_config(
            app_id,
            app_version,
            fallback=manifest.default_config,
        )
        data = dict(cfg.data) if cfg.version > 0 else default_data
        try:
            validate_config_data(
                data,
                manifest.config_schema,
                context=f"runtime config {app_id}@{app_version}",
            )
        except InvalidConfigError as exc:
            raise AppRuntimeError(str(exc)) from exc

        config_path = self._config.app_config_path(app_id, app_version)
        install_path = install_path or self._versioning.version_dir(app_id, app_version)
        runtime_data_path = self._versioning.ensure_version_runtime_data_dir(
            app_id,
            app_version,
        )
        helpers_entry_path = (SHELL_HELPERS_DIR / "aivuda_app_helpers.sh").resolve()
        env: Dict[str, str] = {
            "AIVUDA_APP_ID": app_id,
            "AIVUDA_APP_VERSION": app_version,
            "AIVUDA_APP_INSTALL_PATH": str(install_path.resolve()),
            "AIVUDA_APP_RUNTIME_DATA_PATH": str(runtime_data_path.resolve()),
            "AIVUDA_APP_CONFIG_PATH": str(config_path.resolve()),
            "AIVUDA_APP_HELPERS_ENTRY_PATH": str(helpers_entry_path),
        }
        return env

    def _ensure_version_config_ready(
        self,
        app_id: str,
        app_version: str,
        manifest: AppManifest,
    ) -> None:
        cfg = self._config.get_app_config(app_id, app_version)
        if cfg.version == 0:
            self._config.init_app_config(app_id, app_version, manifest.default_config)
            cfg = self._config.get_app_config(app_id, app_version)

        default_data = self._config.get_app_default_config(
            app_id,
            app_version,
            fallback=manifest.default_config,
        )
        data = dict(cfg.data) if cfg.version > 0 else default_data
        try:
            validate_config_data(
                data,
                manifest.config_schema,
                context=f"switch config {app_id}@{app_version}",
            )
        except InvalidConfigError as exc:
            raise AppRuntimeError(str(exc)) from exc

    @staticmethod
    def _runtime_log_env() -> Dict[str, str]:
        return {
            "PYTHONUNBUFFERED": "1",
            "ROSCONSOLE_STDOUT_LINE_BUFFERED": "1",
            "TERM": "xterm-256color",
            "CLICOLOR_FORCE": "1",
            "FORCE_COLOR": "1",
            "PY_COLORS": "1",
        }

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
        if install_path is not None:
            try:
                manifest = self._get_manifest(app_id)
            except AppNotInstalledError:
                manifest = None

            if manifest and manifest.icon:
                icon_path = self._resolve_manifest_relative_file(
                    install_path,
                    manifest.icon,
                )
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
        self, app_id: str, pid: Optional[int], stopped_at: int
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
        pid: Optional[int],
        autostart: bool,
        last_started_at: Optional[int] = None,
        last_stopped_at: Optional[int] = None,
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
        read_offset = 0 if reset else safe_offset
        tail_aligned = False

        if read_offset + safe_limit < file_size:
            read_offset = max(0, file_size - safe_limit)
            reset = True
            tail_aligned = True

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
