import asyncio
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "backend" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "app.db"

DEFAULT_USER = {"username": "admin", "password": "admin123", "role": "admin"}
TOKENS: dict[str, dict[str, str]] = {}
WS_CLIENTS: set[WebSocket] = set()
SEQ = 0


def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL,
                version INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                updated_by TEXT NOT NULL
            )
            """
        )
        row = conn.execute("SELECT id FROM config WHERE id = 1").fetchone()
        if row is None:
            default_cfg = {
                "max_altitude_m": 120,
                "return_home_altitude_m": 30,
                "failsafe_action": "rtl",
            }
            conn.execute(
                "INSERT INTO config (id, data, version, updated_at, updated_by) VALUES (1, ?, 1, ?, ?)",
                (json.dumps(default_cfg), int(time.time()), "system"),
            )
        conn.commit()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class ConfigUpdateRequest(BaseModel):
    version: int
    data: dict[str, Any]


app = FastAPI(title="Drone Config MVP", version="0.1.0")

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
    asyncio.create_task(telemetry_loop())


async def auth_token(token: str) -> dict[str, str]:
    user = TOKENS.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    if payload.username != DEFAULT_USER["username"] or payload.password != DEFAULT_USER["password"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = str(uuid.uuid4())
    TOKENS[token] = {"username": payload.username, "role": DEFAULT_USER["role"]}
    return LoginResponse(access_token=token, role=DEFAULT_USER["role"])


@app.get("/api/auth/me")
async def me(token: str) -> dict[str, str]:
    user = await auth_token(token)
    return user


@app.get("/api/config")
async def get_config(token: str) -> dict[str, Any]:
    await auth_token(token)
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


@app.put("/api/config")
async def put_config(payload: ConfigUpdateRequest, token: str) -> dict[str, Any]:
    user = await auth_token(token)
    with db_conn() as conn:
        row = conn.execute("SELECT version FROM config WHERE id = 1").fetchone()
        if payload.version != row["version"]:
            raise HTTPException(status_code=409, detail="Config version conflict")

        new_version = row["version"] + 1
        now = int(time.time())
        conn.execute(
            "UPDATE config SET data = ?, version = ?, updated_at = ?, updated_by = ? WHERE id = 1",
            (json.dumps(payload.data), new_version, now, user["username"]),
        )
        conn.commit()

    return {"ok": True, "version": new_version}


@app.get("/api/status/snapshot")
async def snapshot(token: str) -> dict[str, Any]:
    await auth_token(token)
    now = int(time.time())
    return {
        "timestamp": now,
        "battery": 88,
        "mode": "STANDBY",
        "gps_fix": True,
        "lat": 31.2304,
        "lon": 121.4737,
    }


@app.websocket("/ws/telemetry")
async def telemetry_ws(ws: WebSocket) -> None:
    token = ws.query_params.get("token", "")
    if token not in TOKENS:
        await ws.close(code=1008)
        return

    await ws.accept()
    WS_CLIENTS.add(ws)
    try:
        while True:
            _ = await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        WS_CLIENTS.discard(ws)


async def telemetry_loop() -> None:
    global SEQ
    while True:
        await asyncio.sleep(1)
        if not WS_CLIENTS:
            continue
        SEQ += 1
        payload = {
            "seq": SEQ,
            "timestamp": int(time.time()),
            "battery": max(20, 100 - (SEQ % 80)),
            "mode": "AUTO" if SEQ % 2 == 0 else "STANDBY",
            "gps_fix": True,
            "speed_mps": round(4.5 + (SEQ % 5) * 0.3, 2),
        }
        dead: list[WebSocket] = []
        for client in WS_CLIENTS:
            try:
                await client.send_json(payload)
            except Exception:
                dead.append(client)
        for client in dead:
            WS_CLIENTS.discard(client)


if (ROOT / "frontend" / "dist").exists():
    app.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True), name="static")
