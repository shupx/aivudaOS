from __future__ import annotations

import json
import time
from copy import deepcopy
from dataclasses import dataclass
from functools import cached_property
from threading import Lock
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from aivudaos.core.apps.config_validation import validate_config_data
from aivudaos.core.apps.device_network import NetworkSnapshot
from aivudaos.core.apps.network_schema import device_ipv4_fields
from aivudaos.core.apps.versioning import VersioningService
from aivudaos.core.config.filelock import atomic_write_text, get_lock
from aivudaos.core.config.models import VersionedConfig
from aivudaos.core.config.ros_domain import contains_ros_domain_field
from aivudaos.core.config.service import ConfigService
from aivudaos.core.db.connection import db_conn
from aivudaos.core.errors import ConfigVersionConflictError, InvalidConfigError, NotFoundError
from aivudaos.core.paths import MAGNET_CONFIG_PATH


@dataclass
class _AppDefinition:
    schema: Dict[str, Any]
    defaults: Dict[str, Any]

    @cached_property
    def leaves(self) -> Dict[str, Dict[str, Any]]:
        return _flatten_schema_leaves(self.schema)


class MagnetService:
    """Shared parameter groups across active apps and os config."""

    def __init__(self, config_service: ConfigService, versioning_service: VersioningService) -> None:
        self._config = config_service
        self._versioning = versioning_service
        self._write_lock = Lock()  # Serialize registry changes and their dependent app writes.

    def list_groups(self) -> Dict[str, Any]:
        cfg = self._read_registry()
        data = cfg.data
        return {
            "items": list(data.get("groups") or []),
            "conflicts": list(data.get("conflicts") or []),
            "version": cfg.version,
            "updated_at": cfg.updated_at,
            "updated_by": cfg.updated_by,
        }

    def readonly_paths_for_app(self, app_id: str, app_version: str) -> Set[str]:
        return app_binding_paths(self.list_groups()["items"]).get((app_id, app_version), set())

    def readonly_paths_for_sys(self) -> Set[str]:
        groups = self.list_groups().get("items") or []
        readonly: Set[str] = set()
        for group in groups:
            if not isinstance(group, dict):
                continue
            for binding in group.get("bindings") or []:
                if not isinstance(binding, dict):
                    continue
                if binding.get("kind") == "sys":
                    path = str(binding.get("path") or "").strip()
                    if path:
                        readonly.add(path)
        return readonly

    def blocked_paths_for_app_update(
        self,
        app_id: str,
        app_version: str,
        before_data: Dict[str, Any],
        after_data: Dict[str, Any],
    ) -> List[str]:
        blocked: List[str] = []
        for path in sorted(self.readonly_paths_for_app(app_id, app_version)):
            if _nested_get(before_data, path) != _nested_get(after_data, path):
                blocked.append(path)
        return blocked

    def blocked_paths_for_sys_update(
        self,
        before_data: Dict[str, Any],
        after_data: Dict[str, Any],
    ) -> List[str]:
        blocked: List[str] = []
        for path in sorted(self.readonly_paths_for_sys()):
            if _nested_get(before_data, path) != _nested_get(after_data, path):
                blocked.append(path)
        return blocked

    def recompute(self, updated_by: str = "system", *, network: Optional[NetworkSnapshot] = None) -> Dict[str, Any]:
        with self._write_lock:
            return self._recompute(updated_by, network or NetworkSnapshot())

    def _recompute(self, updated_by: str, network: NetworkSnapshot) -> Dict[str, Any]:
        current = self._read_registry()
        definitions = {key: self._app_definition(*key) for key in self._list_active_apps()}
        self._ensure_sys_parameters_for_app_sys_paths(updated_by, definitions)
        previous_groups = {
            str(g.get("path")): g
            for g in (current.data.get("groups") or [])
            if isinstance(g, dict) and g.get("path")
        }

        discovered = self._collect_candidates(definitions)
        next_groups: List[Dict[str, Any]] = []
        conflicts: List[Dict[str, Any]] = []

        for path, entries in sorted(discovered.items(), key=lambda item: item[0]):
            if len(entries) < 2:
                continue

            compatible, reason = _is_compatible(entries)
            if not compatible:
                conflicts.append(
                    {
                        "path": path,
                        "reason": reason,
                        "bindings": [_binding_of(item) for item in entries],
                    }
                )
                continue

            previous = previous_groups.get(path)
            value = self._pick_value(entries, previous)
            # A version may narrow a constraint without changing the field type.
            # Keep migrated values when the previous shared value is no longer
            # valid, rather than failing activation or partially applying a group.
            try:
                for entry in entries:
                    _require_non_domain_values(entry["domain_path"], entry.get("schema"), value)
                    validate_config_data(value, entry.get("schema"), previous_data=entry.get("saved_value"), network=network)
            except InvalidConfigError as exc:
                conflicts.append({
                    "path": path,
                    "reason": str(exc),
                    "bindings": [_binding_of(item) for item in entries],
                })
                continue
            value_type = _infer_type_name(value)
            bindings = [_binding_of(item) for item in entries]
            group_id = _stable_group_id(path)
            next_groups.append(
                {
                    "group_id": group_id,
                    "path": path,
                    "value": value,
                    "value_type": value_type,
                    "bindings": bindings,
                }
            )

        bound_paths = app_binding_paths(next_groups)
        for group in next_groups:
            self._apply_group_value(group, updated_by, bound_paths, network, definitions)

        updated = self._write_registry(
            {
                "groups": next_groups,
                "conflicts": conflicts,
            },
            expected_version=current.version,
            updated_by=updated_by,
        )

        return {
            "ok": True,
            "groups": len(next_groups),
            "conflicts": len(conflicts),
            "version": updated.version,
        }

    def update_group_value(
        self,
        group_id: str,
        value: Any,
        expected_version: int,
        updated_by: str,
    ) -> Dict[str, Any]:
        with self._write_lock:
            return self._update_group_value(group_id, value, expected_version, updated_by)

    def _update_group_value(
        self, group_id: str, value: Any, expected_version: int, updated_by: str,
    ) -> Dict[str, Any]:
        current = self._read_registry()
        if expected_version != current.version:
            raise ConfigVersionConflictError(
                f"Magnet config version conflict, expected {expected_version}, current {current.version}"
            )
        groups = list(current.data.get("groups") or [])

        target_index = -1
        for idx, group in enumerate(groups):
            if isinstance(group, dict) and str(group.get("group_id") or "") == group_id:
                target_index = idx
                break

        if target_index < 0:
            raise NotFoundError(f"Magnet group not found: {group_id}")

        target = dict(groups[target_index])
        target_type = str(target.get("value_type") or "")
        if target_type and target_type != _infer_type_name(value):
            raise InvalidConfigError(
                f"Magnet value type mismatch, expected {target_type}"
            )

        target["value"] = value
        groups[target_index] = target

        self._apply_group_value(target, updated_by, app_binding_paths(groups), NetworkSnapshot())

        updated = self._write_registry(
            {
                "groups": groups,
                "conflicts": list(current.data.get("conflicts") or []),
            },
            expected_version=expected_version,
            updated_by=updated_by,
        )

        return {
            "ok": True,
            "group_id": group_id,
            "version": updated.version,
        }

    def _app_definition(self, app_id: str, version: str, *, need_defaults: bool = True) -> _AppDefinition:
        manifest = self._get_manifest(app_id, version)
        defaults = self._config.get_app_default_config(
            app_id, version, fallback=manifest.get("default_config") or {},
        ) if need_defaults else {}
        return _AppDefinition(manifest.get("config_schema") or {}, defaults)

    def _ensure_sys_parameters_for_app_sys_paths(self, updated_by: str, definitions: Dict[Tuple[str, str], _AppDefinition]) -> None:
        sys_cfg = self._config.get_sys_config()
        sys_data = deepcopy(sys_cfg.data)
        sys_schema_map = _read_sys_schema_map(sys_data)
        changed = False

        for (app_id, app_version), definition in definitions.items():
            app_cfg = self._config.get_app_config(app_id, app_version)
            defaults = definition.defaults
            current_data = app_cfg.data if app_cfg.version > 0 else {}

            for path, leaf_schema in definition.leaves.items():
                if not path.startswith("sys."):
                    continue
                domain_path = _domain_field_path(path, current_data, defaults)
                if _app_leaf_contains_domain(domain_path, leaf_schema, _nested_get(current_data, path), _nested_get(defaults, path)):
                    continue

                if not _nested_has(sys_data, path):
                    if _nested_has(current_data, path):
                        value = _nested_get(current_data, path)
                    elif _nested_has(defaults, path):
                        value = _nested_get(defaults, path)
                    elif isinstance(leaf_schema, dict) and "default" in leaf_schema:
                        value = leaf_schema.get("default")
                    else:
                        value = _schema_default_for_type(leaf_schema)
                    _nested_set(sys_data, path, deepcopy(value))
                    changed = True

                if path not in sys_schema_map:
                    sys_schema_map[path] = deepcopy(leaf_schema)
                    changed = True

        if not changed:
            return

        _write_sys_schema_map(sys_data, sys_schema_map)
        self._config.update_sys_config(
            sys_data,
            expected_version=sys_cfg.version,
            username=updated_by,
        )

    def _pick_value(
        self,
        entries: List[Dict[str, Any]],
        previous_group: Optional[Dict[str, Any]],
    ) -> Any:
        if previous_group and "value" in previous_group:
            return previous_group.get("value")

        for item in entries:
            if item.get("kind") == "sys":
                return item.get("value")

        return entries[0].get("value")

    def _collect_candidates(self, definitions: Dict[Tuple[str, str], _AppDefinition]) -> Dict[str, List[Dict[str, Any]]]:
        discovered: Dict[str, List[Dict[str, Any]]] = {}

        sys_cfg = self._config.get_sys_config().data
        sys_schema_map = _read_sys_schema_map(sys_cfg)
        for path in _flatten_leaf_paths(sys_cfg):
            value = _nested_get(sys_cfg, path)
            schema = sys_schema_map.get(path)
            domain_path = _domain_field_path(path, sys_cfg)
            if contains_ros_domain_field(domain_path, schema, value):
                continue
            inferred_type = _extract_schema_type(schema) or _infer_type_name(value)
            discovered.setdefault(path, []).append(
                {
                    "kind": "sys",
                    "path": path,
                    "domain_path": domain_path,
                    "saved_value": value,
                    "value": value,
                    "schema": schema,
                    "type_name": inferred_type,
                }
            )

        for (app_id, app_version), definition in definitions.items():
            app_cfg = self._config.get_app_config(app_id, app_version)
            defaults = definition.defaults
            source = app_cfg.data if app_cfg.version > 0 else defaults

            for path, leaf_schema in definition.leaves.items():
                value = _nested_get(source, path)
                domain_path = _domain_field_path(path, source, defaults)
                if _app_leaf_contains_domain(domain_path, leaf_schema, value, _nested_get(defaults, path)):
                    continue
                inferred_type = _extract_schema_type(leaf_schema) or _infer_type_name(value)
                discovered.setdefault(path, []).append(
                    {
                        "kind": "app",
                        "app_id": app_id,
                        "app_version": app_version,
                        "path": path,
                        "domain_path": domain_path,
                        "saved_value": value if app_cfg.version > 0 else None,
                        "schema": leaf_schema,
                        "value": value,
                        "type_name": inferred_type,
                    }
                )

        return discovered

    def _apply_group_value(
        self, group: Dict[str, Any], updated_by: str,
        bound_paths: Dict[Tuple[str, str], Set[str]], network: NetworkSnapshot,
        definitions: Optional[Dict[Tuple[str, str], _AppDefinition]] = None,
    ) -> None:
        value = group.get("value")
        app_updates = []
        sys_update = None
        for binding in group.get("bindings") or []:
            if not isinstance(binding, dict) or not binding.get("path"):
                continue
            path = binding["path"]
            if binding.get("kind") == "sys":
                cfg = self._config.get_sys_config()
                _require_non_domain_values(_domain_field_path(path, cfg.data), _read_sys_schema_map(cfg.data).get(path),
                                           _nested_get(cfg.data, path), value)
                if not _nested_has(cfg.data, path) or _nested_get(cfg.data, path) != value:
                    data = deepcopy(cfg.data)
                    _nested_set(data, path, value)
                    sys_update = (data, cfg.version)
                continue
            if binding.get("kind") != "app":
                continue
            app_id, version = binding.get("app_id"), binding.get("app_version")
            if not app_id or not version:
                continue
            cfg = self._config.get_app_config(app_id, version)
            definition = (definitions[(app_id, version)] if definitions is not None
                          else self._app_definition(app_id, version, need_defaults=not cfg.version))
            schema = definition.schema
            before = cfg.data if cfg.version else definition.defaults
            leaf_schema = _nested_get(schema, "properties." + path.replace(".", ".properties."))
            _require_non_domain_values(_domain_field_path(path, before), leaf_schema, _nested_get(before, path), value)
            if _nested_has(before, path) and _nested_get(before, path) == value:
                continue  # Recompute must not clear an intentionally selected source address.
            data = deepcopy(before)
            _nested_set(data, path, value)
            _reset_network_source(data, schema, path, bound_paths[(app_id, version)])
            validate_config_data(
                data, schema, previous_data=cfg.data if cfg.version > 0 else None,
                network=network, context=f"magnet {app_id}@{version}",
            )
            app_updates.append((app_id, version, data, cfg.version))

        # Validate all recipients before a rejected edit can modify the first app.
        if sys_update is not None:
            self._config.update_sys_config(*sys_update, username=updated_by)
        for app_id, version, data, revision in app_updates:
            self._config.update_app_config(app_id, version, data, revision, updated_by=updated_by)

    def _read_registry(self) -> VersionedConfig:
        path = MAGNET_CONFIG_PATH
        lock = get_lock(path)
        with lock:
            if not path.exists():
                return VersionedConfig(data={"groups": [], "conflicts": []}, version=0)
            raw = yaml.safe_load(path.read_text("utf-8")) or {}

        version = int(raw.pop("_version", 0) or 0)
        updated_at = raw.pop("_updated_at", None)
        updated_by = raw.pop("_updated_by", None)
        groups = raw.get("groups") if isinstance(raw.get("groups"), list) else []
        conflicts = raw.get("conflicts") if isinstance(raw.get("conflicts"), list) else []

        return VersionedConfig(
            data={"groups": groups, "conflicts": conflicts},
            version=version,
            updated_at=updated_at,
            updated_by=updated_by,
        )

    def _write_registry(
        self,
        data: Dict[str, Any],
        expected_version: int,
        updated_by: str,
    ) -> VersionedConfig:
        path = MAGNET_CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)

        lock = get_lock(path)
        with lock:
            if path.exists():
                current_raw = yaml.safe_load(path.read_text("utf-8")) or {}
                current_version = int(current_raw.get("_version", 0) or 0)
            else:
                current_version = 0

            if expected_version != current_version:
                raise ConfigVersionConflictError(
                    f"Magnet config version conflict, expected {expected_version}, current {current_version}"
                )

            next_version = current_version + 1
            now = int(time.time())
            to_write = {
                "_version": next_version,
                "_updated_at": now,
                "_updated_by": updated_by,
                "groups": list(data.get("groups") or []),
                "conflicts": list(data.get("conflicts") or []),
            }
            atomic_write_text(
                path,
                yaml.dump(to_write, default_flow_style=False, allow_unicode=True),
            )

        return VersionedConfig(
            data={
                "groups": list(data.get("groups") or []),
                "conflicts": list(data.get("conflicts") or []),
            },
            version=next_version,
            updated_at=now,
            updated_by=updated_by,
        )

    def _list_active_apps(self) -> List[Tuple[str, str]]:
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT app_id, version FROM app_installation ORDER BY app_id, installed_at DESC"
            ).fetchall()

        latest_by_app: Dict[str, str] = {}
        for row in rows:
            app_id = str(row["app_id"])
            if app_id in latest_by_app:
                continue
            latest_by_app[app_id] = str(row["version"])

        active: List[Tuple[str, str]] = []
        for app_id, fallback in latest_by_app.items():
            ver = self._versioning.active_version(app_id) or fallback
            if ver:
                active.append((app_id, ver))
        return active

    def _get_manifest(self, app_id: str, app_version: str) -> Dict[str, Any]:
        with db_conn() as conn:
            row = conn.execute(
                "SELECT manifest FROM app_installation WHERE app_id = ? AND version = ? LIMIT 1",
                (app_id, app_version),
            ).fetchone()
        if not row or not row["manifest"]:
            raise NotFoundError(f"Manifest not found: {app_id}@{app_version}")
        return json.loads(str(row["manifest"]))


def _require_non_domain_values(path: str, schema: Any, *values: Any) -> None:
    if any(contains_ros_domain_field(path, schema, value) for value in values):
        raise InvalidConfigError(f"Cannot synchronize ROS domain parameters at {path}")


def _domain_field_path(path: str, *sources: dict) -> str:
    parent, _, key = path.rpartition(".")
    if key == "value":  # name/value or key/value environment records
        for data in sources:
            record = _nested_get(data, parent) if parent else data
            if isinstance(record, dict):
                label = record.get("name") or record.get("key")
                if isinstance(label, str):
                    return parent + "." + label if parent else label
    return path


def _app_leaf_contains_domain(path: str, schema: dict, value: Any, default: Any) -> bool:
    if contains_ros_domain_field(path, schema, value if value is not None else default):
        return True
    # An emptied array may still contain domains in the package configuration.
    return isinstance(default, list) and default != value and contains_ros_domain_field(path, schema, default)


def _flatten_schema_leaves(schema: Any, parent: str = "") -> Dict[str, Dict[str, Any]]:
    if not isinstance(schema, dict):
        return {}

    schema_type = schema.get("type")
    props = schema.get("properties")
    output: Dict[str, Dict[str, Any]] = {}

    if (schema_type == "object" or isinstance(props, dict)) and isinstance(props, dict):
        for key, child in props.items():
            if not isinstance(child, dict):
                continue
            path = f"{parent}.{key}" if parent else str(key)
            output.update(_flatten_schema_leaves(child, path))
        return output

    if parent:
        output[parent] = schema
    return output


def _flatten_leaf_paths(data: Any, parent: str = "") -> List[str]:
    if not isinstance(data, dict):
        return [parent] if parent else []

    paths: List[str] = []
    for key, value in data.items():
        if str(key).startswith("_"):
            continue
        path = f"{parent}.{key}" if parent else str(key)
        if isinstance(value, dict):
            paths.extend(_flatten_leaf_paths(value, path))
        else:
            paths.append(path)
    return paths


def _nested_get(data: Any, dotted_path: str) -> Any:
    current = data
    for part in str(dotted_path).split("."):
        key = part.strip()
        if not key:
            return None
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _nested_has(data: Any, dotted_path: str) -> bool:
    current = data
    for part in str(dotted_path).split("."):
        key = part.strip()
        if not key:
            return False
        if not isinstance(current, dict) or key not in current:
            return False
        current = current[key]
    return True


def _nested_set(data: Dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = [part.strip() for part in str(dotted_path).split(".") if part.strip()]
    if not parts:
        return

    cursor: Dict[str, Any] = data
    for part in parts[:-1]:
        item = cursor.get(part)
        if not isinstance(item, dict):
            item = {}
            cursor[part] = item
        cursor = item
    cursor[parts[-1]] = value


def _is_compatible(items: List[Dict[str, Any]]) -> Tuple[bool, str]:
    types = {str(item.get("type_name") or "unknown") for item in items}
    if len(types) <= 1:
        return True, ""
    if "unknown" in types and len(types) == 2:
        return True, ""
    return False, f"type mismatch: {sorted(types)}"


def _extract_schema_type(schema: Any) -> str:
    if not isinstance(schema, dict):
        return ""
    type_value = schema.get("type")
    if isinstance(type_value, str):
        return type_value
    if isinstance(type_value, list):
        for item in type_value:
            if isinstance(item, str):
                return item
    return ""


def _infer_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def app_binding_paths(groups: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Set[str]]:
    paths: Dict[Tuple[str, str], Set[str]] = {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        for binding in group.get("bindings") or []:
            if not isinstance(binding, dict) or binding.get("kind") != "app":
                continue
            key = (binding.get("app_id"), binding.get("app_version"))
            path = str(binding.get("path") or "").strip()
            if path and all(key):
                paths.setdefault(key, set()).add(path)
    return paths


def _reset_network_source(data: Dict[str, Any], schema: Dict[str, Any], path: str, bound: Set[str]) -> None:
    group, _, field = path.partition(".")
    props = schema.get("properties")
    fields = device_ipv4_fields(props.get(group)) if isinstance(props, dict) else None
    if fields is None:
        return
    nic, addr, dest = fields
    if field in (nic, dest) and group not in bound and f"{group}.{addr}" not in bound:
        data[group][addr] = "auto"


def _binding_of(item: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(item.get("kind") or "")
    path = str(item.get("path") or "")
    if kind == "sys":
        return {"kind": "sys", "path": path}
    return {
        "kind": "app",
        "app_id": str(item.get("app_id") or ""),
        "app_version": str(item.get("app_version") or ""),
        "path": path,
    }


def _stable_group_id(path: str) -> str:
    safe = path.replace(".", "__")
    return f"magnet__{safe}"


def _schema_default_for_type(schema: Any) -> Any:
    schema_type = _extract_schema_type(schema)
    if schema_type == "string":
        return ""
    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0
    if schema_type == "boolean":
        return False
    if schema_type == "array":
        return []
    if schema_type == "object":
        return {}
    if schema_type == "null":
        return None
    return None


def _read_sys_schema_map(sys_cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = sys_cfg.get("_sys_schema")
    if not isinstance(raw, dict):
        return {}

    output: Dict[str, Dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        if not isinstance(value, dict):
            continue
        output[key] = value
    return output


def _write_sys_schema_map(sys_cfg: Dict[str, Any], schema_map: Dict[str, Dict[str, Any]]) -> None:
    if schema_map:
        sys_cfg["_sys_schema"] = dict(schema_map)
    elif "_sys_schema" in sys_cfg:
        del sys_cfg["_sys_schema"]
