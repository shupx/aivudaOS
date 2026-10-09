"""Validation shared by OS configuration and app process launchers."""
import re
from typing import Dict


DEFAULT_RUNTIME_ENVIRONMENT = {"ROS_LOCALHOST_ONLY": "1"}


def validate_runtime_environment(value: object) -> Dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("runtime_environment must be an object of string values")
    result: Dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError("Invalid environment variable name: {!r}".format(key))
        if key.startswith("AIVUDA_"):
            raise ValueError("AIVUDA_* environment variables are reserved")
        if not isinstance(item, str) or any(char in item for char in ("\x00", "\n", "\r")):
            raise ValueError("Environment variable {} must be a string without NUL or line breaks".format(key))
        result[key] = item
    return result
