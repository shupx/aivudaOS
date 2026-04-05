from __future__ import annotations

from typing import Any, Optional

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


class MagnetUpdateRequest(BaseModel):
    version: int
    value: Any


class SudoNopasswdUpdateRequest(BaseModel):
    enabled: bool
    sudo_password: Optional[str] = None


class AptSourcesWriteRequest(BaseModel):
    content: str
    sudo_password: Optional[str] = None


class AptSourcesRestoreRequest(BaseModel):
    backup_id: str
    sudo_password: Optional[str] = None


class AppConfigUpdateRequest(BaseModel):
    version: int
    data: dict[str, Any]
    app_version: Optional[str] = None


class AppAutostartUpdateRequest(BaseModel):
    enabled: bool


class AppUninstallRequest(BaseModel):
    purge: bool = False
    version: Optional[str] = None


class AppSwitchVersionRequest(BaseModel):
    version: str
    restart: bool = False


class AppUpdateThisVersionRequest(BaseModel):
    version: str
