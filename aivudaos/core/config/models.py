from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VersionedConfig:
    """Wraps config data with version tracking metadata."""

    data: Dict[str, Any]
    version: int = 0
    updated_at: Optional[int] = None
    updated_by: Optional[str] = None


@dataclass
class UserRecord:
    username: str
    password_hash: str
    role: str = "admin"


@dataclass
class UsersConfig:
    users: List[UserRecord] = field(default_factory=list)
