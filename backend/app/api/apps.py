from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.app.schemas import AppAutostartUpdateRequest, AppConfigUpdateRequest, AppInstallRequest, AppUninstallRequest
from backend.app.services import apps_service
from backend.app.services.auth import auth_token

router = APIRouter(prefix="/api/apps", tags=["apps"])


@router.post("/repo/sync")
async def sync_repo(token: str) -> dict[str, Any]:
    await auth_token(token)
    try:
        return apps_service.sync_catalog_from_repo()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"同步远端仓库失败: {exc}") from exc


@router.get("/catalog")
async def get_catalog(token: str) -> dict[str, Any]:
    await auth_token(token)
    return apps_service.get_catalog()


@router.get("/installed")
async def get_installed(token: str) -> dict[str, Any]:
    await auth_token(token)
    return apps_service.get_installed()


@router.post("/{app_id}/install")
async def install_app(app_id: str, payload: AppInstallRequest, token: str) -> dict[str, Any]:
    await auth_token(token)
    return apps_service.create_install_task(app_id, payload.install_runtime)


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, token: str) -> dict[str, Any]:
    await auth_token(token)
    return apps_service.app_task_detail(task_id)


@router.get("/{app_id}/status")
async def get_status(app_id: str, token: str) -> dict[str, Any]:
    await auth_token(token)
    return apps_service.app_runtime_detail(app_id)


@router.post("/{app_id}/start")
async def start_app(app_id: str, token: str) -> dict[str, Any]:
    await auth_token(token)
    return apps_service.start_app_runtime(app_id)


@router.post("/{app_id}/stop")
async def stop_app(app_id: str, token: str) -> dict[str, Any]:
    await auth_token(token)
    return apps_service.stop_app_runtime(app_id)


@router.post("/{app_id}/autostart")
async def set_autostart(app_id: str, payload: AppAutostartUpdateRequest, token: str) -> dict[str, Any]:
    await auth_token(token)
    return apps_service.set_autostart(app_id, payload.enabled)


@router.post("/{app_id}/uninstall")
async def uninstall_app(app_id: str, payload: AppUninstallRequest, token: str) -> dict[str, Any]:
    await auth_token(token)
    return apps_service.uninstall_app(app_id, payload.purge)


@router.get("/{app_id}/config")
async def get_app_config(app_id: str, token: str) -> dict[str, Any]:
    await auth_token(token)
    return apps_service.get_app_config(app_id)


@router.put("/{app_id}/config")
async def put_app_config(app_id: str, payload: AppConfigUpdateRequest, token: str) -> dict[str, Any]:
    await auth_token(token)
    return apps_service.put_app_config(app_id, payload.version, payload.data)
