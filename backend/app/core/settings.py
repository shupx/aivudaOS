from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "backend" / "data"
DB_PATH = DATA_DIR / "app.db"
APPS_ROOT = DATA_DIR / "apps"
ARTIFACT_CACHE_ROOT = DATA_DIR / "artifact-cache"
APP_REPO_URL = os.environ.get("APP_REPO_URL", "http://127.0.0.1:9001/repo").rstrip("/")

DATA_DIR.mkdir(parents=True, exist_ok=True)
APPS_ROOT.mkdir(parents=True, exist_ok=True)
ARTIFACT_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
