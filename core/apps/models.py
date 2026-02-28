from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppManifest:
    app_id: str
    name: str
    description: str
    version: str
    run: dict[str, Any]
    default_config: dict[str, Any] = field(default_factory=dict)
    config_schema: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, app_id: str, raw: dict[str, Any]) -> AppManifest:
        return cls(
            app_id=app_id,
            name=raw.get("name", app_id),
            description=raw.get("description", ""),
            version=raw.get("version", "0.0.0"),
            run=raw.get("run", {}),
            default_config=raw.get("default_config", {}),
            config_schema=raw.get("config_schema"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "app_id": self.app_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "run": self.run,
            "default_config": self.default_config,
        }
        if self.config_schema is not None:
            d["config_schema"] = self.config_schema
        return d


@dataclass
class InstalledVersion:
    app_id: str
    version: str
    install_path: str
    status: str
    installed_at: int


@dataclass
class AppRuntimeState:
    app_id: str
    running: bool
    autostart: bool
    pid: int | None
    last_started_at: int | None
    last_stopped_at: int | None



