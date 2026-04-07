from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from aivudaos.core.auth.models import SessionInfo
from aivudaos.core.auth.service import AuthService
from aivudaos.core.config.service import ConfigService
from aivudaos.core.errors import AuthenticationError, ConfigVersionConflictError
from aivudaos.core.errors import InvalidConfigError, NotFoundError
from aivudaos.gateway.deps import (
    get_apt_sources_service,
    get_aivudaos_service_manager,
    get_auth_service,
    get_config_service,
    get_magnet_service,
    get_relogin_service,
    get_sudo_nopasswd_service,
)
from aivudaos.gateway.schemas import (
    AptSourcesRestoreRequest,
    AptSourcesWriteRequest,
    AppAutostartUpdateRequest,
    ConfigUpdateRequest,
    MagnetUpdateRequest,
    SudoNopasswdUpdateRequest,
)

router = APIRouter(prefix="/api/config", tags=["config"])


def _require_auth(token: str) -> SessionInfo:
    auth: AuthService = get_auth_service()
    try:
        return auth.validate_token(token)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("/system/sudo-nopasswd")
async def get_sudo_nopasswd(token: str) -> Dict[str, Any]:
    _require_auth(token)
    service = get_sudo_nopasswd_service()
    try:
        return service.get_status()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/system/sudo-nopasswd")
async def put_sudo_nopasswd(payload: SudoNopasswdUpdateRequest, token: str) -> Dict[str, Any]:
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
async def relogin_system_user(token: str) -> Dict[str, Any]:
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
async def restart_avahi(token: str) -> Dict[str, Any]:
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


@router.get("/system/aivudaos-service")
async def get_aivudaos_service_status(token: str) -> Dict[str, Any]:
    _require_auth(token)
    service = get_aivudaos_service_manager()
    try:
        return service.get_status()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/system/aivudaos-service/autostart")
async def set_aivudaos_service_autostart(
    payload: AppAutostartUpdateRequest,
    token: str,
) -> Dict[str, Any]:
    _require_auth(token)
    service = get_aivudaos_service_manager()
    try:
        return service.set_autostart(payload.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/system/aivudaos-service/{action}")
async def trigger_aivudaos_service_action(action: str, token: str) -> Dict[str, Any]:
    _require_auth(token)
    service = get_aivudaos_service_manager()
    try:
        return service.schedule_action(action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/system/apt-sources-list")
async def get_apt_sources_list(token: str) -> Dict[str, Any]:
    _require_auth(token)
    service = get_apt_sources_service()
    try:
        return service.read_sources()
    except RuntimeError as exc:
        code = str(getattr(exc, "code", "APT_SOURCES_READ_FAILED"))
        message = str(getattr(exc, "message", str(exc)))
        status = 400 if code in {"SUDO_PASSWORD_REQUIRED"} else 500
        raise HTTPException(status_code=status, detail={"code": code, "message": message})


@router.get("/system/apt-sources-list/backups")
async def list_apt_sources_backups(token: str) -> Dict[str, Any]:
    _require_auth(token)
    service = get_apt_sources_service()
    try:
        return {
            "ok": True,
            "items": service.list_backups(),
        }
    except RuntimeError as exc:
        code = str(getattr(exc, "code", "APT_SOURCES_BACKUPS_FAILED"))
        message = str(getattr(exc, "message", str(exc)))
        raise HTTPException(status_code=500, detail={"code": code, "message": message})


@router.put("/system/apt-sources-list")
async def put_apt_sources_list(payload: AptSourcesWriteRequest, token: str) -> Dict[str, Any]:
    _require_auth(token)
    service = get_apt_sources_service()
    try:
        return service.write_sources(payload.content, sudo_password=payload.sudo_password)
    except RuntimeError as exc:
        code = str(getattr(exc, "code", "APT_SOURCES_WRITE_FAILED"))
        message = str(getattr(exc, "message", str(exc)))
        status = 400 if code in {"SUDO_PASSWORD_REQUIRED", "APT_UPDATE_FAILED", "WRITE_FAILED"} else 500
        raise HTTPException(status_code=status, detail={"code": code, "message": message})


@router.post("/system/apt-sources-list/restore")
async def restore_apt_sources_list(payload: AptSourcesRestoreRequest, token: str) -> Dict[str, Any]:
    _require_auth(token)
    service = get_apt_sources_service()
    try:
        return service.restore_backup(payload.backup_id, sudo_password=payload.sudo_password)
    except RuntimeError as exc:
        code = str(getattr(exc, "code", "APT_SOURCES_RESTORE_FAILED"))
        message = str(getattr(exc, "message", str(exc)))
        status = 400 if code in {
            "SUDO_PASSWORD_REQUIRED",
            "BACKUP_ID_REQUIRED",
            "BACKUP_NOT_FOUND",
            "APT_UPDATE_FAILED",
            "WRITE_FAILED",
        } else 500
        raise HTTPException(status_code=status, detail={"code": code, "message": message})


@router.get("")
async def get_config(token: str) -> Dict[str, Any]:
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
async def put_config(payload: ConfigUpdateRequest, token: str) -> Dict[str, Any]:
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
async def get_os_config(token: str) -> Dict[str, Any]:
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
async def put_os_config(payload: ConfigUpdateRequest, token: str) -> Dict[str, Any]:
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
async def list_magnets(token: str) -> Dict[str, Any]:
    _require_auth(token)
    magnet = get_magnet_service()
    return magnet.list_groups()


@router.put("/magnets/{group_id}")
async def update_magnet(group_id: str, payload: MagnetUpdateRequest, token: str) -> Dict[str, Any]:
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
