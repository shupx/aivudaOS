from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppManifest:
    app_id: str
    name: str
    description: str
    version: str
    runtime: str  # "host" | "docker" | "podman"
    install: dict[str, Any]
    run: dict[str, Any]
    default_config: dict[str, Any] = field(default_factory=dict)
    config_schema: dict[str, Any] | None = None
    runtime_optional: bool = False

    @classmethod
    def from_dict(cls, app_id: str, raw: dict[str, Any]) -> AppManifest:
        return cls(
            app_id=app_id,
            name=raw.get("name", app_id),
            description=raw.get("description", ""),
            version=raw.get("version", "0.0.0"),
            runtime=raw.get("runtime", "host"),
            install=raw.get("install", {}),
            run=raw.get("run", {}),
            default_config=raw.get("default_config", {}),
            config_schema=raw.get("config_schema"),
            runtime_optional=raw.get("runtime_optional", False),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "app_id": self.app_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "runtime": self.runtime,
            "install": self.install,
            "run": self.run,
            "default_config": self.default_config,
        }
        if self.config_schema is not None:
            d["config_schema"] = self.config_schema
        if self.runtime_optional:
            d["runtime_optional"] = self.runtime_optional
        return d


@dataclass
class InstalledVersion:
    app_id: str
    version: str
    runtime: str
    install_path: str
    status: str
    installed_at: int


@dataclass
class AppRuntimeState:
    app_id: str
    running: bool
    autostart: bool
    pid: int | None
    container_id: str | None
    last_started_at: int | None
    last_stopped_at: int | None



