#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RUNTIME_ROOT="${AIVUDAOS_WS_ROOT:-${HOME}/aivudaOS_ws}"
USER_SYSTEMD_DIR="${HOME}/.config/systemd/user"
STACK_SERVICE_NAME="aivudaos.service"
STACK_UNIT="${USER_SYSTEMD_DIR}/${STACK_SERVICE_NAME}"
INSTALL_SCRIPT="${REPO_DIR}/scripts/install_aivudaos.sh"
RUNTIME_OS_CONFIG="${RUNTIME_ROOT}/config/os.yaml"

log() {
  echo "[aivudaos-systemd] $*"
}

ensure_systemctl_user_available() {
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemctl is not available in PATH." >&2
    exit 1
  fi

  if ! systemctl --user --version >/dev/null 2>&1; then
    echo "systemctl --user is not available in the current environment." >&2
    exit 1
  fi
}

ensure_stack_unit_exists() {
  if [[ -f "${STACK_UNIT}" ]]; then
    return
  fi

  echo "AivudaOS user service is not installed: ${STACK_UNIT}" >&2
  echo "Run: bash ${INSTALL_SCRIPT}" >&2
  exit 1
}

is_stack_active() {
  systemctl --user is-active --quiet "${STACK_SERVICE_NAME}"
}

is_stack_enabled() {
  systemctl --user is-enabled --quiet "${STACK_SERVICE_NAME}"
}
