"""ROS 2 host detection and the shared launch-domain parameter."""
import os
import shutil
import time
from pathlib import Path
from typing import Optional

import yaml

from aivudaos.core.config.filelock import atomic_write_text, get_lock


DOMAIN_KEY = "ros2_default_domain_id"


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
