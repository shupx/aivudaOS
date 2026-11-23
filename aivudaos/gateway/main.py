from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from aivudaos.core.db.schema import init_db
from aivudaos.core.paths import UI_DIST_DIR, ensure_dirs
from aivudaos.core.errors import AppOperationConflictError, AppRuntimeError
from aivudaos.gateway.deps import get_magnet_service, get_pipeline_service, get_runtime_service
from aivudaos.gateway.routes import apps, auth, config, pipeline, shared_store


logger = logging.getLogger(__name__)
API_PREFIX = "/aivuda_os"


def create_app() -> FastAPI:
    app = FastAPI(title="AivudaOS", version="1.0.0")
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(config.router, prefix=API_PREFIX)
    app.include_router(pipeline.router, prefix=API_PREFIX)
    app.include_router(apps.router, prefix=API_PREFIX)

    app.include_router(shared_store.router, prefix=API_PREFIX)
    app.mount(API_PREFIX + "/api/shared-apps", shared_store.shared_store)

    from aivudaos.mcp_server import install_mcp
    install_mcp(app)

    @app.on_event("startup")
    async def startup() -> None:
        ensure_dirs()
        init_db()
        get_magnet_service().recompute(updated_by="system")
        try:
            operation = get_pipeline_service().startup()
        except (ValueError, OSError, AppRuntimeError, AppOperationConflictError):
            # Keep the gateway available for diagnosis. Never fall back to an
            # unordered replay when ownership or its execution plan is invalid.
            logger.exception('Startup pipeline was not launched')
            return
        if operation:
            logger.info('Queued startup pipeline: %s', operation['operation_id'])
            return
        runtime = get_runtime_service()
        summary = runtime.start_autostart_apps()
        mode = summary.get("mode", "popen")
        if mode == "systemd":
            logger.info("Autostart managed by systemd; startup replay skipped")
        if summary["failed"]:
            logger.warning("Autostart failures: %s", summary["failed"])
        if summary["started"]:
            logger.info("Autostart started apps: %s", summary["started"])

    @app.on_event("shutdown")
    async def shutdown() -> None:
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(get_pipeline_service().shutdown)
        await run_in_threadpool(get_runtime_service().shutdown)

    if UI_DIST_DIR.exists():
        # 开发环境直接提供静态文件（使得访问后端 ip:port 也能打开前端网页），可以去掉；生产环境建议使用专门的静态文件服务器或反向代理来提供 UI 文件
        app.mount(
            "/",
            StaticFiles(directory=str(UI_DIST_DIR), html=True),
            name="static",
        )

    return app


app = create_app()
