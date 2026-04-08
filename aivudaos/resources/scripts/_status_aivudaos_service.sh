#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
WEB_HINT_SCRIPT="${SCRIPT_DIR}/_web_hint.sh"

source "${SCRIPT_DIR}/helpers/_aivudaos_systemd_common.sh"

print_section() {
  local title="$1"
  echo ""
  echo "=== ${title} ==="
}

main() {
  print_section "Web Access"
  if [[ -f "${WEB_HINT_SCRIPT}" ]]; then
    bash "${WEB_HINT_SCRIPT}" || true
  else
    echo "Web hint script not found: ${WEB_HINT_SCRIPT}" >&2
  fi

  print_section "User Service Status"
  ensure_systemctl_user_available

  if [[ ! -f "${STACK_UNIT}" ]]; then
    echo "AivudaOS user service is not installed: ${STACK_UNIT}"
    echo "Run: bash ${INSTALL_SCRIPT}"
    return 1
  fi

  systemctl --user --no-pager --full status "${STACK_SERVICE_NAME}" || true
}

main "$@"
