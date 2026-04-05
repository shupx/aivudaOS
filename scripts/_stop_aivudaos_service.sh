#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/helpers/_aivudaos_systemd_common.sh"

ensure_systemctl_user_available
ensure_stack_unit_exists

if ! is_stack_active; then
  log "${STACK_SERVICE_NAME} is not running."
  exit 0
fi

log "Stopping ${STACK_SERVICE_NAME}..."
systemctl --user stop "${STACK_SERVICE_NAME}"
log "${STACK_SERVICE_NAME} stopped."
