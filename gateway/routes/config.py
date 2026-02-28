from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from core.auth.models import SessionInfo
from core.auth.service import AuthService
from core.config.service import ConfigService
from core.errors import AuthenticationError, ConfigVersionConflictError
from gateway.deps import get_auth_service, get_config_service
from gateway.schemas import ConfigUpdateRequest

router = APIRouter(prefix="/api/config", tags=["config"])


def _require_auth(token: str) -> SessionInfo:
    auth: AuthService = get_auth_service()
    try:
        return auth.validate_token(token)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("")
async def get_config(token: str) -> dict[str, Any]:
    _require_auth(token)
    config: ConfigService = get_config_service()
    cfg = config.get_os_config()
    return {
        "data": cfg.data,
        "version": cfg.version,
        "updated_at": cfg.updated_at,
        "updated_by": cfg.updated_by,
    }


@router.put("")
async def put_config(payload: ConfigUpdateRequest, token: str) -> dict[str, Any]:
    user = _require_auth(token)
    config: ConfigService = get_config_service()
    try:
        result = config.update_os_config(
            payload.data, payload.version, user.username
        )
    except ConfigVersionConflictError:
        raise HTTPException(status_code=409, detail="Config version conflict")
    return {"ok": True, "version": result.version}
