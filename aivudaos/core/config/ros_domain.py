"""ROS 2 host detection and the shared launch-domain parameter."""
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Optional

import yaml

from aivudaos.core.config.filelock import atomic_write_text, get_lock


DOMAIN_KEY = "ros2_default_domain_id"

_CAMEL_TO_SNAKE_RE = re.compile(r"([a-z0-9])([A-Z])")
_DOMAIN_DESC_RE = re.compile(
    r"\b(?:ros\s*2?|dds)[\s_-]*(?:domain|域)|\bdomain[\s_-]*id\b|(?:ROS\s*2?|DDS)\s*通信域",
    re.IGNORECASE,
)
_DOMAIN_KEY_RE = re.compile(r"(?:^|[_-])(?:domain|domian)(?:[_-]?id)?$")
_ROS_OR_DDS_PREFIX_RE = re.compile(r"(?:ros2?|dds)[_-]")
_INTEGER_STR_RE = re.compile(r"^-?\d+$")


def is_ros_domain_field(path: str, schema: Any = None, value: Any = None) -> bool:
    """Return True if a config leaf path/schema represents a ROS 2 / DDS domain ID.

    Matches the frontend rosDomains.js discovery rules so per-algorithm domain
    parameters are never accidentally merged by MagnetService across apps.
    """
    schema_dict = schema if isinstance(schema, dict) else {}
    schema_type = schema_dict.get("type")
    if schema_type in ("boolean", "array", "object") or isinstance(value, bool):
        return False
    if isinstance(schema_type, list) and any(t in ("boolean", "array", "object") for t in schema_type):
        return False

    segments = [seg.strip() for seg in str(path or "").split(".") if seg.strip()]
    if not segments:
        return False
    key = segments[-1]
    if key == "id" and len(segments) >= 2 and re.fullmatch(r"(?:domain|domian)", segments[-2], re.IGNORECASE):
        key = "domain_id"

    words = _CAMEL_TO_SNAKE_RE.sub(r"\1_\2", key).lower()
    description = " ".join(
        str(part)
        for part in (schema_dict.get("title"), schema_dict.get("description"))
        if part
    )
    if schema_dict.get("x-ros-domain") is True or _DOMAIN_DESC_RE.search(description):
        return True
    if not _DOMAIN_KEY_RE.search(words):
        return False
    if words.endswith("id") or _ROS_OR_DDS_PREFIX_RE.search(words):
        return True
    return schema_type in ("integer", "number") or bool(_INTEGER_STR_RE.fullmatch(str(value if value is not None else "")))



def has_ros2() -> bool:
    return (
        os.environ.get("ROS_VERSION") == "2"
        or shutil.which("ros2") is not None
        or any(p.is_file() for p in Path("/opt/ros").glob("*/bin/ros2"))
    )


def configured_domain(data: dict) -> Optional[int]:
    shared = data.get("sys")
    if not isinstance(shared, dict) or DOMAIN_KEY not in shared:
        return None
    value = shared[DOMAIN_KEY]
    if type(value) is not int or not 0 <= value <= 232:
        raise ValueError("sys.ros2_default_domain_id must be an integer between 0 and 232")
    return value


def populate_default_domain(data: dict, environment: dict) -> bool:
    shared = data.setdefault("sys", {})
    if not isinstance(shared, dict) or DOMAIN_KEY in shared:
        return False
    legacy = os.environ.get("ROS_DOMAIN_ID", "0")
    if isinstance(environment, dict):
        legacy = environment.get("ROS_DOMAIN_ID", legacy)
    try:
        domain = int(legacy)
    except (TypeError, ValueError):
        return False
    if not 0 <= domain <= 232:
        return False
    shared[DOMAIN_KEY] = domain
    schemas = data.setdefault("_sys_schema", {})
    if isinstance(schemas, dict):
        schemas.setdefault("sys." + DOMAIN_KEY, {"type": "integer", "minimum": 0, "maximum": 232})
    return True


def ensure_ros_domain(sys_path: Path, environment: dict) -> None:
    if not has_ros2():
        return
    with get_lock(sys_path):
        data = yaml.safe_load(sys_path.read_text("utf-8")) or {}
        if populate_default_domain(data, environment):
            data["_version"] = data.get("_version", 0) + 1
            data["_updated_at"] = int(time.time())
            data["_updated_by"] = "system"
            atomic_write_text(sys_path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
