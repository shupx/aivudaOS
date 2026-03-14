from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .filelock import get_lock


class AptSourcesError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code or "APT_SOURCES_ERROR")
        self.message = str(message or "APT sources operation failed")


@dataclass
class AptBackupItem:
    backup_id: str
    path: str
    created_at: str


class AptSourcesService:
    _COMMENT_RE = re.compile(r"^\s*#")
    _TZ_SHANGHAI = timezone(timedelta(hours=8))

    def __init__(
        self,
        *,
        sources_path: Path | None = None,
        backup_dir: Path | None = None,
    ) -> None:
        self._sources_path = sources_path or Path("/etc/apt/sources.list")
        self._backup_dir = backup_dir or Path("/var/backups/aivudaos/apt-sources")

    def read_sources(self) -> dict[str, object]:
        content = self._read_text_with_privilege(self._sources_path)
        line_count, comment_count = self._summarize_content(content)
        backups = self.list_backups()
        return {
            "ok": True,
            "path": str(self._sources_path),
            "content": content,
            "line_count": line_count,
            "comment_line_count": comment_count,
            "backup_count": len(backups),
            "latest_backup": backups[0] if backups else None,
        }

    def list_backups(self) -> list[dict[str, str]]:
        if not self._backup_dir.exists() and os.geteuid() != 0:
            try:
                result = subprocess.run(
                    ["sudo", "-n", "ls", "-1", str(self._backup_dir)],
                    text=True,
                    capture_output=True,
                    check=True,
                )
                names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
                return self._build_backup_items_from_names(names)
            except (FileNotFoundError, subprocess.CalledProcessError):
                return []

        if not self._backup_dir.exists():
            return []

        names = [path.name for path in sorted(self._backup_dir.glob("sources.list.*.bak"), reverse=True) if path.is_file()]
        return self._build_backup_items_from_names(names)

    def write_sources(
        self,
        content: str,
        *,
        sudo_password: str | None = None,
    ) -> dict[str, object]:
        text = str(content or "")
        lock = get_lock(self._sources_path)
        with lock:
            backup_path = self._create_backup(sudo_password=sudo_password)
            self._write_text_with_privilege(self._sources_path, text, sudo_password=sudo_password)
            apt_update_output = self._run_apt_update(sudo_password=sudo_password)

        line_count, comment_count = self._summarize_content(text)
        return {
            "ok": True,
            "path": str(self._sources_path),
            "line_count": line_count,
            "comment_line_count": comment_count,
            "backup": {
                "backup_id": self._backup_id_from_path(backup_path),
                "path": str(backup_path),
                "created_at": self._iso_from_backup_id(self._backup_id_from_path(backup_path)),
            },
            "apt_update": {
                "ok": True,
                "output": apt_update_output,
            },
        }

    def restore_backup(
        self,
        backup_id: str,
        *,
        sudo_password: str | None = None,
    ) -> dict[str, object]:
        target_id = str(backup_id or "").strip()
        if not target_id:
            raise AptSourcesError("BACKUP_ID_REQUIRED", "Backup id is required")

        backup_path = self._resolve_backup_path(target_id)
        lock = get_lock(self._sources_path)
        with lock:
            current_backup = self._create_backup(sudo_password=sudo_password)
            content = self._read_text_with_privilege(backup_path)
            self._write_text_with_privilege(self._sources_path, content, sudo_password=sudo_password)
            apt_update_output = self._run_apt_update(sudo_password=sudo_password)

        line_count, comment_count = self._summarize_content(content)
        return {
            "ok": True,
            "path": str(self._sources_path),
            "restored_from": {
                "backup_id": target_id,
                "path": str(backup_path),
                "created_at": self._iso_from_backup_id(target_id),
            },
            "backup": {
                "backup_id": self._backup_id_from_path(current_backup),
                "path": str(current_backup),
                "created_at": self._iso_from_backup_id(self._backup_id_from_path(current_backup)),
            },
            "line_count": line_count,
            "comment_line_count": comment_count,
            "apt_update": {
                "ok": True,
                "output": apt_update_output,
            },
        }

    def _create_backup(self, *, sudo_password: str | None = None) -> Path:
        self._ensure_backup_dir(sudo_password=sudo_password)
        backup_id = datetime.now(self._TZ_SHANGHAI).strftime("%Y%m%dT%H%M%S%f%z")
        backup_path = self._backup_dir / f"sources.list.{backup_id}.bak"

        content = self._read_text_with_privilege(self._sources_path, sudo_password=sudo_password)
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            self._run_privileged(
                ["install", "-m", "640", str(tmp_path), str(backup_path)],
                sudo_password=sudo_password,
            )
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

        return backup_path

    def _write_text_with_privilege(self, path: Path, content: str, *, sudo_password: str | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            self._run_privileged(["install", "-m", "644", str(tmp_path), str(path)], sudo_password=sudo_password)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _read_text_with_privilege(self, path: Path, *, sudo_password: str | None = None) -> str:
        if path.exists():
            if os.geteuid() == 0:
                try:
                    return path.read_text(encoding="utf-8")
                except OSError as exc:
                    raise AptSourcesError("READ_FAILED", f"Failed to read {path}: {exc}") from exc

            try:
                result = subprocess.run(
                    ["sudo", "-n", "cat", str(path)],
                    text=True,
                    capture_output=True,
                    check=True,
                )
                return result.stdout
            except subprocess.CalledProcessError:
                pass
            except FileNotFoundError as exc:
                raise AptSourcesError("MISSING_COMMAND", f"Missing command: {exc.filename}") from exc

            if sudo_password:
                try:
                    result = subprocess.run(
                        ["sudo", "-S", "-p", "", "cat", str(path)],
                        input=f"{sudo_password}\n",
                        text=True,
                        capture_output=True,
                        check=True,
                    )
                    return result.stdout
                except subprocess.CalledProcessError as exc:
                    message = (exc.stderr or exc.stdout or str(exc)).strip()
                    raise AptSourcesError("READ_FAILED", message or f"Failed to read {path}") from exc
                except FileNotFoundError as exc:
                    raise AptSourcesError("MISSING_COMMAND", f"Missing command: {exc.filename}") from exc

            raise AptSourcesError("SUDO_PASSWORD_REQUIRED", "Sudo password is required")

        return ""

    def _run_apt_update(self, *, sudo_password: str | None = None) -> str:
        cmd = ["apt", "update"]
        run_cmd = cmd

        if os.geteuid() != 0:
            run_cmd = ["sudo", "-n", *cmd]

        try:
            result = subprocess.run(
                run_cmd,
                text=True,
                capture_output=True,
                check=True,
            )
            return self._trim_output(result.stdout or result.stderr)
        except subprocess.CalledProcessError as exc:
            if os.geteuid() != 0 and sudo_password:
                try:
                    result = subprocess.run(
                        ["sudo", "-S", "-p", "", *cmd],
                        input=f"{sudo_password}\n",
                        text=True,
                        capture_output=True,
                        check=True,
                    )
                    return self._trim_output(result.stdout or result.stderr)
                except subprocess.CalledProcessError as inner:
                    message = (inner.stderr or inner.stdout or str(inner)).strip()
                    raise AptSourcesError("APT_UPDATE_FAILED", message or "Failed to run apt update") from inner

            if os.geteuid() != 0 and not sudo_password:
                raise AptSourcesError("SUDO_PASSWORD_REQUIRED", "Sudo password is required") from exc

            message = (exc.stderr or exc.stdout or str(exc)).strip()
            raise AptSourcesError("APT_UPDATE_FAILED", message or "Failed to run apt update") from exc
        except FileNotFoundError as exc:
            raise AptSourcesError("MISSING_COMMAND", f"Missing command: {exc.filename}") from exc

    def _run_privileged(self, args: list[str], *, sudo_password: str | None = None) -> None:
        cmd = list(args)
        stdin_text: str | None = None

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
            raise AptSourcesError("MISSING_COMMAND", f"Missing command: {exc.filename}") from exc
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or str(exc)).strip()
            if os.geteuid() != 0 and not sudo_password:
                raise AptSourcesError("SUDO_PASSWORD_REQUIRED", "Sudo password is required") from exc
            raise AptSourcesError("WRITE_FAILED", message or "Failed to update apt sources") from exc

    def _resolve_backup_path(self, backup_id: str) -> Path:
        candidate = self._backup_dir / f"sources.list.{backup_id}.bak"
        if not candidate.exists() or not candidate.is_file():
            raise AptSourcesError("BACKUP_NOT_FOUND", f"Backup not found: {backup_id}")
        return candidate

    def _ensure_backup_dir(self, *, sudo_password: str | None = None) -> None:
        if self._backup_dir.exists():
            return

        try:
            if os.geteuid() == 0:
                self._backup_dir.mkdir(parents=True, exist_ok=True)
            else:
                self._run_privileged(["mkdir", "-p", str(self._backup_dir)], sudo_password=sudo_password)
            self._run_privileged(["chmod", "755", str(self._backup_dir)], sudo_password=sudo_password)
        except OSError as exc:
            raise AptSourcesError("BACKUP_DIR_FAILED", f"Failed to prepare backup directory: {exc}") from exc

    def _backup_id_from_path(self, path: Path | None) -> str:
        if not path:
            return ""
        name = path.name
        if not name.startswith("sources.list.") or not name.endswith(".bak"):
            return ""
        return name[len("sources.list."):-len(".bak")]

    def _iso_from_backup_id(self, backup_id: str) -> str:
        value = str(backup_id or "").strip()
        if not value:
            return ""
        try:
            if value.endswith("Z"):
                parsed = datetime.strptime(value, "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)
            else:
                parsed = datetime.strptime(value, "%Y%m%dT%H%M%S%f%z")
            return parsed.isoformat()
        except ValueError:
            return ""

    def _summarize_content(self, content: str) -> tuple[int, int]:
        text = str(content or "")
        lines = text.splitlines()
        comment_count = sum(1 for line in lines if self._COMMENT_RE.match(line))
        return len(lines), comment_count

    def _build_backup_items_from_names(self, names: list[str]) -> list[dict[str, str]]:
        items: list[AptBackupItem] = []
        for name in sorted(names, reverse=True):
            backup_id = self._backup_id_from_path(Path(name))
            if not backup_id:
                continue
            path = self._backup_dir / name
            items.append(
                AptBackupItem(
                    backup_id=backup_id,
                    path=str(path),
                    created_at=self._iso_from_backup_id(backup_id),
                )
            )

        return [
            {
                "backup_id": item.backup_id,
                "path": item.path,
                "created_at": item.created_at,
            }
            for item in items
        ]

    def _trim_output(self, text: str) -> str:
        raw = str(text or "").strip()
        if len(raw) <= 6000:
            return raw
        return f"{raw[:6000]}\n... (truncated)"
