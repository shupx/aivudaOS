from __future__ import annotations

import asyncio
import time

from fastapi import WebSocket, WebSocketDisconnect

from backend.app.core.state import TOKENS, WS_CLIENTS
import backend.app.core.state as state


async def telemetry_ws(ws: WebSocket) -> None:
    token = ws.query_params.get("token", "")
    if token not in TOKENS:
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


async def telemetry_loop() -> None:
    while True:
        await asyncio.sleep(1)
        if not WS_CLIENTS:
            continue
        state.SEQ += 1
        payload = {
            "seq": state.SEQ,
            "timestamp": int(time.time()),
            "battery": max(20, 100 - (state.SEQ % 80)),
            "mode": "AUTO" if state.SEQ % 2 == 0 else "STANDBY",
            "gps_fix": True,
            "speed_mps": round(4.5 + (state.SEQ % 5) * 0.3, 2),
        }
        dead: list[WebSocket] = []
        for client in WS_CLIENTS:
            try:
                await client.send_json(payload)
            except Exception:
                dead.append(client)
        for client in dead:
            WS_CLIENTS.discard(client)


def snapshot_payload() -> dict[str, object]:
    now = int(time.time())
    return {
        "timestamp": now,
        "battery": 88,
        "mode": "STANDBY",
        "gps_fix": True,
        "lat": 31.2304,
        "lon": 121.4737,
    }
