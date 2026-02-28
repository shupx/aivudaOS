from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class ConfigUpdateRequest(BaseModel):
    version: int
    data: dict[str, Any]


class AppInstallRequest(BaseModel):
    install_runtime: bool = False


class AppConfigUpdateRequest(BaseModel):
    version: int
    data: dict[str, Any]


class AppAutostartUpdateRequest(BaseModel):
    enabled: bool


class AppUninstallRequest(BaseModel):
    purge: bool = False
    version: str | None = None


class AppSwitchVersionRequest(BaseModel):
    version: str
    restart: bool = False
