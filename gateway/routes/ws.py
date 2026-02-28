from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from gateway.deps import get_auth_service, get_telemetry_service

router = APIRouter(tags=["ws"])

WS_CLIENTS: set[WebSocket] = set()


@router.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket) -> None:
    token = ws.query_params.get("token", "")
    auth = get_auth_service()
    try:
        auth.validate_token(token)
    except Exception:
        await ws.close(code=1008)
        return

    await ws.accept()
    WS_CLIENTS.add(ws)
    try:
        while True:
            _ = await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        WS_CLIENTS.discard(ws)


async def telemetry_broadcast_loop() -> None:
    telemetry = get_telemetry_service()
    while True:
        await asyncio.sleep(1)
        if not WS_CLIENTS:
            continue
        payload = telemetry.next_payload()
        dead: list[WebSocket] = []
        for client in WS_CLIENTS:
            try:
                await client.send_json(payload)
            except Exception:
                dead.append(client)
        for client in dead:
            WS_CLIENTS.discard(client)
