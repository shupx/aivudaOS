#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/helpers/_aivudaos_systemd_common.sh"

ensure_systemctl_user_available
ensure_stack_unit_exists

log "Restarting ${STACK_SERVICE_NAME}..."
systemctl --user restart "${STACK_SERVICE_NAME}"
log "${STACK_SERVICE_NAME} restarted."
