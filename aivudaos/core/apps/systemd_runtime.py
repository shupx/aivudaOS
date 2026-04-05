from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class SystemdState:
    running: bool
    enabled: bool
    pid: Optional[int]


class SystemdRuntimeBackend:
    """Manage app process lifecycle via systemd units."""

    UNIT_PREFIX = "aivuda-app"
    COMMON_RUNTIME_ENV: dict[str, str] = {
        "PYTHONUNBUFFERED": "1",
        "ROSCONSOLE_STDOUT_LINE_BUFFERED": "1",
        "TERM": "xterm-256color",
        "CLICOLOR_FORCE": "1",
        "FORCE_COLOR": "1",
        "PY_COLORS": "1",
    }

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    def is_available(self, scope: str) -> bool:
        if shutil.which("systemctl") is None:
            return False
        try:
            self._run_systemctl(scope, ["show", "--property=Version"], check=True)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    def unit_name(self, app_id: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", app_id).strip("-_.")
        if not normalized:
            raise ValueError("invalid app_id for systemd unit")
        return f"{self.UNIT_PREFIX}-{normalized}.service"

    def unit_file_path(self, app_id: str, scope: str) -> Path:
        unit_name = self.unit_name(app_id)
        if scope == "system":
            return Path("/etc/systemd/system") / unit_name

        config_home = Path.home() / ".config"
        return config_home / "systemd" / "user" / unit_name

    def write_unit(
        self,
        app_id: str,
        scope: str,
        command: list[str],
        working_dir: Path,
        log_path: Path,
        description: str,
        environment: Optional[dict[str, str]] = None,
    ) -> Path:
        unit_path = self.unit_file_path(app_id, scope)
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        common_env_path = self._ensure_common_runtime_env_file()

        exec_start = " ".join(shlex.quote(part) for part in command)
        truncate_bin = shutil.which("truncate") or "/usr/bin/truncate"
        exec_start_pre = " ".join(
            shlex.quote(part)
            for part in [truncate_bin, "-s", "0", str(log_path)]
        )
        escaped_workdir = shlex.quote(str(working_dir))
        escaped_log = shlex.quote(str(log_path))
        wanted_by = "multi-user.target" if scope == "system" else "default.target"
        env_lines = []
        for key, value in (environment or {}).items():
            safe_key = str(key).strip()
            if not safe_key:
                continue
            if safe_key in self.COMMON_RUNTIME_ENV:
                continue
            safe_val = str(value).replace('"', '\\"')
            env_lines.append(f'Environment="{safe_key}={safe_val}"')

        unit_lines = [
            "[Unit]",
            f"Description={description}",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={escaped_workdir}",
            f"ExecStartPre={exec_start_pre}",
            f"EnvironmentFile={common_env_path}",
            *env_lines,
            f"ExecStart={exec_start}",
            f"StandardOutput=append:{escaped_log}",
            f"StandardError=append:{escaped_log}",
            "KillMode=control-group",
            "Restart=no",
            "",
            "[Install]",
            f"WantedBy={wanted_by}",
            "",
        ]
        unit_content = "\n".join(unit_lines)
        unit_path.write_text(unit_content, encoding="utf-8")
        return unit_path

    def _ensure_common_runtime_env_file(self) -> Path:
        env_path = (
            self._project_root
            / "core"
            / "shell_helpers"
            / "env"
            / "runtime_common.env"
        )
        env_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"{k}={v}" for k, v in self.COMMON_RUNTIME_ENV.items()]
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return env_path

    def daemon_reload(self, scope: str) -> None:
        self._run_systemctl(scope, ["daemon-reload"], check=True)

    def start(self, app_id: str, scope: str) -> None:
        self._run_systemctl(scope, ["start", self.unit_name(app_id)], check=True)

    def stop(self, app_id: str, scope: str) -> None:
        self._run_systemctl(scope, ["stop", self.unit_name(app_id)], check=True)

    def restart(self, app_id: str, scope: str) -> None:
        self._run_systemctl(scope, ["restart", self.unit_name(app_id)], check=True)

    def set_enabled(self, app_id: str, scope: str, enabled: bool) -> None:
        action = "enable" if enabled else "disable"
        self._run_systemctl(scope, [action, self.unit_name(app_id)], check=True)

    def get_state(self, app_id: str, scope: str) -> SystemdState:
        unit_name = self.unit_name(app_id)
        proc = self._run_systemctl(
            scope,
            [
                "show",
                unit_name,
                "--property=ActiveState,MainPID,UnitFileState",
                "--no-pager",
            ],
            check=False,
        )
        data: dict[str, str] = {}
        for line in (proc.stdout or "").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()

        active_state = data.get("ActiveState", "inactive")
        raw_pid = data.get("MainPID", "0")
        pid = int(raw_pid) if raw_pid.isdigit() and int(raw_pid) > 0 else None
        unit_state = data.get("UnitFileState", "disabled")

        return SystemdState(
            running=active_state == "active",
            enabled=unit_state == "enabled",
            pid=pid,
        )

    def remove_unit(self, app_id: str, scope: str) -> None:
        unit_path = self.unit_file_path(app_id, scope)
        if unit_path.exists():
            unit_path.unlink()
            self.daemon_reload(scope)

    def _run_systemctl(
        self,
        scope: str,
        args: list[str],
        *,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        base = ["systemctl"]
        if scope == "user":
            base.append("--user")
        cmd = [*base, *args]
        return subprocess.run(
            cmd,
            check=check,
            capture_output=True,
            text=True,
            cwd=str(self._project_root),
        )
