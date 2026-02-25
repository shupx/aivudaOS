from __future__ import annotations

from fastapi import APIRouter, WebSocket

from backend.app.services.telemetry import telemetry_ws

router = APIRouter(tags=["ws"])


@router.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket) -> None:
    await telemetry_ws(ws)
