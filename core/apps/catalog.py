from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

from core.apps.models import AppManifest
from core.db.connection import db_conn
from core.errors import NotFoundError


class CatalogService:
    def __init__(self, repo_url: str) -> None:
        self._repo_url = repo_url.rstrip("/")

    @property
    def repo_url(self) -> str:
        return self._repo_url

    def sync_from_repo(self) -> dict[str, Any]:
        """Fetch remote index and replace local catalog."""
        url = f"{self._repo_url}/index"
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if not isinstance(data, dict) or "items" not in data:
            raise RuntimeError("远端仓库 index 格式错误")

        items = data.get("items", [])
        now = int(time.time())
        repo_origin = urllib.parse.urlsplit(self._repo_url)
        host_base = f"{repo_origin.scheme}://{repo_origin.netloc}"

        with db_conn() as conn:
            conn.execute("DELETE FROM app_catalog")
            for item in items:
                app_id = item.get("app_id")
                manifest = item.get("manifest")
                if not app_id or not isinstance(manifest, dict):
                    continue
                install_obj = manifest.get("install", {})
                if isinstance(install_obj, dict) and install_obj.get("url", "").startswith("/"):
                    install_obj["url"] = urllib.parse.urljoin(
                        host_base, install_obj["url"]
                    )
                conn.execute(
                    "INSERT INTO app_catalog (app_id, manifest, updated_at) VALUES (?, ?, ?)",
                    (app_id, json.dumps(manifest), now),
                )
            conn.commit()

        return {
            "ok": True,
            "source": self._repo_url,
            "count": len(items),
            "updated_at": now,
        }

    def get_all(self) -> list[dict[str, Any]]:
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT app_id, manifest, updated_at FROM app_catalog ORDER BY app_id"
            ).fetchall()
        return [
            {
                "app_id": row["app_id"],
                "manifest": json.loads(row["manifest"]),
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_manifest(self, app_id: str) -> AppManifest:
        with db_conn() as conn:
            row = conn.execute(
                "SELECT manifest FROM app_catalog WHERE app_id = ?", (app_id,)
            ).fetchone()
        if not row:
            raise NotFoundError(f"App '{app_id}' not found in catalog")
        raw = json.loads(row["manifest"])
        return AppManifest.from_dict(app_id, raw)

    def get_manifest_raw(self, app_id: str) -> dict[str, Any]:
        with db_conn() as conn:
            row = conn.execute(
                "SELECT manifest FROM app_catalog WHERE app_id = ?", (app_id,)
            ).fetchone()
        if not row:
            raise NotFoundError(f"App '{app_id}' not found in catalog")
        return json.loads(row["manifest"])
