from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import threading
import time

from aivudaos.core.config.filelock import atomic_write_text
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class SystemdState:
    running: bool
    enabled: bool
    pid: Optional[int]


class SystemdRuntimeBackend:
    """Manage app process lifecycle via systemd units."""

    UNIT_PREFIX = "aivuda-app"
    COMMON_RUNTIME_ENV: Dict[str, str] = {
        "PYTHONUNBUFFERED": "1",
        "ROSCONSOLE_STDOUT_LINE_BUFFERED": "1",
        "TERM": "xterm-256color",
        "CLICOLOR_FORCE": "1",
        "FORCE_COLOR": "1",
        "PY_COLORS": "1",
    }

    def __init__(self, shell_helpers_dir: Path, runtime_dir: Path) -> None:
        self._shell_helpers_dir = shell_helpers_dir
        self._runtime_dir = runtime_dir
        self._availability = {}
        self._lock = threading.RLock()
        self._dirty_scopes = set()

    def is_available(self, scope: str) -> bool:
        with self._lock:
            expiry, value = self._availability.get(scope, (0, False))
            if time.monotonic() >= expiry:
                value = self._check_available(scope)
                self._availability[scope] = (time.monotonic() + 5, value)
            return value

    def _check_available(self, scope):
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
        command: List[str],
        working_dir: Path,
        log_path: Path,
        description: str,
        environment: Optional[Dict[str, str]] = None,
    ) -> Path:
        unit_path = self.unit_file_path(app_id, scope)
        unit_path.parent.mkdir(parents=True, exist_ok=True)

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
        for key, value in {**self.COMMON_RUNTIME_ENV, **(environment or {})}.items():
            safe_key = str(key).strip()
            if not safe_key:
                continue
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", safe_key):
                raise ValueError("Invalid environment variable name")
            if any(char in str(value) for char in ("\x00", "\n", "\r")):
                raise ValueError("Invalid environment variable value")
            safe_val = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
            env_lines.append(f'Environment="{safe_key}={safe_val}"')

        receipt = shlex.quote(str(log_path.with_suffix(".exit")))
        unit_lines = [
            "[Unit]",
            f"Description={description}",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={escaped_workdir}",
            f"ExecStartPre=/bin/rm -f {receipt}",
            f"ExecStartPre={exec_start_pre}",
            *env_lines,
            f"ExecStart={exec_start}",
            f"StandardOutput=append:{escaped_log}",
            f"StandardError=append:{escaped_log}",
            f"""ExecStopPost=/bin/sh -c 'echo "$$EXIT_CODE $$EXIT_STATUS $$SERVICE_RESULT" > "$$1"' sh {receipt}""",
            "KillMode=control-group",
            "Restart=no",
            "",
            "[Install]",
            f"WantedBy={wanted_by}",
            "",
        ]
        unit_content = "\n".join(unit_lines)
        with self._lock:
            if not unit_path.exists() or unit_path.read_text(encoding="utf-8") != unit_content:
                atomic_write_text(unit_path, unit_content)
                self._dirty_scopes.add(scope)
        return unit_path

    def daemon_reload(self, scope: str) -> None:
        with self._lock:
            self._run_systemctl(scope, ["daemon-reload"], check=True)
            self._dirty_scopes.discard(scope)

    def reload_changed_units(self, scope):
        with self._lock:
            if scope in self._dirty_scopes:
                self.daemon_reload(scope)

    def start(self, app_id: str, scope: str) -> None:
        self._run_systemctl(scope, ["start", self.unit_name(app_id)], check=True)

    def stop(self, app_id: str, scope: str) -> None:
        self._run_systemctl(scope, ["stop", self.unit_name(app_id)], check=True)

    def restart(self, app_id: str, scope: str) -> None:
        self._run_systemctl(scope, ["restart", self.unit_name(app_id)], check=True)

    def set_enabled(self, app_id: str, scope: str, enabled: bool, *, defer_reload: bool = False) -> None:
        action = "enable" if enabled else "disable"
        args = [action, self.unit_name(app_id)]
        if defer_reload:
            args.insert(0, "--no-reload")
        self._run_systemctl(scope, args, check=True)

    def get_state(self, app_id: str, scope: str) -> SystemdState:
        return self.get_states([app_id], scope)[app_id]

    def get_states(self, app_ids, scope):
        names = {self.unit_name(app): app for app in app_ids}
        if not names:
            return {}
        result = self._run_systemctl(scope, ["show", *names, "--all",
            "--property=Id,ActiveState,MainPID,UnitFileState", "--no-pager"], check=False)
        states = {}
        for block in result.stdout.strip().split("\n\n"):
            data = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
            app = names.get(data.get("Id"))
            if app is not None and "ActiveState" in data:
                pid = int(data.get("MainPID") or 0)
                states[app] = SystemdState(data["ActiveState"] == "active",
                                          data.get("UnitFileState") == "enabled", pid or None)
        if len(states) != len(names):
            raise OSError("Incomplete systemctl show response")
        return states

    def remove_unit(self, app_id: str, scope: str) -> None:
        unit_path = self.unit_file_path(app_id, scope)
        if unit_path.exists():
            unit_path.unlink()
            self.daemon_reload(scope)

    def _run_systemctl(
        self,
        scope: str,
        args: List[str],
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
        )
