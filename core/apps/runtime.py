from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import textwrap
import time
from pathlib import Path
from typing import Any

from core.apps.models import AppManifest, AppRuntimeState
from core.apps.versioning import VersioningService
from core.config.service import ConfigService
from core.db.connection import db_conn
from core.errors import (
    AppNotInstalledError,
    AppRuntimeError,
    RuntimeNotAvailableError,
)


def _run_cmd(
    args: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def _runtime_bin(runtime: str) -> str:
    bin_path = shutil.which(runtime)
    if not bin_path:
        raise RuntimeNotAvailableError(f"未检测到 {runtime}，请先安装运行环境")
    return bin_path


class RuntimeService:
    """App lifecycle management — start / stop / autostart / version switch.

    Manifest is always read from the app_installation DB table, so the service
    works identically for apps installed via local upload or remote catalog.
    """

    def __init__(
        self,
        versioning: VersioningService,
        config_service: ConfigService,
    ) -> None:
        self._versioning = versioning
        self._config = config_service

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
                "SELECT running, autostart, pid, container_id, last_started_at, last_stopped_at "
                "FROM app_runtime WHERE app_id = ?",
                (app_id,),
            ).fetchone()
        if not row:
            return AppRuntimeState(
                app_id=app_id,
                running=False,
                autostart=False,
                pid=None,
                container_id=None,
                last_started_at=None,
                last_stopped_at=None,
            )
        return AppRuntimeState(
            app_id=app_id,
            running=bool(row["running"]),
            autostart=bool(row["autostart"]),
            pid=row["pid"],
            container_id=row["container_id"],
            last_started_at=row["last_started_at"],
            last_stopped_at=row["last_stopped_at"],
        )

    def get_detail(self, app_id: str) -> dict[str, Any]:
        """Full detail: installation info + runtime state + active version."""
        with db_conn() as conn:
            install_rows = conn.execute(
                "SELECT app_id, version, runtime, install_path, status, installed_at "
                "FROM app_installation WHERE app_id = ? ORDER BY installed_at DESC",
                (app_id,),
            ).fetchall()
            runtime_row = conn.execute(
                "SELECT * FROM app_runtime WHERE app_id = ?", (app_id,)
            ).fetchone()

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

        return {
            "app_id": app_id,
            "installed": True,
            "active_version": active_ver,
            "versions": [dict(r) for r in install_rows],
            "runtime": dict(runtime_row) if runtime_row else None,
            "config": {"version": cfg.version, "updated_at": cfg.updated_at},
            "manifest": manifest_info,
        }

    def get_installed_list(self) -> list[dict[str, Any]]:
        """List all installed apps with runtime state and active version."""
        with db_conn() as conn:
            rows = conn.execute(
                """
                SELECT i.app_id, i.version, i.runtime, i.install_path, i.status, i.installed_at,
                       r.running, r.autostart, r.pid, r.container_id,
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
                seen[aid] = {
                    "app_id": aid,
                    "name": name,
                    "active_version": active_ver,
                    "versions": [],
                    "runtime": row["runtime"],
                    "install_path": str(self._versioning.active_link(aid)),
                    "status": row["status"],
                    "installed_at": row["installed_at"],
                    "running": bool(row["running"] or 0),
                    "autostart": bool(row["autostart"] or 0),
                    "pid": row["pid"],
                    "container_id": row["container_id"],
                    "last_started_at": row["last_started_at"],
                    "last_stopped_at": row["last_stopped_at"],
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
        runtime = manifest.runtime
        pid: int | None = None
        container_id: str | None = None

        if runtime == "host":
            command = self._host_exec_command(manifest, install_path)
            proc = subprocess.Popen(
                command,
                cwd=str(install_path),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            pid = proc.pid

        elif runtime in {"docker", "podman"}:
            container_id = self._start_container(manifest, app_id, runtime)

        else:
            raise AppRuntimeError(f"不支持的 runtime: {runtime}")

        with db_conn() as conn:
            conn.execute(
                "INSERT INTO app_runtime (app_id, running, autostart, pid, container_id, last_started_at) "
                "VALUES (?, 1, ?, ?, ?, ?) "
                "ON CONFLICT(app_id) DO UPDATE SET running=1, pid=excluded.pid, "
                "container_id=excluded.container_id, last_started_at=excluded.last_started_at",
                (app_id, int(runtime_state.autostart), pid, container_id, now),
            )
            conn.commit()

        return {"ok": True, "app_id": app_id, "running": True, "runtime": runtime}

    def stop(self, app_id: str) -> dict[str, Any]:
        now = int(time.time())
        runtime_state = self.get_runtime_state(app_id)

        with db_conn() as conn:
            row = conn.execute(
                "SELECT runtime FROM app_installation WHERE app_id = ? LIMIT 1",
                (app_id,),
            ).fetchone()
        if not row:
            raise AppNotInstalledError(f"{app_id} is not installed")
        runtime = row["runtime"]

        if runtime == "host":
            if runtime_state.pid:
                try:
                    os.kill(runtime_state.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        elif runtime in {"docker", "podman"}:
            manifest = self._get_manifest(app_id)
            rt_path = _runtime_bin(runtime)
            cname = manifest.run.get("container_name", f"aivuda-{app_id}")
            result = _run_cmd([rt_path, "stop", cname])
            if result.returncode != 0 and "No such container" not in (
                result.stderr or ""
            ):
                raise AppRuntimeError(
                    (result.stderr or result.stdout or "").strip()
                )

        with db_conn() as conn:
            conn.execute(
                "UPDATE app_runtime SET running=0, pid=NULL, container_id=NULL, last_stopped_at=? "
                "WHERE app_id=?",
                (now, app_id),
            )
            conn.commit()

        return {"ok": True, "app_id": app_id, "running": False}

    def restart(self, app_id: str) -> dict[str, Any]:
        """Stop then start an app."""
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

        try:
            self._ensure_systemd_unit(app_id)
            self._systemd_call("daemon-reload")
            service = self._unit_name(app_id)
            self._systemd_call("enable" if enabled else "disable", service)
        except RuntimeError as exc:
            raise AppRuntimeError(
                f"systemd 自启动设置失败: {exc}"
            ) from exc

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

        # Regenerate systemd unit if autostart is on
        if runtime_state.autostart:
            try:
                self._ensure_systemd_unit(app_id)
                self._systemd_call("daemon-reload")
            except RuntimeError:
                pass

        if runtime_state.running and restart:
            self.start(app_id)

        return {
            "ok": True,
            "app_id": app_id,
            "previous_version": current_active,
            "active_version": version,
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
            self._remove_systemd_unit(app_id)
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
            active = self._versioning.active_version(app_id)
            if active == version and runtime_state.running:
                self.stop(app_id)
            self._versioning.remove_version(app_id, version)
            # If we removed the active version, try to activate another
            remaining = self._versioning.list_versions(app_id)
            if active == version and remaining:
                self._versioning.activate_version(app_id, remaining[0])
            elif not remaining:
                self._remove_systemd_unit(app_id)
                with db_conn() as conn:
                    conn.execute(
                        "DELETE FROM app_runtime WHERE app_id = ?", (app_id,)
                    )
                    conn.commit()
                if purge:
                    self._config.delete_app_config(app_id)

        return {"ok": True, "app_id": app_id, "version": version, "purge": purge}

    # ------------------------------------------------------------------ #
    #  Systemd helpers
    # ------------------------------------------------------------------ #

    def _unit_name(self, app_id: str) -> str:
        return f"aivuda-app-{app_id}.service"

    def _systemd_user_dir(self) -> Path:
        p = Path.home() / ".config" / "systemd" / "user"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _systemd_call(self, *args: str) -> None:
        result = _run_cmd(["systemctl", "--user", *args])
        if result.returncode != 0:
            raise RuntimeError(
                (result.stderr or result.stdout or "systemctl 执行失败").strip()
            )

    def _ensure_systemd_unit(self, app_id: str) -> Path:
        manifest = self._get_manifest(app_id)
        install_path = self._versioning.active_install_path(app_id)
        if install_path is None:
            raise AppNotInstalledError(f"{app_id} has no active version")

        runtime = manifest.runtime
        unit_path = self._systemd_user_dir() / self._unit_name(app_id)

        if runtime == "host":
            cmd = self._host_exec_command(manifest, install_path)
            cmd_line = shlex.join(cmd)
            exec_start = f"/bin/bash -lc {shlex.quote(f'cd {shlex.quote(str(install_path))} && {cmd_line}')}"
            exec_stop = ""
        else:
            rt_path = _runtime_bin(runtime)
            cname = manifest.run.get("container_name", f"aivuda-{app_id}")
            exec_start = f"{rt_path} start -a {cname}"
            exec_stop = f"{rt_path} stop {cname}"

        content = textwrap.dedent(
            f"""
            [Unit]
            Description=AivudaOS App {app_id}
            After=network.target

            [Service]
            Type=simple
            WorkingDirectory={install_path}
            ExecStart={exec_start}
            Restart=on-failure
            RestartSec=3
            {f'ExecStop={exec_stop}' if exec_stop else ''}

            [Install]
            WantedBy=default.target
            """
        ).strip() + "\n"

        unit_path.write_text(content, encoding="utf-8")
        return unit_path

    def _remove_systemd_unit(self, app_id: str) -> None:
        service = self._unit_name(app_id)
        try:
            self._systemd_call("disable", service)
        except Exception:
            pass
        try:
            self._systemd_call("stop", service)
        except Exception:
            pass
        unit_path = self._systemd_user_dir() / service
        if unit_path.exists():
            unit_path.unlink()
        try:
            self._systemd_call("daemon-reload")
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  Process / container helpers
    # ------------------------------------------------------------------ #

    def _host_exec_command(
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

    def _start_container(
        self, manifest: AppManifest, app_id: str, runtime: str
    ) -> str | None:
        rt_path = _runtime_bin(runtime)
        run_cfg = manifest.run
        install_cfg = manifest.install
        image = install_cfg.get("image")
        cname = run_cfg.get("container_name", f"aivuda-{app_id}")

        exists_check = _run_cmd(
            [rt_path, "ps", "-a", "--filter", f"name=^{cname}$", "--format", "{{.ID}}"]
        )
        if exists_check.returncode != 0:
            raise AppRuntimeError(
                (exists_check.stderr or exists_check.stdout).strip()
            )

        existing_id = (exists_check.stdout or "").strip()
        if existing_id:
            start_result = _run_cmd([rt_path, "start", cname])
            if start_result.returncode != 0:
                raise AppRuntimeError(
                    (start_result.stderr or start_result.stdout).strip()
                )
        else:
            if not image:
                raise AppRuntimeError("容器应用未配置镜像")
            cmd = [rt_path, "run", "-d", "--name", cname]
            for port in run_cfg.get("ports", []):
                cmd.extend(["-p", str(port)])

            # Merge default env with app config
            app_cfg = self._config.get_app_config(app_id)
            merged_env = dict(run_cfg.get("env", {}))
            merged_env.update({k.upper(): str(v) for k, v in app_cfg.data.items()})
            for key, value in merged_env.items():
                cmd.extend(["-e", f"{key}={value}"])

            cmd.append(image)
            run_result = _run_cmd(cmd)
            if run_result.returncode != 0:
                raise AppRuntimeError(
                    (run_result.stderr or run_result.stdout).strip()
                )
            existing_id = (run_result.stdout or "").strip()

        id_check = _run_cmd(
            [rt_path, "ps", "--filter", f"name=^{cname}$", "--format", "{{.ID}}"]
        )
        if id_check.returncode == 0 and id_check.stdout.strip():
            return id_check.stdout.strip()
        return existing_id[:12] if existing_id else None
