from __future__ import annotations

from typing import Any

from core.errors import InvalidConfigError


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
    items_schema = schema.get("items")
    if isinstance(items_schema, dict):
        for idx, item in enumerate(value):
            _validate_value(item, items_schema, path=f"{path}[{idx}]")


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