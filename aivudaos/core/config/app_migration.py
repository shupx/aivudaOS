"""Best-effort parameter migration using the same schema rules as app startup."""
from copy import deepcopy
from typing import Any, Dict, List, Tuple

from aivudaos.core.apps.config_validation import validate_config_data
from aivudaos.core.errors import InvalidConfigError

_MISSING = object()


def migrate_app_parameters(
    source: Dict[str, Any], target: Dict[str, Any], defaults: Dict[str, Any],
    schema: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, str]], bool]:
    warnings: List[Dict[str, str]] = []

    def warn(path: str, origin: str, reason: str, action: str = "fallback") -> Dict[str, str]:
        item = {"path": path, "source": origin, "reason": reason, "action": action}
        if item not in warnings:
            warnings.append(item)
        return item

    def visit(candidates: List[Tuple[str, Any]], node: Dict[str, Any], path: str) -> Any:
        rejected: List[Dict[str, str]] = []

        def resolve(action: str) -> None:
            for item in rejected:
                item["action"] = action

        for index, (origin, value) in enumerate(candidates):
            if value is _MISSING:
                continue
            if isinstance(value, dict) and "enum" not in node:
                # Check the container type before salvaging its children. Required
                # fields and object enums are checked after recursive merging.
                shallow = {k: v for k, v in node.items() if k not in ("properties", "required", "enum", "additionalProperties")}
                try:
                    validate_config_data(value, shallow)
                except InvalidConfigError as exc:
                    rejected.append(warn(path, origin, str(exc)))
                    continue
                objects = [(name, item) for name, item in candidates[index:] if isinstance(item, dict)]
                properties = node.get("properties")
                properties = properties if isinstance(properties, dict) else {}
                keys = list(dict.fromkeys(key for _, item in objects for key in item))
                result = {}
                for key in keys:
                    child_path = "%s.%s" % (path, key)
                    if node.get("additionalProperties") is False and isinstance(node.get("properties"), dict) and key not in properties:
                        for name, item in objects:
                            if key in item:
                                warn(child_path, name, "Field is not allowed by target schema", "skipped")
                        continue
                    child_schema = properties.get(key)
                    child_schema = child_schema if isinstance(child_schema, dict) else {}
                    child = visit([(name, item.get(key, _MISSING)) for name, item in objects], child_schema, child_path)
                    if child is not _MISSING:
                        result[key] = child
                # Missing required fields do not discard otherwise valid siblings.
                constraints = {k: v for k, v in node.items() if k not in ("properties", "required", "additionalProperties")}
                try:
                    validate_config_data(result, constraints)
                except InvalidConfigError as exc:
                    rejected.append(warn(path, origin, str(exc)))
                    continue
                resolve("used_" + origin)
                return result
            try:
                validate_config_data(value, node)
            except InvalidConfigError as exc:
                rejected.append(warn(path, origin, str(exc)))
                continue
            resolve("used_" + origin)
            return deepcopy(value)
        resolve("skipped")
        return _MISSING

    data = visit([("source", source), ("target", target), ("default", defaults)], schema or {}, "$")
    if data is _MISSING:
        data = {}
    def collect_missing(value: Any, node: Dict[str, Any], path: str) -> None:
        if isinstance(value, dict):
            required = node.get("required")
            for key in required if isinstance(required, list) else []:
                if isinstance(key, str) and key not in value:
                    warn("%s.%s" % (path, key), "result", "Required field has no compatible value", "requires_configuration")
            properties = node.get("properties")
            if isinstance(properties, dict):
                for key, child_schema in properties.items():
                    if key in value and isinstance(child_schema, dict):
                        collect_missing(value[key], child_schema, "%s.%s" % (path, key))
        elif isinstance(value, list) and isinstance(node.get("items"), dict):
            for index, item in enumerate(value):
                collect_missing(item, node["items"], "%s[%s]" % (path, index))

    collect_missing(data, schema or {}, "$")
    valid = True
    try:
        validate_config_data(data, schema)
    except InvalidConfigError as exc:
        valid = False
        warn("$", "result", str(exc), "requires_configuration")
    return data, warnings, valid
