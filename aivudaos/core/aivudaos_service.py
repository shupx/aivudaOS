from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

from aivudaos import __version__
from aivudaos.core.paths import PACKAGE_RESOURCES_ROOT


class AivudaosServiceManager:
    """Manage the packaged AivudaOS user service lifecycle."""

    def get_status(self) -> Dict[str, Any]:
        installed = self._stack_unit_exists()
        return {
            "ok": True,
            "version": __version__,
            "installed": installed,
            "running": installed and self._systemctl_user_quiet(["is-active", "aivudaos.service"]),
            "autostart_enabled": installed and self._systemctl_user_quiet(["is-enabled", "aivudaos.service"]),
        }

    def set_autostart(self, enabled: bool) -> Dict[str, Any]:
        script_name = (
            "_enable_autostart_aivudaos_service.sh"
            if enabled
            else "_disable_autostart_aivudaos_service.sh"
        )
        self._run_script_sync(script_name)
        return self.get_status()

    def schedule_action(self, action: str) -> Dict[str, Any]:
        script_map = {
            "stop": "_stop_aivudaos_service.sh",
            "restart": "_restart_aivudaos_service.sh",
            "uninstall": "uninstall_aivudaos.sh",
        }
        script_name = script_map.get(action)
        if script_name is None:
            raise ValueError("Unsupported aivudaos service action")

        self._run_script_detached(script_name)
        return {
            "ok": True,
            "accepted": True,
            "action": action,
        }

    def _script_path(self, script_name: str) -> Path:
        script_path = PACKAGE_RESOURCES_ROOT / "scripts" / script_name
        if not script_path.exists():
            raise RuntimeError(f"AivudaOS script not found: {script_path}")
        return script_path

    def _build_script_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env["AIVUDAOS_PACKAGE_ROOT"] = str(PACKAGE_RESOURCES_ROOT)
        return env

    def _run_script_sync(self, script_name: str) -> None:
        script_path = self._script_path(script_name)
        completed = subprocess.run(
            ["bash", str(script_path)],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self._build_script_env(),
        )
        if completed.returncode == 0:
            return

        output = "\n".join(
            item.strip()
            for item in [completed.stdout or "", completed.stderr or ""]
            if item and item.strip()
        ).strip()
        if output:
            raise RuntimeError(output)
        raise RuntimeError(
            "AivudaOS service script failed with exit code {}".format(completed.returncode)
        )

    def _run_script_detached(self, script_name: str) -> None:
        script_path = self._script_path(script_name)
        command = "sleep 1; exec bash {script}".format(
            script=shlex.quote(str(script_path))
        )
        env = self._build_script_env()
        if self._can_use_systemd_run():
            unit_name = "aivudaos-control-{}-{}".format(
                script_name.replace(".sh", "").replace("_", "-"),
                int(time.time() * 1000),
            )
            completed = subprocess.run(
                [
                    "systemd-run",
                    "--user",
                    "--unit",
                    unit_name,
                    "--collect",
                    "--quiet",
                    "/usr/bin/env",
                    "bash",
                    "-lc",
                    command,
                ],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            if completed.returncode == 0:
                return

        subprocess.Popen(
            ["bash", "-lc", command],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )

    @staticmethod
    def _systemctl_user_quiet(args: List[str]) -> bool:
        try:
            completed = subprocess.run(
                ["systemctl", "--user", *args],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return False
        return completed.returncode == 0

    @staticmethod
    def _stack_unit_exists() -> bool:
        return (Path.home() / ".config" / "systemd" / "user" / "aivudaos.service").exists()

    @staticmethod
    def _can_use_systemd_run() -> bool:
        try:
            completed = subprocess.run(
                ["systemd-run", "--user", "--version"],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return False
        return completed.returncode == 0
