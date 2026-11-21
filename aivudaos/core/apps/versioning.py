from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Iterator, List, Optional
from uuid import uuid4

from aivudaos.core.db.connection import db_conn
from aivudaos.core.errors import NotFoundError, PackageFormatError
from aivudaos.core.paths import APPS_DIR, APP_RUNTIME_DATA_DIR


_active_link_lock = Lock()


def _replace_active_link(link: Path, target: str) -> None:
    pending = link.with_name(".active-" + uuid4().hex)
    pending.symlink_to(target)
    try:
        pending.replace(link)
    except BaseException:
        pending.unlink(missing_ok=True)
        raise


class VersioningService:
    """Manages multi-version installations and active version symlinks."""

    def app_dir(self, app_id: str) -> Path:
        return APPS_DIR / app_id

    def version_dir(self, app_id: str, version: str) -> Path:
        return APPS_DIR / app_id / "versions" / version

    def active_link(self, app_id: str) -> Path:
        return APPS_DIR / app_id / "active"

    def app_runtime_data_dir(self, app_id: str) -> Path:
        return APP_RUNTIME_DATA_DIR / app_id

    def version_runtime_data_dir(self, app_id: str, version: str) -> Path:
        return self.app_runtime_data_dir(app_id) / version

    def ensure_version_runtime_data_dir(self, app_id: str, version: str) -> Path:
        runtime_dir = self.version_runtime_data_dir(app_id, version)
        runtime_dir.mkdir(parents=True, exist_ok=True)
        return runtime_dir

    def active_version(self, app_id: str) -> Optional[str]:
        """Read the active version from the symlink. Returns None if no symlink."""
        link = self.active_link(app_id)
        if not link.is_symlink():
            return None
        target = os.readlink(str(link))
        # target is relative: "versions/1.2.3" -> extract "1.2.3"
        return Path(target).name

    def active_install_path(self, app_id: str) -> Optional[Path]:
        """Return the resolved path of the active version, or None."""
        link = self.active_link(app_id)
        if not link.exists():
            return None
        return link.resolve()

    def list_versions(self, app_id: str) -> List[str]:
        """List all installed versions for an app from the database."""
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT version FROM app_installation WHERE app_id = ? ORDER BY installed_at DESC",
                (app_id,),
            ).fetchall()
        return [row["version"] for row in rows]

    def _active_target(self, app_id: str, version: str) -> str:
        directory = self.version_dir(app_id, version)
        if not directory.exists():
            raise NotFoundError(f"Version {version} is not installed for {app_id}")
        return str(directory.relative_to(self.app_dir(app_id)))

    def activate_version(self, app_id: str, version: str) -> None:
        """Point the 'active' symlink to the specified version."""
        with _active_link_lock:
            _replace_active_link(self.active_link(app_id), self._active_target(app_id, version))

    @contextmanager
    def activate_candidate(self, app_id: str, version: str) -> Iterator[None]:
        """Restore the previous target if publication fails and this link is still active."""
        link = self.active_link(app_id)
        with _active_link_lock:
            if link.exists() and not link.is_symlink():
                raise PackageFormatError(f"Active version is not a symlink: {link}")
            previous = os.readlink(link) if link.is_symlink() else None
            candidate = self._active_target(app_id, version)
            _replace_active_link(link, candidate)
        try:
            yield
        except BaseException:
            with _active_link_lock:
                if candidate != previous and link.is_symlink() and os.readlink(link) == candidate:
                    if previous is None:
                        link.unlink()
                    else:
                        _replace_active_link(link, previous)
            raise

    def prepare_version_dir(self, app_id: str, version: str) -> Path:
        """Create and return the version directory for installation."""
        ver_dir = self.version_dir(app_id, version)
        if ver_dir.exists():
            shutil.rmtree(ver_dir)
        runtime_dir = self.version_runtime_data_dir(app_id, version)
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir, ignore_errors=True)
        ver_dir.mkdir(parents=True, exist_ok=True)
        return ver_dir

    def remove_version(self, app_id: str, version: str) -> None:
        """Remove a specific version directory and DB record."""
        ver_dir = self.version_dir(app_id, version)
        if ver_dir.exists():
            shutil.rmtree(ver_dir, ignore_errors=True)
        runtime_dir = self.version_runtime_data_dir(app_id, version)
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir, ignore_errors=True)

        # If active pointed to this version, remove symlink
        if self.active_version(app_id) == version:
            link = self.active_link(app_id)
            if link.is_symlink():
                link.unlink()

        with db_conn() as conn:
            conn.execute(
                "DELETE FROM app_installation WHERE app_id = ? AND version = ?",
                (app_id, version),
            )
            conn.commit()

    def remove_app_entirely(self, app_id: str) -> None:
        """Remove all versions and the app directory."""
        app_dir = self.app_dir(app_id)
        if app_dir.exists():
            shutil.rmtree(app_dir, ignore_errors=True)

        runtime_app_dir = self.app_runtime_data_dir(app_id)
        if runtime_app_dir.exists():
            shutil.rmtree(runtime_app_dir, ignore_errors=True)

        with db_conn() as conn:
            conn.execute("DELETE FROM app_installation WHERE app_id = ?", (app_id,))
            conn.commit()
