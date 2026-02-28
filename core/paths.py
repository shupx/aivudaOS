from __future__ import annotations

import os
from pathlib import Path

# PROJECT_ROOT is the aivudaOS/ directory itself
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Config files (YAML)
CONFIG_DIR = PROJECT_ROOT / "config"
OS_CONFIG_PATH = CONFIG_DIR / "os.yaml"
USERS_CONFIG_PATH = CONFIG_DIR / "users.yaml"
APP_CONFIG_DIR = CONFIG_DIR / "apps"

# App installations (multi-version with symlinks)
APPS_DIR = PROJECT_ROOT / "apps"

# Runtime data
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "aivuda.db"
ARTIFACT_CACHE_DIR = DATA_DIR / "artifact-cache"
SESSIONS_DIR = DATA_DIR / "sessions"
LOG_DIR = DATA_DIR / "logs"
OS_LOG_DIR = LOG_DIR / "os"
APP_LOG_DIR = LOG_DIR / "apps"

# UI build output
UI_DIST_DIR = PROJECT_ROOT / "ui" / "dist"


def ensure_dirs() -> None:
    """Create all required directories. Called once at startup."""
    for d in [
        CONFIG_DIR,
        APP_CONFIG_DIR,
        APPS_DIR,
        DATA_DIR,
        ARTIFACT_CACHE_DIR,
        SESSIONS_DIR,
        LOG_DIR,
        OS_LOG_DIR,
        APP_LOG_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)
