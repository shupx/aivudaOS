from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from core.auth.models import SessionInfo
from core.auth.service import AuthService
from core.errors import AuthenticationError
from gateway.deps import get_auth_service, get_telemetry_service

router = APIRouter(prefix="/api/status", tags=["status"])


def _require_auth(token: str) -> SessionInfo:
    auth: AuthService = get_auth_service()
    try:
        return auth.validate_token(token)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("/snapshot")
async def snapshot(token: str) -> dict[str, Any]:
    _require_auth(token)
    telemetry = get_telemetry_service()
    return telemetry.snapshot()
