from __future__ import annotations

import os
import random
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Set


class AvahiService:
    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._config_path = config_path or Path("/etc/avahi/avahi-daemon.conf")
        self._hostname_re = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")

    def generate_hostname(self, *, retries: int = 8, existing: Optional[Set[str]] = None) -> str:
        occupied = {str(item).strip().lower() for item in (existing or set()) if str(item).strip()}
        rand = random.SystemRandom()
        for _ in range(max(1, retries)):
            base = int(time.time()) + rand.randint(0, 4095)
            candidate = f"robot-{base & 0xFFF:03x}"
            if candidate not in occupied:
                return candidate
        fallback = f"robot-{rand.randint(0, 0xFFF):03x}"
        if fallback in occupied:
            return f"robot-{(rand.randint(0, 0xFFF) ^ int(time.time())) & 0xFFF:03x}"
        return fallback

    def normalize_hostname(self, raw: str) -> str:
        value = str(raw or "").strip().lower()
        if not value:
            raise ValueError("Avahi hostname cannot be empty")
        if len(value) > 63:
            raise ValueError("Avahi hostname is too long")
        if not self._hostname_re.fullmatch(value):
            raise ValueError("Avahi hostname must contain only lowercase letters, digits, and hyphens")
        return value

    def write_hostname(self, hostname: str, sudo_password: Optional[str] = None) -> None:
        normalized = self.normalize_hostname(hostname)
        current_text = self._read_config_text(sudo_password=sudo_password)
        updated_text = self._upsert_server_hostname(current_text, normalized)

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(updated_text)

        try:
            self._run_privileged(
                ["install", "-m", "644", str(tmp_path), str(self._config_path)],
                sudo_password=sudo_password,
            )
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _upsert_server_hostname(self, config_text: str, hostname: str) -> str:
        '''Returns updated config text with the specified host-name set in the [server] section.'''
        text = config_text or ""
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.splitlines(keepends=True)
        section_re = re.compile(r"^\s*\[([^\]]+)\]\s*(?:[;#].*)?$")
        host_re = re.compile(r"^(\s*)host-name\s*[=:].*$", re.IGNORECASE)

        if not lines:
            return f"[server]{newline}host-name={hostname}{newline}"

        server_start = -1
        server_end = len(lines)

        for idx, line in enumerate(lines):
            match = section_re.match(line.strip("\r\n"))
            if not match:
                continue
            section_name = match.group(1).strip().lower()
            if section_name == "server":
                server_start = idx
                for next_idx in range(idx + 1, len(lines)):
                    if section_re.match(lines[next_idx].strip("\r\n")):
                        server_end = next_idx
                        break
                break

        if server_start >= 0:
            for idx in range(server_start + 1, server_end):
                match = host_re.match(lines[idx].strip("\r\n"))
                if match:
                    indent = match.group(1)
                    line_newline = ""
                    if lines[idx].endswith("\r\n"):
                        line_newline = "\r\n"
                    elif lines[idx].endswith("\n"):
                        line_newline = "\n"
                    lines[idx] = f"{indent}host-name={hostname}{line_newline}"
                    return "".join(lines)

            insert_newline = ""
            if lines[server_start].endswith("\r\n"):
                insert_newline = "\r\n"
            elif lines[server_start].endswith("\n"):
                insert_newline = "\n"
            else:
                insert_newline = newline
                lines[server_start] = f"{lines[server_start]}{insert_newline}"
            lines.insert(server_start + 1, f"host-name={hostname}{insert_newline}")
            return "".join(lines)

        if lines and not (lines[-1].endswith("\n") or lines[-1].endswith("\r\n")):
            lines[-1] = f"{lines[-1]}{newline}"
        lines.append(f"[server]{newline}")
        lines.append(f"host-name={hostname}{newline}")
        return "".join(lines)

    def restart(self, sudo_password: Optional[str] = None) -> None:
        self._run_privileged(["systemctl", "restart", "avahi-daemon.service"], sudo_password=sudo_password)

    def write_and_restart(self, hostname: str, sudo_password: Optional[str] = None) -> None:
        self.write_hostname(hostname, sudo_password=sudo_password)
        self.restart(sudo_password=sudo_password)

    def _read_config_text(self, sudo_password: Optional[str] = None) -> str:
        if self._config_path.exists():
            try:
                if os.geteuid() == 0:
                    return self._config_path.read_text(encoding="utf-8")
                result = subprocess.run(
                    ["sudo", "-n", "cat", str(self._config_path)],
                    text=True,
                    capture_output=True,
                    check=True,
                )
                return result.stdout
            except (OSError, subprocess.CalledProcessError):
                pass

        if os.geteuid() == 0:
            return "[server]\n"

        if sudo_password:
            try:
                result = subprocess.run(
                    ["sudo", "-S", "-p", "", "cat", str(self._config_path)],
                    input=f"{sudo_password}\n",
                    text=True,
                    capture_output=True,
                    check=True,
                )
                return result.stdout
            except (OSError, subprocess.CalledProcessError):
                return "[server]\n"

        return "[server]\n"

    def _run_privileged(
        self,
        args: List[str],
        *,
        sudo_password: Optional[str] = None,
    ) -> None:
        cmd = list(args)
        stdin_text: Optional[str] = None

        if os.geteuid() != 0:
            if sudo_password:
                cmd = ["sudo", "-S", "-p", "", *cmd]
                stdin_text = f"{sudo_password}\n"
            else:
                cmd = ["sudo", "-n", *cmd]

        try:
            subprocess.run(
                cmd,
                input=stdin_text,
                text=True,
                capture_output=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"Missing command: {cmd[0]}") from exc
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or str(exc)).strip()
            raise RuntimeError(message or "Failed to update Avahi service") from exc
