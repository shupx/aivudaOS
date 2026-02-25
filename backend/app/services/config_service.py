from __future__ import annotations

import json
import time
from typing import Any

from fastapi import HTTPException

from backend.app.services.db import db_conn


def get_global_config() -> dict[str, Any]:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT data, version, updated_at, updated_by FROM config WHERE id = 1"
        ).fetchone()
    return {
        "data": json.loads(row["data"]),
        "version": row["version"],
        "updated_at": row["updated_at"],
        "updated_by": row["updated_by"],
    }


def update_global_config(version: int, data: dict[str, Any], username: str) -> dict[str, Any]:
    with db_conn() as conn:
        row = conn.execute("SELECT version FROM config WHERE id = 1").fetchone()
        if version != row["version"]:
            raise HTTPException(status_code=409, detail="Config version conflict")

        new_version = row["version"] + 1
        now = int(time.time())
        conn.execute(
            "UPDATE config SET data = ?, version = ?, updated_at = ?, updated_by = ? WHERE id = 1",
            (json.dumps(data), new_version, now, username),
        )
        conn.commit()

    return {"ok": True, "version": new_version}
