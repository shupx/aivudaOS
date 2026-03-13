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
    icon: str | None = None
    pre_install: str | None = None
    pre_uninstall: str | None = None
    update_this_version: str | None = None
    ui_index_path: str = ""
    caddyfile_config_path: str = ""
    default_config_path: str = ""
    config_schema_path: str = ""
    default_config: dict[str, Any] = field(default_factory=dict)
    config_schema: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, app_id: str, raw: dict[str, Any]) -> AppManifest:
        return cls(
            app_id=app_id,
            name=raw.get("name", app_id),
            description=raw.get("description", ""),
            version=raw.get("version", "0.0.0"),
            run=raw.get("run", {}),
            icon=raw.get("icon"),
            pre_install=raw.get("pre_install"),
            pre_uninstall=raw.get("pre_uninstall"),
            update_this_version=raw.get("update_this_version"),
            ui_index_path=str(raw.get("ui_index_path") or ""),
            caddyfile_config_path=str(raw.get("caddyfile_config_path") or ""),
            default_config_path=str(raw.get("default_config_path") or ""),
            config_schema_path=str(raw.get("config_schema_path") or ""),
            default_config=raw.get("default_config") or {},
            config_schema=raw.get("config_schema") or {},
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "app_id": self.app_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "run": self.run,
            "default_config_path": self.default_config_path,
            "config_schema_path": self.config_schema_path,
            "default_config": self.default_config,
            "config_schema": self.config_schema,
        }
        if self.pre_install is not None:
            d["pre_install"] = self.pre_install
        if self.icon is not None:
            d["icon"] = self.icon
        if self.pre_uninstall is not None:
            d["pre_uninstall"] = self.pre_uninstall
        if self.update_this_version is not None:
            d["update_this_version"] = self.update_this_version
        if self.ui_index_path:
            d["ui_index_path"] = self.ui_index_path
        if self.caddyfile_config_path:
            d["caddyfile_config_path"] = self.caddyfile_config_path
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



