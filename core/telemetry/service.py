from __future__ import annotations

import time
from typing import Any


class TelemetryService:
    """Pure data generation for telemetry. No WebSocket dependency."""

    def __init__(self) -> None:
        self._seq = 0

    def next_payload(self) -> dict[str, Any]:
        self._seq += 1
        return {
            "seq": self._seq,
            "timestamp": int(time.time()),
            "battery": max(20, 100 - (self._seq % 80)),
            "mode": "AUTO" if self._seq % 2 == 0 else "STANDBY",
            "gps_fix": True,
            "speed_mps": round(4.5 + (self._seq % 5) * 0.3, 2),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "timestamp": int(time.time()),
            "battery": 88,
            "mode": "STANDBY",
            "gps_fix": True,
            "lat": 31.2304,
            "lon": 121.4737,
        }
