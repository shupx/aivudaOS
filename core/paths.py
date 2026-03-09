from __future__ import annotations

import os
from pathlib import Path

import yaml

# PROJECT_ROOT is the aivudaOS/ directory itself
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _runtime_root() -> Path:
    from_env = os.environ.get("AIVUDAOS_WS_ROOT", "").strip()
    if from_env:
        return Path(from_env).expanduser().resolve()
    return (Path.home() / "aivudaOS_ws").resolve()


RUNTIME_ROOT = _runtime_root()

# Config files (YAML)
CONFIG_DIR = RUNTIME_ROOT / "config"
OS_CONFIG_PATH = CONFIG_DIR / "os.yaml"
SYS_CONFIG_PATH = CONFIG_DIR / "sys.yaml"
USERS_CONFIG_PATH = CONFIG_DIR / "users.yaml"
APP_CONFIG_DIR = CONFIG_DIR / "apps"
MAGNET_CONFIG_PATH = CONFIG_DIR / "magnets.yaml"

# App installations (multi-version with symlinks)
APPS_DIR = RUNTIME_ROOT / "apps"

# Runtime data
DATA_DIR = RUNTIME_ROOT / "data"
DB_PATH = DATA_DIR / "aivuda.db"
# ARTIFACT_CACHE_DIR = DATA_DIR / "artifact-cache"
UPLOAD_TEMP_DIR = DATA_DIR / "uploads"
SESSIONS_DIR = DATA_DIR / "sessions"
LOG_DIR = DATA_DIR / "logs"
OS_LOG_DIR = LOG_DIR / "os"
APP_LOG_DIR = LOG_DIR / "apps"

# UI build output
UI_DIST_DIR = PROJECT_ROOT / "ui" / "dist"

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
        APPS_DIR,
        DATA_DIR,
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
    if not OS_CONFIG_PATH.exists():
        OS_CONFIG_PATH.write_text(
            yaml.dump(
                {
                    "_version": 1,
                    "_updated_at": None,
                    "_updated_by": "system",
                    **DEFAULT_OS_CONFIG,
                },
                default_flow_style=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

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
