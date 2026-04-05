from __future__ import annotations

from functools import lru_cache

from aivudaos.core.apps.installer import InstallerService
from aivudaos.core.apps.magnet import MagnetService
from aivudaos.core.apps.operations import AppOperationManager
from aivudaos.core.apps.runtime import RuntimeService
from aivudaos.core.apps.versioning import VersioningService
from aivudaos.core.auth.relogin import ReloginService
from aivudaos.core.auth.service import AuthService
from aivudaos.core.config.apt_sources import AptSourcesService
from aivudaos.core.config.avahi import AvahiService
from aivudaos.core.config.service import ConfigService
from aivudaos.core.config.sudo_nopasswd import SudoNopasswdService


@lru_cache
def get_avahi_service() -> AvahiService:
    return AvahiService()


@lru_cache
def get_config_service() -> ConfigService:
    return ConfigService(avahi_service=get_avahi_service())


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


@lru_cache
def get_relogin_service() -> ReloginService:
    return ReloginService()


@lru_cache
def get_apt_sources_service() -> AptSourcesService:
    return AptSourcesService()

