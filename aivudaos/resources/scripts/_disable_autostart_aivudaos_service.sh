#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/helpers/_aivudaos_systemd_common.sh"

ensure_systemctl_user_available
ensure_stack_unit_exists

if ! is_stack_enabled; then
  log "${STACK_SERVICE_NAME} is already disabled."
  exit 0
fi

log "Disabling autostart for ${STACK_SERVICE_NAME}..."
systemctl --user disable "${STACK_SERVICE_NAME}"
systemctl --user daemon-reload
log "${STACK_SERVICE_NAME} autostart disabled."
