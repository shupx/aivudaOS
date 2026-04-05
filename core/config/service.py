from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Optional

import yaml

from core.config.avahi import AvahiService
from core.config.caddy_runtime import CaddyRuntimeService
from core.config.filelock import atomic_write_text, get_lock
from core.config.models import UserRecord, UsersConfig, VersionedConfig
from core.errors import ConfigVersionConflictError
from core.paths import APP_CONFIG_DIR, OS_CONFIG_PATH, SYS_CONFIG_PATH, USERS_CONFIG_PATH


class ConfigService:
    """File-based YAML configuration management with optimistic locking."""

    def __init__(
        self,
        avahi_service: Optional[AvahiService] = None,
        caddy_service: Optional[CaddyRuntimeService] = None,
    ) -> None:
        self._avahi = avahi_service or AvahiService()
        self._caddy = caddy_service or CaddyRuntimeService()

    # --- OS Config ---

    def get_os_config(self) -> VersionedConfig:
        return self._read_versioned(OS_CONFIG_PATH)

    def update_os_config(
        self, data: dict[str, Any], expected_version: int, username: str
    ) -> VersionedConfig:
        normalized_data = dict(data)
        if "avahi_hostname" in normalized_data:
            normalized_data["avahi_hostname"] = self._avahi.normalize_hostname(
                str(normalized_data.get("avahi_hostname") or "")
            )

        previous = self.get_os_config()
        previous_hostname = str(previous.data.get("avahi_hostname") or "").strip().lower()

        updated = self._write_versioned(OS_CONFIG_PATH, normalized_data, expected_version, username)

        new_hostname = str(updated.data.get("avahi_hostname") or "").strip().lower()
        if new_hostname and new_hostname != previous_hostname:
            try:
                self._avahi.write_and_restart(new_hostname)
                caddy_changed = self._caddy.sync_https_hostname(new_hostname)
                if caddy_changed:
                    self._caddy.reload_if_running()
            except Exception as exc:
                rollback_error: Optional[Exception] = None
                try:
                    self._rollback_os_config_after_hostname_sync_failure(
                        previous_data=previous.data,
                        failed_version=updated.version,
                        updated_by=username,
                    )
                except Exception as rb_exc:
                    rollback_error = rb_exc

                if rollback_error is not None:
                    raise RuntimeError(
                        f"{exc}. Also failed to rollback avahi_hostname in OS config: {rollback_error}"
                    ) from exc
                raise

        return updated

    def get_os_setting(self, key: str, default: Any = None) -> Any:
        cfg = self.get_os_config()
        return cfg.data.get(key, default)

    # --- SYS Config (shared parameters) ---

    def get_sys_config(self) -> VersionedConfig:
        return self._read_versioned(SYS_CONFIG_PATH)

    def update_sys_config(
        self, data: dict[str, Any], expected_version: int, username: str
    ) -> VersionedConfig:
        return self._write_versioned(SYS_CONFIG_PATH, data, expected_version, username)

    # --- Per-App Config ---

    def app_config_path(self, app_id: str, app_version: str) -> Path:
        return APP_CONFIG_DIR / app_id / app_version / f"{app_version}.yaml"

    def app_default_config_path(self, app_id: str, app_version: str) -> Path:
        return APP_CONFIG_DIR / app_id / app_version / f"{app_version}_default.yaml"

    def app_legacy_config_path(self, app_id: str, app_version: str) -> Path:
        return APP_CONFIG_DIR / app_id / f"{app_version}.yaml"

    def get_app_config(self, app_id: str, app_version: str) -> VersionedConfig:
        self._migrate_legacy_app_config_if_needed(app_id, app_version)
        path = self._resolve_app_config_read_path(app_id, app_version)
        if path is None:
            return VersionedConfig(data={}, version=0)
        return self._read_versioned(path)

    def get_app_default_config(
        self,
        app_id: str,
        app_version: str,
        fallback: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        path = self.app_default_config_path(app_id, app_version)
        if not path.exists():
            return dict(fallback or {})

        cfg = self._read_versioned(path)
        if cfg.version <= 0 and not cfg.data:
            return dict(fallback or {})
        return dict(cfg.data)

    def update_app_config(
        self,
        app_id: str,
        app_version: str,
        data: dict[str, Any],
        expected_version: int,
        updated_by: str = "system",
    ) -> VersionedConfig:
        self._migrate_legacy_app_config_if_needed(app_id, app_version)
        path = self.app_config_path(app_id, app_version)
        path.parent.mkdir(parents=True, exist_ok=True)
        return self._write_versioned(
            path, data, expected_version, updated_by=updated_by
        )

    def init_app_config(
        self,
        app_id: str,
        app_version: str,
        default_data: dict[str, Any],
        *,
        overwrite_default: bool = False,
    ) -> None:
        """Initialize app config paths and keep active config intact when already present."""
        self._write_default_app_config(
            app_id,
            app_version,
            default_data,
            overwrite=overwrite_default,
        )

        path = self.app_config_path(app_id, app_version)
        legacy_path = self.app_legacy_config_path(app_id, app_version)
        if path.exists() or legacy_path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_versioned(path, default_data, expected_version=0, updated_by="system")

    def delete_app_config(self, app_id: str, app_version: Optional[str] = None) -> None:
        if app_version is None:
            app_dir = APP_CONFIG_DIR / app_id
            if app_dir.exists() and app_dir.is_dir():
                shutil.rmtree(app_dir)
            legacy_path = APP_CONFIG_DIR / f"{app_id}.yaml"
            if legacy_path.exists():
                legacy_path.unlink()
            return

        path = self.app_config_path(app_id, app_version)
        if path.exists():
            path.unlink()

        default_path = self.app_default_config_path(app_id, app_version)
        if default_path.exists():
            default_path.unlink()

        legacy_path = self.app_legacy_config_path(app_id, app_version)
        if legacy_path.exists():
            legacy_path.unlink()

        version_dir = APP_CONFIG_DIR / app_id / app_version
        if version_dir.exists() and version_dir.is_dir() and not any(version_dir.iterdir()):
            version_dir.rmdir()

        app_dir = APP_CONFIG_DIR / app_id
        if app_dir.exists() and app_dir.is_dir() and not any(app_dir.iterdir()):
            app_dir.rmdir()

    def restart_avahi_daemon(self) -> None:
        self._avahi.restart()

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

    def find_user(self, username: str) -> Optional[UserRecord]:
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

    def _rollback_os_config_after_hostname_sync_failure(
        self,
        *,
        previous_data: dict[str, Any],
        failed_version: int,
        updated_by: str,
    ) -> None:
        rollback_data = dict(previous_data)
        self._write_versioned(
            OS_CONFIG_PATH,
            rollback_data,
            expected_version=failed_version,
            updated_by=updated_by,
        )

    def _resolve_app_config_read_path(self, app_id: str, app_version: str) -> Optional[Path]:
        active = self.app_config_path(app_id, app_version)
        if active.exists():
            return active

        legacy = self.app_legacy_config_path(app_id, app_version)
        if legacy.exists():
            return legacy
        return None

    def _migrate_legacy_app_config_if_needed(self, app_id: str, app_version: str) -> None:
        active = self.app_config_path(app_id, app_version)
        legacy = self.app_legacy_config_path(app_id, app_version)
        if active.exists() or not legacy.exists():
            return

        active.parent.mkdir(parents=True, exist_ok=True)
        lock = get_lock(legacy)
        with lock:
            raw = legacy.read_text("utf-8")
        atomic_write_text(active, raw)

    def _write_default_app_config(
        self,
        app_id: str,
        app_version: str,
        default_data: dict[str, Any],
        *,
        overwrite: bool,
    ) -> None:
        path = self.app_default_config_path(app_id, app_version)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            return

        now = int(time.time())
        to_write = {
            "_version": 1,
            "_updated_at": now,
            "_updated_by": "system",
            **dict(default_data),
        }
        atomic_write_text(
            path,
            yaml.dump(to_write, default_flow_style=False, allow_unicode=True),
        )
