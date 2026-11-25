"""Schema contract shared by network discovery and magnet propagation."""
from typing import Any, Optional, Tuple


def device_ipv4_fields(group_schema: Any) -> Optional[Tuple[str, str, str]]:
    if not isinstance(group_schema, dict):
        return None
    fields = group_schema.get("x-device-ipv4")
    props = group_schema.get("properties")
    if not isinstance(fields, dict) or not isinstance(props, dict):
        return None
    nic, addr, dest = (fields.get(key) for key in ("interface", "address", "destination"))
    names = (nic, addr, dest)
    if not all(isinstance(key, str) and key and isinstance(props.get(key), dict) for key in names):
        return None
    return names if len(set(names)) == 3 else None
