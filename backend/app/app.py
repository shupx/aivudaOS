from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.apps import router as apps_router
from backend.app.api.auth import router as auth_router
from backend.app.api.config import router as config_router
from backend.app.api.status import router as status_router
from backend.app.api.ws import router as ws_router
from backend.app.core.settings import ROOT
from backend.app.services.apps_service import sync_catalog_from_repo
from backend.app.services.db import init_db
from backend.app.services.telemetry import telemetry_loop


def create_app() -> FastAPI:
    app = FastAPI(title="Robot Config MVP", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(config_router)
    app.include_router(status_router)
    app.include_router(apps_router)
    app.include_router(ws_router)

    @app.on_event("startup")
    async def startup() -> None:
        init_db()
        try:
            sync_catalog_from_repo()
        except Exception:
            pass
        asyncio.create_task(telemetry_loop())

    if (ROOT / "frontend" / "dist").exists():
        app.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True), name="static")

    return app
