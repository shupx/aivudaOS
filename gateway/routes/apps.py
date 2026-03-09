from __future__ import annotations

import json
import threading
import time
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse

from core.apps.config_validation import normalize_config_schema, validate_config_data
from core.auth.models import SessionInfo
from core.auth.service import AuthService
from core.db.connection import db_conn
from core.errors import (
    AppOperationConflictError,
    AppNotInstalledError,
    AppRuntimeError,
    AuthenticationError,
    ConfigVersionConflictError,
    InvalidConfigError,
    NotFoundError,
    OperationCanceledError,
    PackageFormatError,
)
from gateway.deps import (
    get_app_operation_manager,
    get_auth_service,
    get_config_service,
    get_installer_service,
    get_magnet_service,
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


def _optional_auth(token: str) -> None:
    if not str(token or "").strip():
        return
    _require_auth(token)


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
        except OperationCanceledError as exc:
            operations.mark_canceled(operation_id, str(exc))
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
    overwrite: bool = False,
    token: str = "",
) -> dict[str, Any]:
    """Upload an app package (.tar.gz / .zip) and install it.

    The package must contain a ``manifest.yaml`` at the root (or one level
    deep) describing the app metadata, runtime, entrypoint, etc.
    """
    session = _require_auth(token)
    operations = get_app_operation_manager()
    installer = get_installer_service()
    file_data = await file.read()
    filename = file.filename or "package.tar.gz"

    record = operations.start_operation(
        "upload",
        app_id=None,
        interactive_enabled=True,
    )

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
                overwrite=overwrite,
                event_cb=emit,
                interactive=True,
                read_input=lambda timeout: operations.wait_interactive_input(
                    record.operation_id,
                    timeout=timeout,
                ),
                cancel_requested=lambda: operations.is_cancel_requested(
                    record.operation_id,
                ),
            )
        except PackageFormatError as exc:
            raise AppRuntimeError(str(exc)) from exc

    _spawn_operation(record.operation_id, task)
    return {
        "ok": True,
        "operation_id": record.operation_id,
        "status": "queued",
        "operation_type": "upload",
        "interactive_enabled": True,
        "interactive_ws_path": f"/api/apps/operations/{record.operation_id}/interactive/ws",
        "operator": session.username,
    }


# ================================================================== #
#  Listings & detail
# ================================================================== #


@router.get("/installed")
async def get_installed(token: str) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    return {"items": runtime.get_installed_list()}


@router.get("/configs/active")
async def get_active_configs(token: str) -> dict[str, Any]:
    _require_auth(token)
    runtime = get_runtime_service()
    config = get_config_service()
    magnet = get_magnet_service()
    items: list[dict[str, Any]] = []

    for app in runtime.get_installed_list():
        app_id = str(app.get("app_id") or "")
        app_version = str(app.get("active_version") or "")
        if not app_id or not app_version:
            continue

        cfg = config.get_app_config(app_id, app_version)
        manifest = _get_manifest_from_db(app_id, app_version)
        schema = manifest.get("config_schema") if isinstance(manifest, dict) else {}
        default_config = manifest.get("default_config") if isinstance(manifest, dict) else {}
        normalized_schema = normalize_config_schema(schema)
        data = dict(cfg.data) if cfg.version > 0 else dict(default_config or {})

        items.append(
            {
                "app_id": app_id,
                "name": str(app.get("name") or app_id),
                "app_version": app_version,
                "data": data,
                "version": cfg.version,
                "updated_at": cfg.updated_at,
                "schema": schema or {},
                "normalized_schema": normalized_schema,
                "constraints": _get_constraints_for_app(app_id),
                "readonly_paths": sorted(
                    magnet.readonly_paths_for_app(app_id, app_version)
                ),
            }
        )

    magnets = magnet.list_groups()
    return {
        "items": items,
        "magnets": magnets.get("items") or [],
        "magnet_conflicts": magnets.get("conflicts") or [],
        "magnet_version": magnets.get("version", 0),
    }


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


@router.get("/{app_id}/ui")
@router.get("/{app_id}/ui/")
async def get_app_builtin_ui_entry(app_id: str, token: str = "") -> FileResponse:
    _optional_auth(token)
    runtime = get_runtime_service()
    entry_path = runtime.get_app_ui_entry_path(app_id)
    if entry_path is None:
        raise HTTPException(status_code=404, detail="Built-in UI entry not found")
    return FileResponse(str(entry_path), media_type="text/html")


@router.get("/{app_id}/ui/{asset_path:path}")
async def get_app_builtin_ui_asset(
    app_id: str,
    asset_path: str,
    token: str = "",
) -> FileResponse:
    _optional_auth(token)
    runtime = get_runtime_service()
    asset = runtime.get_app_ui_asset_path(app_id, asset_path)
    if asset is None:
        raise HTTPException(status_code=404, detail="Built-in UI asset not found")
    return FileResponse(str(asset))


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
        record = operations.start_operation(
            "update_this_version",
            app_id=app_id,
            interactive_enabled=True,
        )
    except AppOperationConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))

    def emit(event_type: str, event_payload: dict[str, Any]) -> None:
        operations.publish(record.operation_id, event_type, **event_payload)

    def task() -> dict[str, Any]:
        return runtime.update_this_version(
            app_id,
            payload.version,
            event_cb=emit,
            interactive=True,
            read_input=lambda timeout: operations.wait_interactive_input(
                record.operation_id,
                timeout=timeout,
            ),
            cancel_requested=lambda: operations.is_cancel_requested(
                record.operation_id,
            ),
        )

    _spawn_operation(record.operation_id, task)
    return {
        "ok": True,
        "operation_id": record.operation_id,
        "status": "queued",
        "operation_type": "update_this_version",
        "app_id": app_id,
        "interactive_enabled": True,
        "interactive_ws_path": f"/api/apps/operations/{record.operation_id}/interactive/ws",
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
        record = operations.start_operation(
            "uninstall",
            app_id=app_id,
            interactive_enabled=True,
        )
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
            interactive=True,
            read_input=lambda timeout: operations.wait_interactive_input(
                record.operation_id,
                timeout=timeout,
            ),
            cancel_requested=lambda: operations.is_cancel_requested(
                record.operation_id,
            ),
        )

    _spawn_operation(record.operation_id, task)
    return {
        "ok": True,
        "operation_id": record.operation_id,
        "status": "queued",
        "operation_type": "uninstall",
        "app_id": app_id,
        "interactive_enabled": True,
        "interactive_ws_path": f"/api/apps/operations/{record.operation_id}/interactive/ws",
    }


@router.get("/operations/{operation_id}")
async def get_operation(operation_id: str, token: str) -> dict[str, Any]:
    _require_auth(token)
    operations = get_app_operation_manager()
    try:
        return operations.get_operation(operation_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/operations/{operation_id}/cancel")
async def cancel_operation(operation_id: str, token: str) -> dict[str, Any]:
    _require_auth(token)
    operations = get_app_operation_manager()
    try:
        operations.request_cancel(operation_id, reason="Canceled by user")
        return {
            "ok": True,
            "operation_id": operation_id,
            "status": "cancelling",
        }
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AppOperationConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.websocket("/operations/{operation_id}/interactive/ws")
async def operation_interactive_ws(
    websocket: WebSocket,
    operation_id: str,
) -> None:
    token = str(websocket.query_params.get("token") or "")
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    try:
        _require_auth(token)
    except HTTPException:
        await websocket.close(code=1008, reason="Invalid token")
        return

    operations = get_app_operation_manager()
    try:
        info = operations.get_operation(operation_id)
    except NotFoundError:
        await websocket.close(code=1008, reason="Operation not found")
        return

    if not bool(info.get("interactive_enabled")):
        await websocket.close(code=1008, reason="Interactive mode disabled")
        return

    await websocket.accept()
    await websocket.send_json(
        {
            "type": "interactive_ready",
            "operation_id": operation_id,
            "interactive_open": bool(info.get("interactive_open")),
        }
    )

    try:
        while True:
            message = await websocket.receive_text()
            payload = message
            try:
                data = json.loads(message)
                if isinstance(data, dict):
                    payload = str(data.get("data", ""))
            except json.JSONDecodeError:
                payload = message

            if payload is None:
                continue

            text = str(payload)
            if not text.strip():
                continue

            try:
                operations.submit_interactive_input(operation_id, text)
            except (AppOperationConflictError, NotFoundError) as exc:
                await websocket.send_json(
                    {
                        "type": "interactive_closed",
                        "operation_id": operation_id,
                        "message": str(exc),
                    }
                )
                await websocket.close(code=1000)
                return

            await websocket.send_json(
                {
                    "type": "interactive_input_accepted",
                    "operation_id": operation_id,
                }
            )
    except WebSocketDisconnect:
        return


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
async def get_app_config(app_id: str, token: str, app_version: str | None = None) -> dict[str, Any]:
    """Get config for an installed app.

    Reads default_config from the manifest stored in DB.
    """
    _require_auth(token)
    config = get_config_service()
    magnet = get_magnet_service()
    versioning = get_versioning_service()
    target_version = app_version or versioning.active_version(app_id)
    if not target_version:
        raise HTTPException(status_code=404, detail=f"{app_id} not installed")

    cfg = config.get_app_config(app_id, target_version)
    manifest = _get_manifest_from_db(app_id, target_version)
    data = dict(cfg.data) if cfg.version > 0 else dict(manifest.get("default_config") or {})

    constraints = _get_constraints_for_app(app_id)
    normalized_schema = normalize_config_schema(manifest.get("config_schema") or {})
    readonly_paths = sorted(magnet.readonly_paths_for_app(app_id, target_version))
    return {
        "app_id": app_id,
        "app_version": target_version,
        "data": data,
        "version": cfg.version,
        "updated_at": cfg.updated_at,
        "schema": manifest.get("config_schema") or {},
        "normalized_schema": normalized_schema,
        "constraints": constraints,
        "readonly_paths": readonly_paths,
    }


@router.put("/{app_id}/config")
async def put_app_config(
    app_id: str, payload: AppConfigUpdateRequest, token: str
) -> dict[str, Any]:
    session = _require_auth(token)
    config = get_config_service()
    magnet = get_magnet_service()

    # Verify the app is installed
    versioning = get_versioning_service()
    versions = versioning.list_versions(app_id)
    if not versions:
        raise HTTPException(status_code=404, detail=f"{app_id} is not installed")

    target_version = payload.app_version or versioning.active_version(app_id)
    if not target_version:
        raise HTTPException(status_code=404, detail=f"{app_id} has no active version")
    if target_version not in versions:
        raise HTTPException(status_code=404, detail=f"{app_id}@{target_version} is not installed")

    manifest = _get_manifest_from_db(app_id, target_version)
    schema = manifest.get("config_schema") or {}
    try:
        validate_config_data(payload.data, schema, context=f"api {app_id}@{target_version}")
    except InvalidConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    violations = _validate_equal_constraints(
        editing_app_id=app_id,
        editing_app_version=target_version,
        editing_data=payload.data,
    )
    if violations:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "App config equal constraints violated",
                "violations": violations,
            },
        )

    current_cfg = config.get_app_config(app_id, target_version)
    current_data = current_cfg.data if current_cfg.version > 0 else dict(manifest.get("default_config") or {})
    blocked_paths = magnet.blocked_paths_for_app_update(
        app_id=app_id,
        app_version=target_version,
        before_data=current_data,
        after_data=payload.data,
    )
    if blocked_paths:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Magnet-bound parameters are read-only here",
                "blocked_paths": blocked_paths,
            },
        )

    try:
        result = config.update_app_config(
            app_id,
            target_version,
            payload.data,
            payload.version,
            updated_by=session.username,
        )
    except ConfigVersionConflictError:
        raise HTTPException(
            status_code=409, detail="App config version conflict"
        )

    magnet.recompute(updated_by=session.username)
    return {"ok": True, "version": result.version, "app_version": target_version}


# ================================================================== #
#  Helpers
# ================================================================== #


def _get_manifest_from_db(app_id: str, app_version: str) -> dict[str, Any]:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT manifest FROM app_installation WHERE app_id = ? AND version = ? LIMIT 1",
            (app_id, app_version),
        ).fetchone()
    if row and row["manifest"]:
        return json.loads(row["manifest"])
    return {}


def _get_constraints_for_app(app_id: str) -> list[dict[str, Any]]:
    config = get_config_service()
    sys_data = config.get_sys_config().data
    constraints = sys_data.get("app_config_equal_constraints")
    if not isinstance(constraints, list):
        return []

    selected: list[dict[str, Any]] = []
    for item in constraints:
        if not isinstance(item, dict):
            continue
        left = item.get("left")
        right = item.get("right")
        if not (isinstance(left, dict) and isinstance(right, dict)):
            continue
        if left.get("app_id") == app_id or right.get("app_id") == app_id:
            selected.append(item)
    return selected


def _validate_equal_constraints(
    editing_app_id: str,
    editing_app_version: str,
    editing_data: dict[str, Any],
) -> list[dict[str, Any]]:
    constraints = _get_constraints_for_app(editing_app_id)
    if not constraints:
        return []

    config = get_config_service()
    versioning = get_versioning_service()
    violations: list[dict[str, Any]] = []

    for item in constraints:
        left = item.get("left") if isinstance(item, dict) else None
        right = item.get("right") if isinstance(item, dict) else None
        if not (isinstance(left, dict) and isinstance(right, dict)):
            continue

        left_value = _resolve_endpoint_value(
            left,
            editing_app_id,
            editing_app_version,
            editing_data,
            config,
            versioning,
        )
        right_value = _resolve_endpoint_value(
            right,
            editing_app_id,
            editing_app_version,
            editing_data,
            config,
            versioning,
        )

        if left_value is None or right_value is None:
            continue
        if left_value != right_value:
            violations.append(
                {
                    "left": left,
                    "right": right,
                    "left_value": left_value,
                    "right_value": right_value,
                }
            )

    return violations


def _resolve_endpoint_value(
    endpoint: dict[str, Any],
    editing_app_id: str,
    editing_app_version: str,
    editing_data: dict[str, Any],
    config: Any,
    versioning: Any,
) -> Any:
    app_id = str(endpoint.get("app_id") or "")
    path = str(endpoint.get("path") or "")
    if not app_id or not path:
        return None

    if app_id == editing_app_id:
        return _nested_get(editing_data, path)

    active_version = versioning.active_version(app_id)
    if not active_version:
        return None

    cfg = config.get_app_config(app_id, active_version)
    if cfg.version > 0:
        source = cfg.data
    else:
        manifest = _get_manifest_from_db(app_id, active_version)
        source = manifest.get("default_config") or {}
    return _nested_get(source, path)


def _nested_get(data: Any, dotted_path: str) -> Any:
    current = data
    for part in dotted_path.split("."):
        key = part.strip()
        if not key:
            return None
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current
    return {}
