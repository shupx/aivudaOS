from __future__ import annotations

from core.db.connection import db_conn


def init_db() -> None:
    with db_conn() as conn:
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
                app_id TEXT NOT NULL,
                version TEXT NOT NULL,
                runtime TEXT NOT NULL,
                install_path TEXT NOT NULL,
                status TEXT NOT NULL,
                installed_at INTEGER NOT NULL,
                PRIMARY KEY (app_id, version)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_runtime (
                app_id TEXT PRIMARY KEY,
                running INTEGER NOT NULL DEFAULT 0,
                autostart INTEGER NOT NULL DEFAULT 0,
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
                progress INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )

        conn.commit()
