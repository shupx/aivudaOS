from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.app.services.auth import auth_token
from backend.app.services.telemetry import snapshot_payload

router = APIRouter(prefix="/api/status", tags=["status"])


@router.get("/snapshot")
async def snapshot(token: str) -> dict[str, Any]:
    await auth_token(token)
    return snapshot_payload()
