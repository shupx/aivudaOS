from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml

from core.config.filelock import atomic_write_text, get_lock
from core.config.models import UserRecord, UsersConfig, VersionedConfig
from core.errors import ConfigVersionConflictError
from core.paths import APP_CONFIG_DIR, OS_CONFIG_PATH, USERS_CONFIG_PATH


class ConfigService:
    """File-based YAML configuration management with optimistic locking."""

    # --- OS Config ---

    def get_os_config(self) -> VersionedConfig:
        return self._read_versioned(OS_CONFIG_PATH)

    def update_os_config(
        self, data: dict[str, Any], expected_version: int, username: str
    ) -> VersionedConfig:
        return self._write_versioned(OS_CONFIG_PATH, data, expected_version, username)

    def get_os_setting(self, key: str, default: Any = None) -> Any:
        cfg = self.get_os_config()
        return cfg.data.get(key, default)

    # --- Per-App Config ---

    def app_config_path(self, app_id: str) -> Path:
        return APP_CONFIG_DIR / f"{app_id}.yaml"

    def get_app_config(self, app_id: str) -> VersionedConfig:
        path = self.app_config_path(app_id)
        if not path.exists():
            return VersionedConfig(data={}, version=0)
        return self._read_versioned(path)

    def update_app_config(
        self, app_id: str, data: dict[str, Any], expected_version: int
    ) -> VersionedConfig:
        return self._write_versioned(
            self.app_config_path(app_id), data, expected_version, updated_by="system"
        )

    def init_app_config(self, app_id: str, default_data: dict[str, Any]) -> None:
        """Create app config if it does not exist yet."""
        path = self.app_config_path(app_id)
        if path.exists():
            return
        self._write_versioned(path, default_data, expected_version=0, updated_by="system")

    def delete_app_config(self, app_id: str) -> None:
        path = self.app_config_path(app_id)
        if path.exists():
            path.unlink()

    # --- Users ---

    def get_users(self) -> UsersConfig:
        if not USERS_CONFIG_PATH.exists():
            return UsersConfig(users=[])
        lock = get_lock(USERS_CONFIG_PATH)
        with lock:
            raw = yaml.safe_load(USERS_CONFIG_PATH.read_text("utf-8")) or {}
        users_raw = raw.get("users", [])
        return UsersConfig(users=[UserRecord(**u) for u in users_raw])

    def save_users(self, users_config: UsersConfig) -> None:
        lock = get_lock(USERS_CONFIG_PATH)
        with lock:
            raw = {
                "users": [
                    {
                        "username": u.username,
                        "password_hash": u.password_hash,
                        "role": u.role,
                    }
                    for u in users_config.users
                ]
            }
            atomic_write_text(
                USERS_CONFIG_PATH,
                yaml.dump(raw, default_flow_style=False, allow_unicode=True),
            )

    def find_user(self, username: str) -> UserRecord | None:
        users = self.get_users()
        for u in users.users:
            if u.username == username:
                return u
        return None

    # --- Internal helpers ---

    def _read_versioned(self, path: Path) -> VersionedConfig:
        lock = get_lock(path)
        with lock:
            if not path.exists():
                return VersionedConfig(data={}, version=0)
            raw = yaml.safe_load(path.read_text("utf-8")) or {}
        version = raw.pop("_version", 0)
        updated_at = raw.pop("_updated_at", None)
        updated_by = raw.pop("_updated_by", None)
        return VersionedConfig(
            data=raw, version=version, updated_at=updated_at, updated_by=updated_by
        )

    def _write_versioned(
        self,
        path: Path,
        data: dict[str, Any],
        expected_version: int,
        updated_by: str,
    ) -> VersionedConfig:
        lock = get_lock(path)
        with lock:
            if path.exists():
                current_raw = yaml.safe_load(path.read_text("utf-8")) or {}
                current_version = current_raw.get("_version", 0)
            else:
                current_version = 0

            if expected_version != current_version:
                raise ConfigVersionConflictError(
                    f"Expected version {expected_version}, current is {current_version}"
                )

            new_version = current_version + 1
            now = int(time.time())
            to_write = {
                "_version": new_version,
                "_updated_at": now,
                "_updated_by": updated_by,
                **data,
            }
            atomic_write_text(
                path,
                yaml.dump(to_write, default_flow_style=False, allow_unicode=True),
            )

        return VersionedConfig(
            data=data, version=new_version, updated_at=now, updated_by=updated_by
        )
