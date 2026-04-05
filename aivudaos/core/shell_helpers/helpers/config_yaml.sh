#!/usr/bin/env bash

# Config YAML helper functions for app start scripts.
# Requires: AIVUDA_APP_CONFIG_PATH

if [[ -n "${AIVUDA_APP_CONFIG_YAML_HELPER_LOADED:-}" ]]; then
  return 0 2>/dev/null || exit 0
fi
AIVUDA_APP_CONFIG_YAML_HELPER_LOADED=1

_aivuda_yaml_require_config_path() {
  if [[ -z "${AIVUDA_APP_CONFIG_PATH:-}" ]]; then
    echo "AIVUDA_APP_CONFIG_PATH is not set" >&2
    return 1
  fi
  if [[ ! -f "${AIVUDA_APP_CONFIG_PATH}" ]]; then
    echo "Config file not found: ${AIVUDA_APP_CONFIG_PATH}" >&2
    return 1
  fi
  return 0
}

aivuda_yaml_get() {
  local dotted_path="${1:-}"
  local default_value="${2-}"

  if [[ -z "${dotted_path}" ]]; then
    echo "aivuda_yaml_get requires dotted path" >&2
    return 2
  fi

  _aivuda_yaml_require_config_path || return 1

  python3 - "${AIVUDA_APP_CONFIG_PATH}" "${dotted_path}" "${default_value}" <<'PY'
import json
import sys

import yaml

cfg_path = sys.argv[1]
dotted_path = sys.argv[2]
default_value = sys.argv[3]

with open(cfg_path, "r", encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}

current = data
found = True
for raw_part in dotted_path.split('.'):
    part = raw_part.strip()
    if not part:
        found = False
        break

    if isinstance(current, dict):
        if part in current:
            current = current[part]
            continue
        found = False
        break

    if isinstance(current, list) and part.isdigit():
        index = int(part)
        if 0 <= index < len(current):
            current = current[index]
            continue

    found = False
    break

if not found:
    if default_value:
        sys.stdout.write(default_value)
        sys.exit(0)
    sys.exit(1)

if current is None:
    sys.stdout.write("")
elif isinstance(current, (dict, list)):
    sys.stdout.write(json.dumps(current, ensure_ascii=False))
elif isinstance(current, bool):
    sys.stdout.write("true" if current else "false")
else:
    sys.stdout.write(str(current))
PY
}

aivuda_yaml_has() {
  local dotted_path="${1:-}"
  if [[ -z "${dotted_path}" ]]; then
    echo "aivuda_yaml_has requires dotted path" >&2
    return 2
  fi

  _aivuda_yaml_require_config_path || return 1
  python3 - "${AIVUDA_APP_CONFIG_PATH}" "${dotted_path}" <<'PY'
import sys

import yaml

cfg_path = sys.argv[1]
dotted_path = sys.argv[2]

with open(cfg_path, "r", encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}

current = data
for raw_part in dotted_path.split('.'):
    part = raw_part.strip()
    if not part:
        sys.exit(1)

    if isinstance(current, dict) and part in current:
        current = current[part]
        continue

    if isinstance(current, list) and part.isdigit():
        index = int(part)
        if 0 <= index < len(current):
            current = current[index]
            continue

    sys.exit(1)

sys.exit(0)
PY
}
