from __future__ import annotations

import re
from typing import Any

from core.errors import InvalidConfigError


SUPPORTED_SCHEMA_KEYS = {
    "type",
    "default",
    "need_restart",
    "description",
    "enum",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
}


def validate_config_data(data: Any, schema: dict[str, Any] | None, *, context: str = "config") -> None:
    if schema is None:
        return
    if not isinstance(schema, dict):
        raise InvalidConfigError(f"{context} schema must be an object")
    _validate_value(data, schema, path="$")


def _validate_value(value: Any, schema: dict[str, Any], *, path: str) -> None:
    expected_type = schema.get("type")
    if expected_type is not None:
        _validate_type(value, expected_type, path)

    if "enum" in schema:
        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and value not in enum_values:
            raise InvalidConfigError(f"{path} must be one of {enum_values}")

    _validate_value_constraints(value, schema, path)

    if isinstance(value, dict):
        _validate_object(value, schema, path)
        return

    if isinstance(value, list):
        _validate_array(value, schema, path)


def _validate_object(value: dict[str, Any], schema: dict[str, Any], path: str) -> None:
    required = schema.get("required") or []
    if isinstance(required, list):
        for key in required:
            if isinstance(key, str) and key not in value:
                raise InvalidConfigError(f"{path}.{key} is required")

    properties = schema.get("properties")
    if isinstance(properties, dict):
        for key, child_schema in properties.items():
            if key not in value:
                continue
            if not isinstance(child_schema, dict):
                continue
            _validate_value(value[key], child_schema, path=f"{path}.{key}")

    additional = schema.get("additionalProperties", True)
    if additional is False and isinstance(properties, dict):
        unknown = [k for k in value.keys() if k not in properties]
        if unknown:
            raise InvalidConfigError(f"{path} has unknown keys: {', '.join(unknown)}")


def _validate_array(value: list[Any], schema: dict[str, Any], path: str) -> None:
    min_items = schema.get("minItems")
    if isinstance(min_items, int) and len(value) < min_items:
        raise InvalidConfigError(f"{path} must have at least {min_items} items")

    max_items = schema.get("maxItems")
    if isinstance(max_items, int) and len(value) > max_items:
        raise InvalidConfigError(f"{path} must have at most {max_items} items")

    items_schema = schema.get("items")
    if isinstance(items_schema, dict):
        for idx, item in enumerate(value):
            _validate_value(item, items_schema, path=f"{path}[{idx}]")


def _validate_value_constraints(value: Any, schema: dict[str, Any], path: str) -> None:
    if isinstance(value, bool):
        return

    if isinstance(value, (int, float)):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            raise InvalidConfigError(f"{path} must be >= {minimum}")

        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and value > maximum:
            raise InvalidConfigError(f"{path} must be <= {maximum}")

        exclusive_minimum = schema.get("exclusiveMinimum")
        if isinstance(exclusive_minimum, (int, float)) and value <= exclusive_minimum:
            raise InvalidConfigError(f"{path} must be > {exclusive_minimum}")

        exclusive_maximum = schema.get("exclusiveMaximum")
        if isinstance(exclusive_maximum, (int, float)) and value >= exclusive_maximum:
            raise InvalidConfigError(f"{path} must be < {exclusive_maximum}")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            raise InvalidConfigError(f"{path} length must be >= {min_length}")

        max_length = schema.get("maxLength")
        if isinstance(max_length, int) and len(value) > max_length:
            raise InvalidConfigError(f"{path} length must be <= {max_length}")

        pattern = schema.get("pattern")
        if isinstance(pattern, str):
            try:
                if re.fullmatch(pattern, value) is None:
                    raise InvalidConfigError(f"{path} does not match pattern {pattern}")
            except re.error as exc:
                raise InvalidConfigError(f"{path} has invalid schema pattern: {exc}")


def _validate_type(value: Any, expected: Any, path: str) -> None:
    expected_values = expected if isinstance(expected, list) else [expected]
    if not expected_values:
        return

    if any(_is_type_match(value, item) for item in expected_values):
        return

    raise InvalidConfigError(f"{path} type mismatch, expected {expected_values}")


def _is_type_match(value: Any, expected: Any) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(value, float)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def normalize_config_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    return _normalize_schema_node(schema)


def _normalize_schema_node(schema: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    for key in SUPPORTED_SCHEMA_KEYS:
        if key in schema:
            normalized[key] = schema[key]

    properties = schema.get("properties")
    if isinstance(properties, dict):
        normalized["properties"] = {
            key: _normalize_schema_node(child)
            for key, child in properties.items()
            if isinstance(key, str) and isinstance(child, dict)
        }

    items = schema.get("items")
    if isinstance(items, dict):
        normalized["items"] = _normalize_schema_node(items)

    required = schema.get("required")
    if isinstance(required, list):
        normalized["required"] = [item for item in required if isinstance(item, str)]

    return normalized