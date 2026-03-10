from __future__ import annotations

from functools import lru_cache

from core.apps.installer import InstallerService
from core.apps.magnet import MagnetService
from core.apps.operations import AppOperationManager
from core.apps.runtime import RuntimeService
from core.apps.versioning import VersioningService
from core.auth.service import AuthService
from core.config.service import ConfigService
from core.config.sudo_nopasswd import SudoNopasswdService


@lru_cache
def get_config_service() -> ConfigService:
    return ConfigService()


@lru_cache
def get_auth_service() -> AuthService:
    return AuthService(get_config_service())


@lru_cache
def get_versioning_service() -> VersioningService:
    return VersioningService()


@lru_cache
def get_installer_service() -> InstallerService:
    return InstallerService(
        versioning=get_versioning_service(),
        config_service=get_config_service(),
        magnet_service=get_magnet_service(),
    )


@lru_cache
def get_runtime_service() -> RuntimeService:
    return RuntimeService(
        versioning=get_versioning_service(),
        config_service=get_config_service(),
        magnet_service=get_magnet_service(),
    )


@lru_cache
def get_magnet_service() -> MagnetService:
    return MagnetService(
        config_service=get_config_service(),
        versioning_service=get_versioning_service(),
    )


@lru_cache
def get_app_operation_manager() -> AppOperationManager:
    return AppOperationManager()


@lru_cache
def get_sudo_nopasswd_service() -> SudoNopasswdService:
    return SudoNopasswdService()

