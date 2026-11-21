"""YAML representation shared by config saves and in-place migrations."""
import time
from pathlib import Path
from typing import Any, Dict

import yaml

from aivudaos.core.config.filelock import atomic_write_text
from aivudaos.core.config.models import VersionedConfig


def load_revision(path: Path) -> VersionedConfig:
    raw = yaml.safe_load(path.read_text('utf-8')) or {}
    version = raw.pop('_version', 0)
    updated_at = raw.pop('_updated_at', None)
    updated_by = raw.pop('_updated_by', None)
    return VersionedConfig(data=raw, version=version, updated_at=updated_at, updated_by=updated_by)


def write_revision(path: Path, data: Dict[str, Any], version: int, updated_by: str) -> VersionedConfig:
    """Write a known revision; callers hold the path lock for read/modify/write."""
    now = int(time.time())
    raw = {'_version': version, '_updated_at': now, '_updated_by': updated_by, **data}
    atomic_write_text(path, yaml.safe_dump(raw, default_flow_style=False, allow_unicode=True))
    return VersionedConfig(data=data, version=version, updated_at=now, updated_by=updated_by)
