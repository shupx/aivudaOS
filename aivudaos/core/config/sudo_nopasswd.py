from __future__ import annotations

import getpass
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional


class SudoNopasswdService:
    def __init__(self, sudoers_dir: Optional[Path] = None) -> None:
        self._sudoers_dir = sudoers_dir or Path('/etc/sudoers.d')
        self._username_re = re.compile(r'^[a-z_][a-z0-9_-]*[$]?$', re.IGNORECASE)

    def resolve_target_user(self) -> str:
        candidate = (
            str(os.environ.get('AIVUDAOS_SUDO_TARGET_USER') or '').strip()
            or str(os.environ.get('SUDO_USER') or '').strip()
            or str(getpass.getuser() or '').strip()
        )
        if not candidate:
            raise RuntimeError('Cannot determine target system user')
        if not self._username_re.fullmatch(candidate):
            raise ValueError(f'Invalid system username: {candidate}')
        return candidate

    def get_status(self) -> Dict[str, object]:
        username = self.resolve_target_user()
        return {
            'username': username,
            'enabled': self._is_passwordless_sudo_enabled(username),
        }

    def set_enabled(self, enabled: bool, sudo_password: Optional[str] = None) -> Dict[str, object]:
        username = self.resolve_target_user()
        self._set_passwordless_sudo(username, bool(enabled), sudo_password)
        return {
            'username': username,
            'enabled': self._is_passwordless_sudo_enabled(username),
        }

    def _sudoers_file_for_user(self, username: str) -> Path:
        return self._sudoers_dir / username

    def _is_passwordless_sudo_enabled(self, username: str) -> bool:
        path = self._sudoers_file_for_user(username)
        try:
            if path.exists() and path.is_file():
                content = path.read_text(encoding='utf-8', errors='ignore')
            else:
                return False
        except PermissionError:
            content = self._read_sudoers_file_via_nopasswd_sudo(path)
            if content is None:
                return False
        except OSError:
            return False
        expected = f'{username} ALL=(ALL) NOPASSWD:ALL'
        return expected in content

    @staticmethod
    def _read_sudoers_file_via_nopasswd_sudo(path: Path) -> Optional[str]:
        try:
            result = subprocess.run(
                ['sudo', '-n', 'cat', str(path)],
                text=True,
                capture_output=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return result.stdout

    def _run_privileged(
        self,
        args: List[str],
        *,
        sudo_password: Optional[str] = None,
        input_text: Optional[str] = None,
    ) -> None:
        cmd = list(args)
        stdin_text = input_text
        if os.geteuid() != 0:
            clean_password = str(sudo_password or '')
            if not clean_password:
                raise RuntimeError('Sudo password is required')
            cmd = ['sudo', '-S', '-p', '', *cmd]
            stdin_text = f'{clean_password}\n{input_text or ""}'
        try:
            subprocess.run(
                cmd,
                input=stdin_text,
                text=True,
                capture_output=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f'Missing command: {cmd[0]}') from exc
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or str(exc)).strip()
            raise RuntimeError(message or 'Failed to update sudoers') from exc

    def _set_passwordless_sudo(self, username: str, enabled: bool, sudo_password: Optional[str] = None) -> None:
        sudoers_file = self._sudoers_file_for_user(username)
        if not enabled:
            self._run_privileged(['rm', '-f', str(sudoers_file)], sudo_password=sudo_password)
            return

        self._sudoers_dir.mkdir(parents=True, exist_ok=True)
        line = f'{username} ALL=(ALL) NOPASSWD:ALL\n'
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as tmp:
                tmp.write(line)
                tmp_path = tmp.name

            os.chmod(tmp_path, 0o440)
            self._run_privileged(['visudo', '-cf', tmp_path], sudo_password=sudo_password)
            self._run_privileged(['install', '-m', '440', tmp_path, str(sudoers_file)], sudo_password=sudo_password)
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
