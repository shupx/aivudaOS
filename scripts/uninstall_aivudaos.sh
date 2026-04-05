#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/helpers/_aivudaos_systemd_common.sh"

usage() {
  cat <<EOF
Usage: $0

Uninstall the AivudaOS user-level systemd service.

This removes:
  - ${STACK_UNIT}

This does not remove:
  - ${RUNTIME_ROOT}
  - ${RUNTIME_ROOT}/.tools/caddy
  - /etc/avahi/avahi-daemon.conf changes
EOF
}

if [[ $# -gt 0 ]]; then
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -V|--version)
      echo "${AIVUDAOS_VERSION:-unknown}"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
fi

ensure_systemctl_user_available

if [[ ! -f "${STACK_UNIT}" ]]; then
  log "${STACK_SERVICE_NAME} is not installed."
  exit 0
fi

if is_stack_active; then
  log "Stopping ${STACK_SERVICE_NAME}..."
  systemctl --user stop "${STACK_SERVICE_NAME}"
fi

if is_stack_enabled; then
  log "Disabling autostart for ${STACK_SERVICE_NAME}..."
  systemctl --user disable "${STACK_SERVICE_NAME}"
fi

log "Removing ${STACK_UNIT}..."
rm -f "${STACK_UNIT}"
systemctl --user daemon-reload
systemctl --user reset-failed "${STACK_SERVICE_NAME}" >/dev/null 2>&1 || true

log "${STACK_SERVICE_NAME} uninstalled."
