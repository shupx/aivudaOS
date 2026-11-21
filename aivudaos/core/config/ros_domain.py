"""ROS 2 host detection and the shared launch-domain parameter."""
import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from aivudaos.core.config.filelock import get_lock
from aivudaos.core.config.versioned_yaml import load_revision, write_revision


DOMAIN_KEY = "ros2_default_domain_id"

_CAMEL_TO_SNAKE_RE = re.compile(r"([a-z0-9])([A-Z])")
_DOMAIN_DESC_RE = re.compile(
    r"\b(?:ros\s*2?|dds)[\s_-]*(?:domain|域)|(?:ROS\s*2?|DDS)\s*通信域",
    re.IGNORECASE,
)
_DOMAIN_KEY_RE = re.compile(r"(?:^|[_-])(?:domain|domian)(?:[_-]?id)?$")
_ROS_CONTEXT_RE = re.compile(r"(?:^|[._-])(?:ros2?|dds)(?:$|[._-])")
_INTEGER_STR_RE = re.compile(r"^-?[0-9]+$")


def is_ros_domain_field(path: str, schema: Any = None, value: Any = None) -> bool:
    """Return True if a config leaf path/schema represents a ROS 2 / DDS domain ID.

    Matches the frontend rosDomains.js discovery rules so per-algorithm domain
    parameters are never accidentally merged by MagnetService across apps.
    """
    schema_dict = schema if isinstance(schema, dict) else {}
    schema_type = schema_dict.get("type")
    types = schema_type if isinstance(schema_type, list) else [schema_type]
    if any(t in ("boolean", "array", "object") for t in types) or isinstance(value, (bool, list, dict)):
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
    if not (_DOMAIN_KEY_RE.search(words) or re.search(r"\bdomain[\s_-]*id\b", description, re.IGNORECASE)):
        return False
    context = _CAMEL_TO_SNAKE_RE.sub(r"\1_\2", ".".join(segments)).lower()
    if _ROS_CONTEXT_RE.search(context) or re.search(r"\b(?:ros\s*2?|dds)\b", description, re.IGNORECASE):
        return True
    # Unqualified IDs can be UUIDs or DNS names rather than ROS domains.
    return (any(t in ("integer", "number") for t in types)
            or isinstance(value, (int, float))
            or (isinstance(value, str) and bool(_INTEGER_STR_RE.fullmatch(value))))


def contains_ros_domain_field(path: str, schema: Any, value: Any) -> bool:
    """Magnet leaves are atomic: protect the whole leaf if it contains a domain."""
    schema = schema if isinstance(schema, dict) else {}
    if value is None:
        value = schema.get("default")
    items = schema.get("items")
    if isinstance(value, list) or isinstance(items, dict):
        # Inspect declared items even when the array is empty or not yet configured.
        entries = value if isinstance(value, list) and value else [None]
        return any(contains_ros_domain_field(f"{path}.{i}", items, item) for i, item in enumerate(entries))
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    if isinstance(value, dict) or properties:
        obj = value if isinstance(value, dict) else {}
        for key in set(properties).union(obj):
            label = obj.get("name", obj.get("key", key)) if key == "value" else key
            if contains_ros_domain_field(path + "." + str(label), properties.get(key), obj.get(key)):
                return True
        return False
    return is_ros_domain_field(path, schema, value)


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


def effective_domain(data: dict, environment: dict) -> int:
    """Read persisted legacy strings as well as integers, skipping invalid sources."""
    shared = data.get("sys")
    for value in (
        shared.get(DOMAIN_KEY) if isinstance(shared, dict) else None,
        environment.get("ROS_DOMAIN_ID") if isinstance(environment, dict) else None,
        os.environ.get("ROS_DOMAIN_ID"),
    ):
        if isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
            try:
                value = int(value)
            except ValueError:  # Oversized decimal strings are not domain IDs either.
                continue
        if type(value) is int and 0 <= value <= 232:
            return value
    return 0


def populate_default_domain(data: dict, environment: dict) -> bool:
    shared = data.setdefault("sys", {})
    if not isinstance(shared, dict):
        return False
    domain = effective_domain(data, environment)
    previous = shared.get(DOMAIN_KEY)
    changed = type(previous) is not int or previous != domain
    shared[DOMAIN_KEY] = domain
    schemas = data.setdefault("_sys_schema", {})
    path = "sys." + DOMAIN_KEY
    if isinstance(schemas, dict):
        old_schema = schemas.get(path)
        if not isinstance(old_schema, dict) or old_schema.get("type") != "integer":
            schema = {"type": "integer", "minimum": 0, "maximum": 232}
            if isinstance(old_schema, dict):
                for key in ("title", "description", "need_restart", "readOnly"):
                    if key in old_schema:
                        schema[key] = old_schema[key]
            schemas[path] = schema
            changed = True
    return changed


def ensure_ros_domain(sys_path: Path, environment: dict) -> None:
    if not has_ros2():
        return
    with get_lock(sys_path):
        cfg = load_revision(sys_path)
        if populate_default_domain(cfg.data, environment):
            write_revision(sys_path, cfg.data, cfg.version + 1, "system")
