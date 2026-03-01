from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from core.auth.models import SessionInfo
from core.auth.service import AuthService
from core.db.connection import db_conn
from core.errors import (
    AppNotInstalledError,
    AppRuntimeError,
    AuthenticationError,
    ConfigVersionConflictError,
    NotFoundError,
    PackageFormatError,
)
from gateway.deps import (
    get_auth_service,
    get_config_service,
    get_installer_service,
    get_runtime_service,
    get_versioning_service,
)
from gateway.schemas import (
    AppAutostartUpdateRequest,
    AppConfigUpdateRequest,
    AppSwitchVersionRequest,
    AppUpdateVersionRequest,
    AppUninstallRequest,
)

router = APIRouter(prefix="/api/apps", tags=["apps"])


def _require_auth(token: str) -> SessionInfo:
    auth: AuthService = get_auth_service()
    try:
        return auth.validate_token(token)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ================================================================== #
#  Upload & Install (primary flow — local package upload)
# ================================================================== #


@router.post("/upload")
async def upload_app(
    file: UploadFile = File(...),
    token: str = "",
) -> dict[str, Any]:
    """Upload an app package (.tar.gz / .zip) and install it.

    The package must contain a ``manifest.yaml`` at the root (or one level
    deep) describing the app metadata, runtime, entrypoint, etc.
    """
    _require_auth(token)
    installer = get_installer_service()
    file_data = await file.read()
    filename = file.filename or "package.tar.gz"
    try:
        return installer.install_from_upload(file_data, filename)
    except PackageFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"安装失败: {e}")


# ================================================================== #
#  Listings & detail
# ================================================================== #


@router.get("/installed")
async def get_installed(token: str) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    return {"items": runtime.get_installed_list()}


@router.get("/{app_id}/status")
async def get_status(app_id: str, token: str) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    try:
        return runtime.get_detail(app_id)
    except AppNotInstalledError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{app_id}/logs")
async def get_logs(
    app_id: str,
    token: str,
    offset: int = 0,
    limit: int = 65536,
) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    try:
        return runtime.read_logs(app_id, offset=offset, limit=limit)
    except AppNotInstalledError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AppRuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================================================== #
#  Lifecycle: start / stop / restart
# ================================================================== #


@router.post("/{app_id}/start")
async def start_app(app_id: str, token: str) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    try:
        return runtime.start(app_id)
    except AppNotInstalledError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AppRuntimeError as e:
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


@router.post("/{app_id}/restart")
async def restart_app(app_id: str, token: str) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    try:
        return runtime.restart(app_id)
    except AppNotInstalledError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AppRuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================================================== #
#  Autostart
# ================================================================== #


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


# ================================================================== #
#  Version management & upgrade
# ================================================================== #


@router.get("/{app_id}/versions")
async def list_versions(app_id: str, token: str) -> dict[str, Any]:
    _require_auth(token)
    versioning = get_versioning_service()
    versions = versioning.list_versions(app_id)
    active = versioning.active_version(app_id)
    return {"app_id": app_id, "versions": versions, "active_version": active}


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


@router.post("/{app_id}/update_version")
async def update_version(
    app_id: str, payload: AppUpdateVersionRequest, token: str
) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    try:
        return runtime.update_version(app_id, payload.version)
    except AppNotInstalledError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AppRuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{app_id}/upgrade")
async def upgrade_app(
    app_id: str,
    file: UploadFile = File(...),
    token: str = "",
) -> dict[str, Any]:
    """Upload a new version package to upgrade an existing app.

    - Installs the new version
    - Activates it
    - If the app was running, restarts it automatically
    """
    _require_auth(token)
    installer = get_installer_service()
    runtime = get_runtime_service()

    file_data = await file.read()
    filename = file.filename or "package.tar.gz"

    # Check if running before install
    rs = runtime.get_runtime_state(app_id)
    was_running = rs.running

    try:
        result = installer.install_from_upload(file_data, filename)
    except PackageFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"升级失败: {e}")

    # If was running, restart with new version
    if was_running:
        try:
            runtime.restart(result["app_id"])
            result["restarted"] = True
        except Exception:
            result["restarted"] = False

    result["upgraded"] = True
    return result


# ================================================================== #
#  Uninstall
# ================================================================== #


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


# ================================================================== #
#  Per-app config
# ================================================================== #


@router.get("/{app_id}/config")
async def get_app_config(app_id: str, token: str) -> dict[str, Any]:
    """Get config for an installed app.

    Reads default_config from the manifest stored in DB.
    """
    _require_auth(token)
    config = get_config_service()
    cfg = config.get_app_config(app_id)

    if cfg.version == 0:
        # No custom config yet — return default from manifest
        default_config = _get_default_config_from_db(app_id)
        return {
            "app_id": app_id,
            "data": default_config,
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
    config = get_config_service()

    # Verify the app is installed
    versioning = get_versioning_service()
    if not versioning.list_versions(app_id):
        raise HTTPException(status_code=404, detail=f"{app_id} 未安装")

    try:
        result = config.update_app_config(
            app_id, payload.data, payload.version
        )
    except ConfigVersionConflictError:
        raise HTTPException(
            status_code=409, detail="App config version conflict"
        )
    return {"ok": True, "version": result.version}


# ================================================================== #
#  Helpers
# ================================================================== #


def _get_default_config_from_db(app_id: str) -> dict[str, Any]:
    """Read default_config from the manifest stored in app_installation."""
    with db_conn() as conn:
        row = conn.execute(
            "SELECT manifest FROM app_installation WHERE app_id = ? "
            "ORDER BY installed_at DESC LIMIT 1",
            (app_id,),
        ).fetchone()
    if row and row["manifest"]:
        manifest_data = json.loads(row["manifest"])
        return manifest_data.get("default_config", {})
    return {}
