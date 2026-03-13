from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from core.auth.models import SessionInfo
from core.auth.service import AuthService
from core.config.service import ConfigService
from core.errors import AuthenticationError, ConfigVersionConflictError
from core.errors import InvalidConfigError, NotFoundError
from gateway.deps import (
    get_auth_service,
    get_config_service,
    get_magnet_service,
    get_relogin_service,
    get_sudo_nopasswd_service,
)
from gateway.schemas import ConfigUpdateRequest, MagnetUpdateRequest, SudoNopasswdUpdateRequest

router = APIRouter(prefix="/api/config", tags=["config"])


def _require_auth(token: str) -> SessionInfo:
    auth: AuthService = get_auth_service()
    try:
        return auth.validate_token(token)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("/system/sudo-nopasswd")
async def get_sudo_nopasswd(token: str) -> dict[str, Any]:
    _require_auth(token)
    service = get_sudo_nopasswd_service()
    try:
        return service.get_status()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/system/sudo-nopasswd")
async def put_sudo_nopasswd(payload: SudoNopasswdUpdateRequest, token: str) -> dict[str, Any]:
    _require_auth(token)
    service = get_sudo_nopasswd_service()
    try:
        result = service.set_enabled(payload.enabled, payload.sudo_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, **result}


@router.post("/system/relogin")
async def relogin_system_user(token: str) -> dict[str, Any]:
    _require_auth(token)

    auth = get_auth_service()
    auth.logout(token)

    relogin_service = get_relogin_service()
    relogin_service.trigger_relogin()

    return {
        "ok": True,
        "message": "Relogin has been scheduled. User services will restart shortly.",
    }


@router.post("/system/avahi/restart")
async def restart_avahi(token: str) -> dict[str, Any]:
    _require_auth(token)
    config = get_config_service()
    try:
        config.restart_avahi_daemon()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to restart avahi-daemon.service: {exc}")
    return {"ok": True}


@router.get("")
async def get_config(token: str) -> dict[str, Any]:
    _require_auth(token)
    config: ConfigService = get_config_service()
    magnet = get_magnet_service()
    cfg = config.get_sys_config()
    magnets = magnet.list_groups()
    return {
        "data": cfg.data,
        "version": cfg.version,
        "updated_at": cfg.updated_at,
        "updated_by": cfg.updated_by,
        "readonly_paths": sorted(magnet.readonly_paths_for_sys()),
        "magnets": magnets.get("items") or [],
        "magnet_conflicts": magnets.get("conflicts") or [],
        "magnet_version": magnets.get("version", 0),
    }


@router.put("")
async def put_config(payload: ConfigUpdateRequest, token: str) -> dict[str, Any]:
    user = _require_auth(token)
    config: ConfigService = get_config_service()
    magnet = get_magnet_service()

    current = config.get_sys_config()
    blocked_paths = magnet.blocked_paths_for_sys_update(
        before_data=current.data,
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

    result = None
    for _ in range(5):
        current_for_write = config.get_sys_config()
        try:
            result = config.update_sys_config(
                payload.data,
                current_for_write.version,
                user.username,
            )
            break
        except ConfigVersionConflictError:
            continue

    if result is None:
        raise HTTPException(status_code=409, detail="Config version conflict")

    magnet.recompute(updated_by=user.username)
    return {"ok": True, "version": result.version}


@router.get("/os")
async def get_os_config(token: str) -> dict[str, Any]:
    _require_auth(token)
    config: ConfigService = get_config_service()
    cfg = config.get_os_config()
    return {
        "data": cfg.data,
        "version": cfg.version,
        "updated_at": cfg.updated_at,
        "updated_by": cfg.updated_by,
    }


@router.put("/os")
async def put_os_config(payload: ConfigUpdateRequest, token: str) -> dict[str, Any]:
    user = _require_auth(token)
    config: ConfigService = get_config_service()

    result = None
    for _ in range(5):
        current_for_write = config.get_os_config()
        try:
            result = config.update_os_config(
                payload.data,
                current_for_write.version,
                user.username,
            )
            break
        except ConfigVersionConflictError:
            continue
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    if result is None:
        raise HTTPException(status_code=409, detail="Config version conflict")

    return {"ok": True, "version": result.version}


@router.get("/magnets")
async def list_magnets(token: str) -> dict[str, Any]:
    _require_auth(token)
    magnet = get_magnet_service()
    return magnet.list_groups()


@router.put("/magnets/{group_id}")
async def update_magnet(group_id: str, payload: MagnetUpdateRequest, token: str) -> dict[str, Any]:
    user = _require_auth(token)
    magnet = get_magnet_service()

    try:
        result = magnet.update_group_value(
            group_id=group_id,
            value=payload.value,
            expected_version=payload.version,
            updated_by=user.username,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ConfigVersionConflictError:
        raise HTTPException(status_code=409, detail="Magnet config version conflict")
    except InvalidConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return result
