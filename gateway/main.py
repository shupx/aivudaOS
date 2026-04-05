from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from core.db.schema import init_db
from core.paths import UI_DIST_DIR, ensure_dirs
from core.config.caddy_runtime import CaddyRuntimeService
from gateway.deps import get_magnet_service, get_runtime_service
from gateway.routes import apps, auth, config


logger = logging.getLogger(__name__)
API_PREFIX = "/aivuda_os"


def create_app() -> FastAPI:
    app = FastAPI(title="AivudaOS", version="1.0.0")
    # app.add_middleware(
    #     CORSMiddleware,
    #     allow_origins=["*"], # dangerous in production, should be restricted to specific origins
    #     allow_credentials=False, # if true, also need to specify allowed origins and cannot be "*"
    #     allow_methods=["*"],
    #     allow_headers=["*"],
    # )

    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(config.router, prefix=API_PREFIX)
    app.include_router(apps.router, prefix=API_PREFIX)

    @app.on_event("startup")
    async def startup() -> None:
        ensure_dirs()
        init_db()
        get_magnet_service().recompute(updated_by="system")
        runtime = get_runtime_service()
        summary = runtime.start_autostart_apps() # only for popen mode, systemd will manage autostart itself and we skip replay to avoid conflicts
        mode = summary.get("mode", "popen")
        if mode == "systemd":
            logger.info("Autostart managed by systemd; startup replay skipped")
        if summary["failed"]:
            logger.warning("Autostart failures: %s", summary["failed"])
        if summary["started"]:
            logger.info("Autostart started apps: %s", summary["started"])

    if UI_DIST_DIR.exists():
        # 开发环境直接提供静态文件（使得访问后端 ip:port 也能打开前端网页），可以去掉；生产环境建议使用专门的静态文件服务器或反向代理来提供 UI 文件
        app.mount(
            "/",
            StaticFiles(directory=str(UI_DIST_DIR), html=True),
            name="static",
        )

    return app


app = create_app()
