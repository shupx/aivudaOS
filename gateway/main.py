from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.db.schema import init_db
from core.paths import UI_DIST_DIR, ensure_dirs
from gateway.deps import get_catalog_service
from gateway.routes import apps, auth, config


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
    app.include_router(apps.router)

    @app.on_event("startup")
    async def startup() -> None:
        ensure_dirs()
        init_db()
        try:
            get_catalog_service().sync_from_repo()
        except Exception:
            pass

    if UI_DIST_DIR.exists():
        # 生产环境直接提供静态文件，可以去掉，生产环境建议使用专门的静态文件服务器（如 nginx）来提供 UI 文件
        app.mount(
            "/",
            StaticFiles(directory=str(UI_DIST_DIR), html=True),
            name="static",
        )

    return app


app = create_app()
