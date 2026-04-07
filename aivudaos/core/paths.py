from __future__ import annotations

import os
import shutil
from pathlib import Path

import yaml

from aivudaos.core.config.avahi import AvahiService
import aivudaos


def _source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _package_resources_root() -> Path:
    from_env = os.environ.get("AIVUDAOS_PACKAGE_ROOT", "").strip()
    if from_env:
        candidate = Path(from_env).expanduser().resolve()
        if (candidate / "caddy" / "Caddyfile_template").exists():
            return candidate

    packaged_root = (Path(aivudaos.__file__).resolve().parent / "resources").resolve()
    return packaged_root


SOURCE_ROOT = _source_root().resolve()
PACKAGE_RESOURCES_ROOT = _package_resources_root()
CADDYFILE_TEMPLATE_PATH = PACKAGE_RESOURCES_ROOT / "caddy" / "Caddyfile_template"
SHELL_HELPERS_DIR = PACKAGE_RESOURCES_ROOT / "shell_helpers"
SHELL_HELPERS_ENV_DIR = SHELL_HELPERS_DIR / "env"
UI_DIST_DIR = PACKAGE_RESOURCES_ROOT / "ui" / "dist"
UI_DEFAULT_ICON_PATH = UI_DIST_DIR / "app-default-icon.png"
UI_FALLBACK_ICON_PATH = UI_DIST_DIR / "aivuda_icon.png"


def _runtime_root() -> Path:
    from_env = os.environ.get("AIVUDAOS_WS_ROOT", "").strip()
    if from_env:
        return Path(from_env).expanduser().resolve()
    return (Path.home() / "aivudaOS_ws").resolve()


RUNTIME_ROOT = _runtime_root()
CADDY_BIN_PATH = RUNTIME_ROOT / ".tools" / "caddy" / "caddy"

# Config files (YAML)
CONFIG_DIR = RUNTIME_ROOT / "config"
CADDYFILE_PATH = CONFIG_DIR / "Caddyfile"
OS_CONFIG_PATH = CONFIG_DIR / "os.yaml"
SYS_CONFIG_PATH = CONFIG_DIR / "sys.yaml"
USERS_CONFIG_PATH = CONFIG_DIR / "users.yaml"
APP_CONFIG_DIR = CONFIG_DIR / "apps"
APP_CADDY_GEN_DIR = CONFIG_DIR / "caddy"
MAGNET_CONFIG_PATH = CONFIG_DIR / "magnets.yaml"

# App installations (multi-version with symlinks)
APPS_DIR = RUNTIME_ROOT / "apps"

# Runtime data
DATA_DIR = RUNTIME_ROOT / "data"
APP_RUNTIME_DATA_DIR = DATA_DIR / "runtime"
SYSTEMD_RUNTIME_DIR = APP_RUNTIME_DATA_DIR / "systemd"
DB_PATH = DATA_DIR / "aivuda.db"
# ARTIFACT_CACHE_DIR = DATA_DIR / "artifact-cache"
UPLOAD_TEMP_DIR = DATA_DIR / "uploads"
SESSIONS_DIR = DATA_DIR / "sessions"
LOG_DIR = DATA_DIR / "logs"
OS_LOG_DIR = LOG_DIR / "os"
APP_LOG_DIR = LOG_DIR / "apps"

DEFAULT_OS_CONFIG: dict[str, object] = {
    "runtime_process_manager": "auto",
    "runtime_systemd_scope": "user",
}

DEFAULT_SYS_CONFIG: dict[str, object] = {
    "sys": {
        "role": {
            "id": 1,
        }
    }
}

DEFAULT_USERS_CONFIG: dict[str, object] = {
    "users": [
        {
            "username": "admin",
            "password_hash": "$2b$12$Zsx8FX3em7.8TZOPEuwIA.HLnU6rqpW8aRd2naIt.psx1Eo8PiTEa",
            "role": "admin",
        }
    ]
}

DEFAULT_MAGNETS_CONFIG: dict[str, object] = {
    "_version": 0,
    "_updated_at": None,
    "_updated_by": "system",
    "groups": [],
    "conflicts": [],
}


def ensure_dirs() -> None:
    """Create all required runtime directories and bootstrap default configs."""
    for d in [
        RUNTIME_ROOT,
        CONFIG_DIR,
        APP_CONFIG_DIR,
        APP_CADDY_GEN_DIR,
        APPS_DIR,
        DATA_DIR,
        APP_RUNTIME_DATA_DIR,
        SYSTEMD_RUNTIME_DIR,
        # ARTIFACT_CACHE_DIR, 
        UPLOAD_TEMP_DIR,
        SESSIONS_DIR,
        LOG_DIR,
        OS_LOG_DIR,
        APP_LOG_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)

    _ensure_default_runtime_files()


def _ensure_default_runtime_files() -> None:
    avahi = AvahiService()
    os_raw = {}
    if OS_CONFIG_PATH.exists():
        loaded = yaml.safe_load(OS_CONFIG_PATH.read_text("utf-8")) or {}
        if isinstance(loaded, dict):
            os_raw = dict(loaded)

    if not isinstance(os_raw, dict):
        os_raw = {}

    changed = False
    created_avahi = False

    if "_version" not in os_raw:
        os_raw["_version"] = 1
        changed = True
    if "_updated_at" not in os_raw:
        os_raw["_updated_at"] = None
        changed = True
    if "_updated_by" not in os_raw:
        os_raw["_updated_by"] = "system"
        changed = True

    for key, default_value in DEFAULT_OS_CONFIG.items():
        if key not in os_raw:
            os_raw[key] = default_value
            changed = True

    if "avahi_hostname" not in os_raw:
        generated = avahi.generate_hostname(existing={str(os_raw.get("avahi_hostname") or "").strip().lower()})
        os_raw["avahi_hostname"] = generated
        created_avahi = True
        changed = True

    if changed or (not OS_CONFIG_PATH.exists()):
        OS_CONFIG_PATH.write_text(
            yaml.dump(os_raw, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

    if created_avahi:
        try:
            avahi.write_and_restart(str(os_raw.get("avahi_hostname") or ""))
        except Exception:
            pass

    if not USERS_CONFIG_PATH.exists():
        USERS_CONFIG_PATH.write_text(
            yaml.dump(DEFAULT_USERS_CONFIG, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

    if not SYS_CONFIG_PATH.exists():
        SYS_CONFIG_PATH.write_text(
            yaml.dump(
                {
                    "_version": 1,
                    "_updated_at": None,
                    "_updated_by": "system",
                    **DEFAULT_SYS_CONFIG,
                },
                default_flow_style=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

    if not MAGNET_CONFIG_PATH.exists():
        MAGNET_CONFIG_PATH.write_text(
            yaml.dump(DEFAULT_MAGNETS_CONFIG, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

    if not CADDYFILE_PATH.exists() and CADDYFILE_TEMPLATE_PATH.exists():
        shutil.copy2(CADDYFILE_TEMPLATE_PATH, CADDYFILE_PATH)
    
    import aivudaos.core.config.caddy_runtime as caddy_runtime
    caddy_service = caddy_runtime.CaddyRuntimeService()
    caddy_service.sync_https_hostname(str(os_raw.get("avahi_hostname") or ""))
    caddy_service.reload_if_running()
