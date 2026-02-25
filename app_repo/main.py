from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
FILES_DIR = DATA_DIR / "files"
DB_PATH = DATA_DIR / "repo.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
FILES_DIR.mkdir(parents=True, exist_ok=True)


def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_release (
                app_id TEXT NOT NULL,
                version TEXT NOT NULL,
                status TEXT NOT NULL,
                manifest TEXT NOT NULL,
                file_relpath TEXT,
                file_sha256 TEXT,
                file_size INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY(app_id, version)
            )
            """
        )
        conn.commit()


def parse_manifest(manifest_text: str | None) -> dict[str, Any]:
    if not manifest_text:
        return {}
    try:
        return json.loads(manifest_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"manifest_json 不是合法 JSON: {exc}") from exc


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def build_manifest(
    *,
    base_url: str,
    app_id: str,
    version: str,
    name: str,
    description: str,
    category: str,
    icon: str,
    runtime: str,
    runtime_optional: bool,
    run_entrypoint: str,
    run_args: list[str],
    config_schema: dict[str, Any],
    default_config: dict[str, Any],
    file_relpath: str | None,
    file_sha256_text: str | None,
    file_size: int | None,
    image: str | None,
    extra: dict[str, Any],
) -> dict[str, Any]:
    install_obj: dict[str, Any] = {}
    if runtime in {"docker", "podman"}:
        if not image:
            raise HTTPException(status_code=400, detail="容器应用必须提供 image")
        install_obj = {
            "image": image,
            "sha256": file_sha256_text or "",
        }
    else:
        if not file_relpath:
            raise HTTPException(status_code=400, detail="host 应用必须上传 artifact 文件")
        install_obj = {
            "url": f"{base_url}/repo/files/{file_relpath}",
            "sha256": file_sha256_text or "",
            "size": file_size or 0,
        }

    manifest = {
        "app_id": app_id,
        "name": name,
        "version": version,
        "description": description,
        "icon": icon,
        "category": category,
        "runtime": runtime,
        "install": install_obj,
        "run": {
            "entrypoint": run_entrypoint,
            "args": run_args,
        },
        "ui": extra.get("ui", {}),
        "config_schema": config_schema,
        "default_config": default_config,
        "autostart_supported": bool(extra.get("autostart_supported", True)),
        "runtime_optional": runtime_optional,
    }

    for key, value in extra.items():
        if key not in manifest:
            manifest[key] = value
    return manifest


app = FastAPI(title="aivudaOS App Repo", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    init_db()


@app.get("/repo/index")
async def repo_index() -> dict[str, Any]:
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT r1.*
            FROM app_release r1
            JOIN (
                SELECT app_id, MAX(created_at) AS max_created
                FROM app_release
                WHERE status = 'listed'
                GROUP BY app_id
            ) r2
            ON r1.app_id = r2.app_id AND r1.created_at = r2.max_created
            WHERE r1.status = 'listed'
            ORDER BY r1.app_id
            """
        ).fetchall()
    return {
        "generated_at": int(time.time()),
        "items": [
            {
                "app_id": row["app_id"],
                "version": row["version"],
                "manifest": json.loads(row["manifest"]),
                "updated_at": row["updated_at"],
            }
            for row in rows
        ],
    }


@app.get("/repo/admin/apps")
async def admin_apps() -> dict[str, Any]:
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT app_id, version, status, created_at, updated_at FROM app_release ORDER BY app_id, created_at DESC"
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@app.post("/repo/apps/upload")
async def upload_app(
    app_id: str = Form(...),
    version: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    category: str = Form("general"),
    icon: str = Form("box"),
    runtime: str = Form("host"),
    runtime_optional: bool = Form(False),
    image: str = Form(""),
    run_entrypoint: str = Form("./run.sh"),
    run_args_json: str = Form("[]"),
    config_schema_json: str = Form('{"type":"object","properties":{}}'),
    default_config_json: str = Form("{}"),
    manifest_json: str = Form(""),
    file: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    if runtime not in {"host", "docker", "podman"}:
        raise HTTPException(status_code=400, detail="runtime 仅支持 host/docker/podman")

    try:
        run_args = json.loads(run_args_json)
        config_schema = json.loads(config_schema_json)
        default_config = json.loads(default_config_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"JSON 参数错误: {exc}") from exc

    if not isinstance(run_args, list):
        raise HTTPException(status_code=400, detail="run_args_json 必须是数组")

    file_relpath: str | None = None
    file_sha: str | None = None
    file_size: int | None = None

    if file is not None:
        save_dir = FILES_DIR / "apps" / app_id / version
        save_dir.mkdir(parents=True, exist_ok=True)
        filename = file.filename or "artifact.bin"
        save_path = save_dir / filename
        with save_path.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        file_relpath = str(save_path.relative_to(FILES_DIR))
        file_sha = file_sha256(save_path)
        file_size = save_path.stat().st_size

    extra = parse_manifest(manifest_json)
    base_url = ""
    # 由客户端自行替换 host，避免代理/网关场景错位
    manifest = build_manifest(
        base_url=base_url,
        app_id=app_id,
        version=version,
        name=name,
        description=description,
        category=category,
        icon=icon,
        runtime=runtime,
        runtime_optional=runtime_optional,
        run_entrypoint=run_entrypoint,
        run_args=[str(x) for x in run_args],
        config_schema=config_schema,
        default_config=default_config,
        file_relpath=file_relpath,
        file_sha256_text=file_sha,
        file_size=file_size,
        image=image or None,
        extra=extra,
    )

    now = int(time.time())
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO app_release (
                app_id, version, status, manifest, file_relpath, file_sha256, file_size, created_at, updated_at
            ) VALUES (?, ?, 'listed', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(app_id, version) DO UPDATE SET
                status = 'listed',
                manifest = excluded.manifest,
                file_relpath = excluded.file_relpath,
                file_sha256 = excluded.file_sha256,
                file_size = excluded.file_size,
                updated_at = excluded.updated_at
            """,
            (
                app_id,
                version,
                json.dumps(manifest),
                file_relpath,
                file_sha,
                file_size,
                now,
                now,
            ),
        )
        conn.commit()

    return {"ok": True, "app_id": app_id, "version": version, "manifest": manifest}


@app.post("/repo/apps/{app_id}/delist")
async def delist_app(app_id: str) -> dict[str, Any]:
    now = int(time.time())
    with db_conn() as conn:
        row = conn.execute("SELECT COUNT(1) AS cnt FROM app_release WHERE app_id = ?", (app_id,)).fetchone()
        if row["cnt"] == 0:
            raise HTTPException(status_code=404, detail="app 不存在")
        conn.execute(
            "UPDATE app_release SET status = 'delisted', updated_at = ? WHERE app_id = ?",
            (now, app_id),
        )
        conn.commit()
    return {"ok": True, "app_id": app_id, "status": "delisted"}


@app.post("/repo/apps/{app_id}/list")
async def list_app(app_id: str) -> dict[str, Any]:
    now = int(time.time())
    with db_conn() as conn:
        row = conn.execute("SELECT COUNT(1) AS cnt FROM app_release WHERE app_id = ?", (app_id,)).fetchone()
        if row["cnt"] == 0:
            raise HTTPException(status_code=404, detail="app 不存在")
        conn.execute(
            "UPDATE app_release SET status = 'listed', updated_at = ? WHERE app_id = ?",
            (now, app_id),
        )
        conn.commit()
    return {"ok": True, "app_id": app_id, "status": "listed"}


@app.delete("/repo/apps/{app_id}/versions/{version}")
async def remove_version(app_id: str, version: str) -> dict[str, Any]:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT file_relpath FROM app_release WHERE app_id = ? AND version = ?",
            (app_id, version),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="版本不存在")
        conn.execute("DELETE FROM app_release WHERE app_id = ? AND version = ?", (app_id, version))
        conn.commit()

    file_rel = row["file_relpath"]
    if file_rel:
        p = FILES_DIR / file_rel
        if p.exists():
            p.unlink()
    return {"ok": True, "app_id": app_id, "version": version}


app.mount("/repo/files", StaticFiles(directory=FILES_DIR), name="repo-files")
