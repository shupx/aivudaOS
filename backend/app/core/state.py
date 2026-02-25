from __future__ import annotations

from fastapi import WebSocket

DEFAULT_USER = {"username": "admin", "password": "admin123", "role": "admin"}
TOKENS: dict[str, dict[str, str]] = {}
WS_CLIENTS: set[WebSocket] = set()
SEQ = 0
