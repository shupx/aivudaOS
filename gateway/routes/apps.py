from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from core.auth.models import SessionInfo
from core.auth.service import AuthService
from core.errors import (
    AppNotInstalledError,
    AppRuntimeError,
    AuthenticationError,
    ConfigVersionConflictError,
    InstallTaskConflictError,
    NotFoundError,
    RuntimeNotAvailableError,
)
from gateway.deps import (
    get_auth_service,
    get_catalog_service,
    get_config_service,
    get_installer_service,
    get_runtime_service,
    get_versioning_service,
)
from gateway.schemas import (
    AppAutostartUpdateRequest,
    AppConfigUpdateRequest,
    AppInstallRequest,
    AppSwitchVersionRequest,
    AppUninstallRequest,
)

router = APIRouter(prefix="/api/apps", tags=["apps"])


def _require_auth(token: str) -> SessionInfo:
    auth: AuthService = get_auth_service()
    try:
        return auth.validate_token(token)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/repo/sync")
async def sync_repo(token: str) -> dict[str, Any]:
    _require_auth(token)
    catalog = get_catalog_service()
    try:
        return catalog.sync_from_repo()
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"同步远端仓库失败: {exc}"
        ) from exc


@router.get("/catalog")
async def get_catalog(token: str) -> dict[str, Any]:
    _require_auth(token)
    catalog = get_catalog_service()
    return {"items": catalog.get_all()}


@router.get("/installed")
async def get_installed(token: str) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    return {"items": runtime.get_installed_list()}


@router.post("/{app_id}/install")
async def install_app(
    app_id: str, payload: AppInstallRequest, token: str
) -> dict[str, Any]:
    _require_auth(token)
    installer = get_installer_service()
    try:
        return installer.create_install_task(app_id, payload.install_runtime)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InstallTaskConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, token: str) -> dict[str, Any]:
    _require_auth(token)
    installer = get_installer_service()
    try:
        return installer.get_task(task_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{app_id}/status")
async def get_status(app_id: str, token: str) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    try:
        return runtime.get_detail(app_id)
    except AppNotInstalledError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{app_id}/start")
async def start_app(app_id: str, token: str) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    try:
        return runtime.start(app_id)
    except AppNotInstalledError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (AppRuntimeError, RuntimeNotAvailableError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{app_id}/stop")
async def stop_app(app_id: str, token: str) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    try:
        return runtime.stop(app_id)
    except AppNotInstalledError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AppRuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{app_id}/autostart")
async def set_autostart(
    app_id: str, payload: AppAutostartUpdateRequest, token: str
) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    try:
        return runtime.set_autostart(app_id, payload.enabled)
    except AppNotInstalledError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AppRuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# NEW: Version switching endpoint
@router.post("/{app_id}/switch-version")
async def switch_version(
    app_id: str, payload: AppSwitchVersionRequest, token: str
) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    try:
        return runtime.switch_version(
            app_id, payload.version, payload.restart
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AppRuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# NEW: List versions for an app
@router.get("/{app_id}/versions")
async def list_versions(app_id: str, token: str) -> dict[str, Any]:
    _require_auth(token)
    versioning = get_versioning_service()
    versions = versioning.list_versions(app_id)
    active = versioning.active_version(app_id)
    return {"app_id": app_id, "versions": versions, "active_version": active}


@router.post("/{app_id}/uninstall")
async def uninstall_app(
    app_id: str, payload: AppUninstallRequest, token: str
) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    try:
        return runtime.uninstall(
            app_id, version=payload.version, purge=payload.purge
        )
    except AppNotInstalledError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{app_id}/config")
async def get_app_config(app_id: str, token: str) -> dict[str, Any]:
    _require_auth(token)
    catalog = get_catalog_service()
    config = get_config_service()
    try:
        manifest = catalog.get_manifest(app_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    cfg = config.get_app_config(app_id)
    if cfg.version == 0:
        return {
            "app_id": app_id,
            "data": manifest.default_config,
            "version": 0,
            "updated_at": None,
        }
    return {
        "app_id": app_id,
        "data": cfg.data,
        "version": cfg.version,
        "updated_at": cfg.updated_at,
    }


@router.put("/{app_id}/config")
async def put_app_config(
    app_id: str, payload: AppConfigUpdateRequest, token: str
) -> dict[str, Any]:
    _require_auth(token)
    catalog = get_catalog_service()
    config = get_config_service()
    try:
        catalog.get_manifest(app_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    try:
        result = config.update_app_config(
            app_id, payload.data, payload.version
        )
    except ConfigVersionConflictError:
        raise HTTPException(
            status_code=409, detail="App config version conflict"
        )
    return {"ok": True, "version": result.version}
