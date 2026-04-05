#!/usr/bin/env bash

# Unified helper entrypoint for app start scripts.
# Source this file once in app start.sh:
#   source "${AIVUDA_APP_HELPERS_ENTRY_PATH}"

if [[ -n "${AIVUDA_APP_HELPERS_LOADED:-}" ]]; then
  return 0 2>/dev/null || exit 0
fi
AIVUDA_APP_HELPERS_LOADED=1

_THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "${_THIS_DIR}/helpers/config_yaml.sh"
