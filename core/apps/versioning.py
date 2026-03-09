from __future__ import annotations

import os
import shutil
from pathlib import Path

from core.db.connection import db_conn
from core.errors import NotFoundError
from core.paths import APPS_DIR, APP_RUNTIME_DATA_DIR


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

    def active_version(self, app_id: str) -> str | None:
        """Read the active version from the symlink. Returns None if no symlink."""
        link = self.active_link(app_id)
        if not link.is_symlink():
            return None
        target = os.readlink(str(link))
        # target is relative: "versions/1.2.3" -> extract "1.2.3"
        return Path(target).name

    def active_install_path(self, app_id: str) -> Path | None:
        """Return the resolved path of the active version, or None."""
        link = self.active_link(app_id)
        if not link.exists():
            return None
        return link.resolve()

    def list_versions(self, app_id: str) -> list[str]:
        """List all installed versions for an app from the database."""
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT version FROM app_installation WHERE app_id = ? ORDER BY installed_at DESC",
                (app_id,),
            ).fetchall()
        return [row["version"] for row in rows]

    def activate_version(self, app_id: str, version: str) -> None:
        """Point the 'active' symlink to the specified version."""
        ver_dir = self.version_dir(app_id, version)
        if not ver_dir.exists():
            raise NotFoundError(f"Version {version} is not installed for {app_id}")

        link = self.active_link(app_id)
        relative_target = Path("versions") / version

        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(relative_target)

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
