"""Startup pipeline configuration. Plans contain app IDs, never live processes.

Group order is a hard barrier; item order breaks ties between ready items.
Equal orders preserve array order. Disabled entries must still form a valid DAG,
so enabling an entry cannot reveal a previously hidden cycle or missing app.
"""

import fcntl
import heapq
import ipaddress
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import yaml

from aivudaos.core.config.filelock import atomic_write_text


class PipelineConflict(ValueError):
    """The submitted config version is not the current stored version."""


_ID = re.compile(r"[A-Za-z0-9_.-]+")
_ROS_NAME = re.compile(r"/?(?:[A-Za-z_][A-Za-z0-9_]*/)*[A-Za-z_][A-Za-z0-9_]*")
_PROBE_FIELDS = {
    "started": (), "delay": ("delay_sec",), "tcp": ("host", "port"),
    "http": ("url",), "command": ("command",), "ros2_node": ("node_name",),
    "ros2_topic": ("topic", "require_publisher"),
    "ros2_lifecycle": ("node_name", "lifecycle_state"),
}


def ros2_template() -> List[dict]:
    """Return a fresh set of empty ROS 2 groups; never assume apps are installed."""
    groups = (
        ("middleware", "Middleware & Transport"), ("hardware", "Hardware & Drivers"),
        ("perception", "Perception & Localization"), ("planning", "Planning & Control"),
        ("telemetry", "Telemetry & Tools"),
    )
    return [{"id": key, "name": name, "order": i, "mode": "parallel", "enabled": True,
             "items": []} for i, (key, name) in enumerate(groups)]


def _default_config() -> dict:
    return {"version": 0, "takeover_autostart": False, "default_profile": "default",
            "profiles": [{"name": "default", "on_failure": "abort", "groups": []}]}


def _object(value, fields, path):
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    for key in value:
        if key not in fields:
            raise ValueError(f"{path} contains an unknown field: {key!r}")
    return value


def _array(value, path):
    if not isinstance(value, list):
        raise ValueError(f"{path} must be an array")
    return value


def _text(value, path):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ValueError(f"{path} must be a nonempty string without NUL characters")
    return value


def _identifier(value, path):
    if not _ID.fullmatch(_text(value, path)) or value in (".", ".."):
        raise ValueError(f"{path} must be a valid identifier (letters, digits, '.', '_' or '-')")
    return value


def _enum(value, choices, path):
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{path} must be one of: {', '.join(choices)}")
    return value


def _integer(value, path):
    if type(value) is not int:
        raise ValueError(f"{path} must be an integer")
    return value


def _bool(value, path):
    if type(value) is not bool:
        raise ValueError(f"{path} must be a boolean")
    return value


def _duration(value, path, allow_zero=False):
    if type(value) in (int, float):
        try:
            if math.isfinite(value) and (value > 0 or (allow_zero and value == 0)):
                return value
        except OverflowError:
            pass
    bound = "nonnegative" if allow_zero else "positive"
    raise ValueError(f"{path} must be a finite {bound} number of seconds")


def normalize_readiness(value, path):
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    kind = _enum(value.get("type", "started"), _PROBE_FIELDS, f"{path}.type")
    _object(value, ("type", "timeout_sec", "interval_sec") + _PROBE_FIELDS[kind], path)
    probe = {
        "type": kind,
        "timeout_sec": _duration(value.get("timeout_sec", 30), f"{path}.timeout_sec"),
        "interval_sec": _duration(value.get("interval_sec", 1), f"{path}.interval_sec"),
    }
    if kind == "delay":
        probe["delay_sec"] = _duration(value.get("delay_sec", 1), f"{path}.delay_sec", True)
    elif kind == "tcp":
        host = _text(value.get("host", "127.0.0.1"), f"{path}.host")
        if host.lower() != "localhost":
            try:
                local = ipaddress.ip_address(host).is_loopback
            except ValueError:
                local = False
            if not local:
                raise ValueError(f"{path}.host must be localhost or a loopback IP address")
        port = _integer(value.get("port"), f"{path}.port")
        if not 1 <= port <= 65535:
            raise ValueError(f"{path}.port must be between 1 and 65535")
        probe.update(host=host, port=port)
    elif kind == "http":
        url = _text(value.get("url"), f"{path}.url")
        try:
            parsed = urlsplit(url)
            if (parsed.scheme not in ("http", "https") or not parsed.hostname or
                    parsed.port == 0 or any(c.isspace() or ord(c) < 32 for c in url)):
                raise ValueError
        except ValueError:
            raise ValueError(f"{path}.url must be a valid HTTP(S) URL") from None
        probe["url"] = url
    elif kind == "command":
        probe["command"] = _text(value.get("command"), f"{path}.command")
    elif kind.startswith("ros2_"):
        field = "topic" if kind == "ros2_topic" else "node_name"
        name = _text(value.get(field), f"{path}.{field}")
        if not _ROS_NAME.fullmatch(name):
            raise ValueError(f"{path}.{field} must be a ROS name")
        probe[field] = name
        if kind == "ros2_topic":
            probe["require_publisher"] = _bool(value.get("require_publisher", False),
                                               f"{path}.require_publisher")
        if kind == "ros2_lifecycle":
            probe["lifecycle_state"] = _text(value.get("lifecycle_state", "active"),
                                             f"{path}.lifecycle_state")
    return probe


def _item(raw, path):
    raw = _object(raw, ("app_id", "order", "enabled", "depends_on", "readiness"), path)
    deps = [_identifier(d, f"{path}.depends_on[{i}]") for i, d in enumerate(
        _array(raw.get("depends_on", []), f"{path}.depends_on"))]
    if len(set(deps)) != len(deps):
        raise ValueError(f"{path}.depends_on contains a duplicate prerequisite")
    return {
        "app_id": _identifier(raw.get("app_id"), f"{path}.app_id"),
        "order": _integer(raw.get("order", 0), f"{path}.order"),
        "enabled": _bool(raw.get("enabled", True), f"{path}.enabled"),
        "depends_on": deps, "readiness": normalize_readiness(raw.get("readiness", {}), f"{path}.readiness"),
    }


def _group(raw, path):
    raw = _object(raw, ("id", "name", "order", "mode", "enabled", "items"), path)
    group_id = _identifier(raw.get("id"), f"{path}.id")
    return {
        "id": group_id, "name": _text(raw.get("name", group_id), f"{path}.name"),
        "order": _integer(raw.get("order", 0), f"{path}.order"),
        "mode": _enum(raw.get("mode", "parallel"), ("parallel", "sequential"), f"{path}.mode"),
        "enabled": _bool(raw.get("enabled", True), f"{path}.enabled"),
        "items": [_item(v, f"{path}.items[{i}]") for i, v in enumerate(
            _array(raw.get("items"), f"{path}.items"))],
    }


def _layout(raw, path) -> Dict[str, Dict[str, float]]:
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be an object")
    result = {}
    for node_id, box in raw.items():
        _text(node_id, path)
        location = f"{path}[{node_id!r}]"
        _object(box, ("x", "y", "w", "h"), location)
        if "x" not in box or "y" not in box:
            raise ValueError(f"{location} requires x and y")
        coords = {}
        for key, value in box.items():
            try:
                finite = type(value) in (float, int) and math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite or (key in ("w", "h") and value <= 0):
                raise ValueError(f"{location}.{key} must be finite; sizes must be positive")
            coords[key] = float(value)
        result[node_id] = coords
    return result


def _profile(raw, path):
    raw = _object(raw, ("name", "on_failure", "groups", "layout"), path)
    return {
        **({"layout": _layout(raw["layout"], f"{path}.layout")} if "layout" in raw else {}),
        "name": _text(raw.get("name"), f"{path}.name"),
        "on_failure": _enum(raw.get("on_failure", "abort"), ("abort", "skip_dependents", "continue"),
                            f"{path}.on_failure"),
        "groups": [_group(v, f"{path}.groups[{i}]") for i, v in enumerate(
            _array(raw.get("groups"), f"{path}.groups"))],
    }


def _batches(group, owners, group_idx):
    # Rank is the stable (order, array index) tie-breaker. Same-group edges are
    # scheduled here; preceding group barriers already satisfy cross-group edges.
    items = sorted(group["items"], key=lambda x: x["order"])
    rank = {item["app_id"]: i for i, item in enumerate(items)}
    incoming = [0] * len(items)
    followers = [[] for _ in items]
    for i, item in enumerate(items):
        app = item["app_id"]
        for dep in item["depends_on"]:
            if dep == app:
                raise ValueError(f"App {app!r} cannot depend on itself")
            if dep not in owners:
                raise ValueError(f"App {app!r} has unknown prerequisite {dep!r}")
            dep_group, dep_enabled = owners[dep]
            if dep_group > group_idx:
                raise ValueError(f"App {app!r} depends on {dep!r} in a later group")
            if group["enabled"] and item["enabled"] and not dep_enabled:
                raise ValueError(f"Enabled app {app!r} depends on disabled prerequisite {dep!r}")
            if dep_group == group_idx:
                followers[rank[dep]].append(i)
                incoming[i] += 1

    ready = [i for i, count in enumerate(incoming) if count == 0]
    batches = []
    visited = 0
    while ready:
        if group["mode"] == "sequential":
            wave = [heapq.heappop(ready)]
        else:
            wave, ready = sorted(ready), []
        batch = []
        for i in wave:
            visited += 1
            if items[i]["enabled"]:
                batch.append(items[i]["app_id"])
            for j in followers[i]:
                incoming[j] -= 1
                if incoming[j] == 0:
                    heapq.heappush(ready, j)
        if batch:
            batches.append(batch)
    if visited != len(items):
        raise ValueError(f"Dependency cycle in group {group['id']!r}")
    return batches


def _plan(profile):
    groups = sorted(profile["groups"], key=lambda g: g["order"])
    owners = {}
    ids = set()
    for n, group in enumerate(groups):
        if group["id"] in ids:
            raise ValueError(f"Duplicate group id {group['id']!r}")
        ids.add(group["id"])
        for item in group["items"]:
            app = item["app_id"]
            if app in owners:
                raise ValueError(f"Duplicate app_id {app!r} in profile {profile['name']!r}")
            owners[app] = (n, group["enabled"] and item["enabled"])
    stages = []
    for n, group in enumerate(groups):
        batches = _batches(group, owners, n)
        if group["enabled"]:
            stages.append({"group_id": group["id"], "batches": batches})
    return stages


def build_execution_plan(profile: dict) -> List[dict]:
    """Return enabled groups and topological batches; raise ValueError on invalid input."""
    return _plan(_profile(profile, "profile"))


def build_stop_plan(profile: dict) -> List[dict]:
    """Reverse start order, including the deterministic order inside each batch."""
    return [{"group_id": stage["group_id"], "batches": [b[::-1] for b in reversed(stage["batches"])]}
            for stage in reversed(build_execution_plan(profile))]


def _config(raw, check_graph=True) -> Tuple[dict, dict, List[str]]:
    raw = _object(raw, ("version", "takeover_autostart", "default_profile", "profiles"), "config")
    version = _integer(raw.get("version"), "config.version")
    if version < 0:
        raise ValueError("config.version must not be negative")
    default = _text(raw.get("default_profile"), "config.default_profile")
    takeover = _bool(raw.get("takeover_autostart", False), "config.takeover_autostart")
    profiles, seen, preview, errors = [], set(), {}, []
    for i, raw_profile in enumerate(_array(raw.get("profiles"), "config.profiles")):
        path = f"config.profiles[{i}]"
        try:
            profile = _profile(raw_profile, path)
            name = profile["name"]
            if name in seen:
                raise ValueError(f"Duplicate profile name {name!r}")
            seen.add(name)
            profiles.append(profile)
            if check_graph:
                preview[name] = _plan(profile)
        except ValueError as exc:
            errors.append(str(exc))
    if default not in seen:
        errors.append("config.default_profile must name an existing profile")
    return ({"version": version, "default_profile": default, "takeover_autostart": takeover,
             "profiles": profiles}, preview, errors)


def validate_config(config: dict) -> Dict[str, Any]:
    """Validate without mutating or writing; invalid configs have no executable preview."""
    try:
        _, preview, errors = _config(config)
    except ValueError as exc:
        preview, errors = {}, [str(exc)]
    return {"valid": not errors, "errors": errors, "preview": {} if errors else preview}


def _checked(raw, check_graph=True):
    config, _, errors = _config(raw, check_graph=check_graph)
    if errors:
        raise ValueError("; ".join(errors))
    return config


class PipelineStore:
    """Versioned YAML store. Readers see only old or new, complete snapshots."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self, *, for_editing=False) -> dict:
        """Never execute an invalid DAG, but let the editor diagnose and repair one."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _default_config()
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid pipeline YAML: {exc}") from exc
        return _checked(raw, check_graph=not for_editing)

    def save(self, config: dict, before_replace: Optional[Callable[[dict, dict], None]] = None) -> dict:
        """Compare and increment version; return the normalized saved snapshot.

        before_replace(old, new) runs under the writer lock only after a successful
        version check. If it raises, the file is unchanged. Its caller owns any
        rollback of external effects, including if atomic replacement later fails.
        The callback must not re-enter save() on this path.
        """
        new = _checked(config)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Lock a stable sidecar, not the YAML inode that os.replace() exchanges.
        lock_path = self.path.with_name(self.path.name + ".lock")
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            old = self.load(for_editing=True)
            if new["version"] != old["version"]:
                raise PipelineConflict(f"Pipeline version conflict: submitted {new['version']}, "
                                       f"current {old['version']}")
            new["version"] += 1
            text = yaml.safe_dump(new, allow_unicode=True, sort_keys=False)
            if before_replace is not None:
                before_replace(old, deepcopy(new))
            atomic_write_text(self.path, text)
        return new
