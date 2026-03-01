from __future__ import annotations

import json
import threading
import time
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from core.auth.models import SessionInfo
from core.auth.service import AuthService
from core.db.connection import db_conn
from core.errors import (
    AppOperationConflictError,
    AppNotInstalledError,
    AppRuntimeError,
    AuthenticationError,
    ConfigVersionConflictError,
    NotFoundError,
    PackageFormatError,
)
from gateway.deps import (
    get_app_operation_manager,
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
    AppUpdateThisVersionRequest,
    AppUninstallRequest,
)

router = APIRouter(prefix="/api/apps", tags=["apps"])


def _require_auth(token: str) -> SessionInfo:
    auth: AuthService = get_auth_service()
    try:
        return auth.validate_token(token)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid token")


def _sse_event(event: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {body}\n\n"


def _spawn_operation(
    operation_id: str,
    task: Any,
) -> None:
    operations = get_app_operation_manager()

    def runner() -> None:
        operations.mark_running(operation_id)
        try:
            result = task()
            operations.mark_completed(operation_id, result)
        except Exception as exc:
            operations.mark_failed(operation_id, str(exc))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()


# ================================================================== #
#  Upload & Install (primary flow — local package upload)
# ================================================================== #


@router.post("/upload", status_code=202)
async def upload_app(
    file: UploadFile = File(...),
    token: str = "",
) -> dict[str, Any]:
    """Upload an app package (.tar.gz / .zip) and install it.

    The package must contain a ``manifest.yaml`` at the root (or one level
    deep) describing the app metadata, runtime, entrypoint, etc.
    """
    _require_auth(token)
    operations = get_app_operation_manager()
    installer = get_installer_service()
    file_data = await file.read()
    filename = file.filename or "package.tar.gz"

    record = operations.start_operation("upload", app_id=None)

    def emit(event_type: str, payload: dict[str, Any]) -> None:
        app_id = payload.get("app_id")
        if app_id:
            operations.bind_app_id(record.operation_id, str(app_id))
        operations.publish(record.operation_id, event_type, **payload)

    def task() -> dict[str, Any]:
        try:
            return installer.install_from_upload(
                file_data,
                filename,
                event_cb=emit,
            )
        except PackageFormatError as exc:
            raise AppRuntimeError(str(exc)) from exc

    _spawn_operation(record.operation_id, task)
    return {
        "ok": True,
        "operation_id": record.operation_id,
        "status": "queued",
        "operation_type": "upload",
    }


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


@router.get("/{app_id}/icon")
async def get_app_icon(app_id: str) -> FileResponse:
    runtime = get_runtime_service()
    icon_path = runtime.get_app_icon_path(app_id)
    media_type = "image/png" if icon_path.suffix.lower() == ".png" else "image/svg+xml"
    return FileResponse(str(icon_path), media_type=media_type)


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


@router.post("/{app_id}/update_this_version", status_code=202)
async def update_this_version(
    app_id: str, payload: AppUpdateThisVersionRequest, token: str
) -> dict[str, Any]:
    _require_auth(token)
    operations = get_app_operation_manager()
    runtime = get_runtime_service()

    try:
        record = operations.start_operation("update_this_version", app_id=app_id)
    except AppOperationConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))

    def emit(event_type: str, event_payload: dict[str, Any]) -> None:
        operations.publish(record.operation_id, event_type, **event_payload)

    def task() -> dict[str, Any]:
        return runtime.update_this_version(
            app_id,
            payload.version,
            event_cb=emit,
        )

    _spawn_operation(record.operation_id, task)
    return {
        "ok": True,
        "operation_id": record.operation_id,
        "status": "queued",
        "operation_type": "update_this_version",
        "app_id": app_id,
    }


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


@router.post("/{app_id}/uninstall", status_code=202)
async def uninstall_app(
    app_id: str, payload: AppUninstallRequest, token: str
) -> dict[str, Any]:
    _require_auth(token)
    operations = get_app_operation_manager()
    runtime = get_runtime_service()

    try:
        record = operations.start_operation("uninstall", app_id=app_id)
    except AppOperationConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))

    def emit(event_type: str, event_payload: dict[str, Any]) -> None:
        operations.publish(record.operation_id, event_type, **event_payload)

    def task() -> dict[str, Any]:
        return runtime.uninstall(
            app_id,
            version=payload.version,
            purge=payload.purge,
            event_cb=emit,
        )

    _spawn_operation(record.operation_id, task)
    return {
        "ok": True,
        "operation_id": record.operation_id,
        "status": "queued",
        "operation_type": "uninstall",
        "app_id": app_id,
    }


@router.get("/operations/{operation_id}")
async def get_operation(operation_id: str, token: str) -> dict[str, Any]:
    _require_auth(token)
    operations = get_app_operation_manager()
    try:
        return operations.get_operation(operation_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/operations/{operation_id}/events")
async def stream_operation_events(
    operation_id: str,
    token: str,
) -> StreamingResponse:
    _require_auth(token)
    operations = get_app_operation_manager()
    try:
        operations.get_operation(operation_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    def event_iter() -> Any:
        seq = 0
        while True:
            events, done = operations.wait_events(operation_id, seq, timeout=15.0)
            if not events:
                heartbeat = {
                    "operation_id": operation_id,
                    "type": "heartbeat",
                    "ts": int(time.time()),
                }
                yield _sse_event("heartbeat", heartbeat)
                if done:
                    break
                continue

            for event in events:
                seq = int(event.get("seq", seq))
                event_name = str(event.get("type", "message"))
                yield _sse_event(event_name, event)

            if done:
                break

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
