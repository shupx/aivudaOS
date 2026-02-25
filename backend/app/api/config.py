from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.app.schemas import ConfigUpdateRequest
from backend.app.services.auth import auth_token
from backend.app.services.config_service import get_global_config, update_global_config

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_config(token: str) -> dict[str, Any]:
    await auth_token(token)
    return get_global_config()


@router.put("")
async def put_config(payload: ConfigUpdateRequest, token: str) -> dict[str, Any]:
    user = await auth_token(token)
    return update_global_config(payload.version, payload.data, user["username"])
