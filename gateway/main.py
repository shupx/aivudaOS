from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.db.schema import init_db
from core.paths import UI_DIST_DIR, ensure_dirs
from gateway.deps import get_catalog_service
from gateway.routes import apps, auth, config, status, ws


def create_app() -> FastAPI:
    app = FastAPI(title="AivudaOS", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(config.router)
    app.include_router(status.router)
    app.include_router(apps.router)
    app.include_router(ws.router)

    @app.on_event("startup")
    async def startup() -> None:
        ensure_dirs()
        init_db()
        try:
            get_catalog_service().sync_from_repo()
        except Exception:
            pass
        asyncio.create_task(ws.telemetry_broadcast_loop())

    if UI_DIST_DIR.exists():
        app.mount(
            "/",
            StaticFiles(directory=str(UI_DIST_DIR), html=True),
            name="static",
        )

    return app


app = create_app()
