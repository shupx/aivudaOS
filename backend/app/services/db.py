from __future__ import annotations

import json
import sqlite3
import time

from backend.app.core.settings import DB_PATH


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_catalog (
                app_id TEXT PRIMARY KEY,
                manifest TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_installation (
                app_id TEXT PRIMARY KEY,
                version TEXT NOT NULL,
                runtime TEXT NOT NULL,
                install_path TEXT NOT NULL,
                status TEXT NOT NULL,
                installed_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_config (
                app_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                version INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_runtime (
                app_id TEXT PRIMARY KEY,
                running INTEGER NOT NULL,
                autostart INTEGER NOT NULL,
                pid INTEGER,
                container_id TEXT,
                last_started_at INTEGER,
                last_stopped_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_task (
                task_id TEXT PRIMARY KEY,
                app_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL,
                message TEXT NOT NULL,
                error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
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
