from __future__ import annotations

import os
from functools import lru_cache

from core.apps.catalog import CatalogService
from core.apps.installer import InstallerService
from core.apps.runtime import RuntimeService
from core.apps.versioning import VersioningService
from core.auth.service import AuthService
from core.config.service import ConfigService


@lru_cache
def get_config_service() -> ConfigService:
    return ConfigService()


@lru_cache
def get_auth_service() -> AuthService:
    return AuthService(get_config_service())


@lru_cache
def get_catalog_service() -> CatalogService:
    cfg = get_config_service()
    repo_url = cfg.get_os_setting(
        "repo_url",
        os.environ.get("APP_REPO_URL", "http://127.0.0.1:9001/repo"),
    )
    return CatalogService(repo_url)


@lru_cache
def get_versioning_service() -> VersioningService:
    return VersioningService()


@lru_cache
def get_installer_service() -> InstallerService:
    return InstallerService(
        versioning=get_versioning_service(),
        config_service=get_config_service(),
        catalog=get_catalog_service(),
    )


@lru_cache
def get_runtime_service() -> RuntimeService:
    return RuntimeService(
        versioning=get_versioning_service(),
        config_service=get_config_service(),
    )

