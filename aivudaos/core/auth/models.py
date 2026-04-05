from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SessionInfo:
    token: str
    username: str
    role: str
    created_at: int
