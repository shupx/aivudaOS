#!/usr/bin/env bash
set -euo pipefail

RUNTIME_ROOT="${AIVUDAOS_WS_ROOT:-${HOME}/aivudaOS_ws}"
RUNTIME_OS_CONFIG="${RUNTIME_ROOT}/config/os.yaml"
RUNTIME_CADDY_CONFIG="${RUNTIME_ROOT}/config/Caddyfile"
USER_SYSTEMD_UNIT="${HOME}/.config/systemd/user/aivudaos.service"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GET_AVAHI_HOSTNAME_HELPER="${SCRIPT_DIR}/_get_avahi_hostname.sh"

source "${GET_AVAHI_HOSTNAME_HELPER}"

LOCAL_URL="http://127.0.0.1"

print_install_hint() {
  echo -e "\033[0;33maivudaos is not ready yet. Please run \033[1maivudaos install\033[0;33m first.\033[0m" >&2
}

main() {
  local avahi_hostname=""

  if [[ ! -f "${RUNTIME_OS_CONFIG}" || ! -f "${RUNTIME_CADDY_CONFIG}" || ! -f "${USER_SYSTEMD_UNIT}" ]]; then
    print_install_hint
    return 1
  fi

  avahi_hostname="$(get_avahi_hostname 2>/dev/null || true)"
  if [[ -z "${avahi_hostname}" ]]; then
    print_install_hint
    return 1
  fi

  echo "AivudaOS web addresses:"
  echo -e "  Local:  \e[32m${LOCAL_URL}\e[0m"
  echo -e "  Remote: \e[32mhttps://${avahi_hostname}.local\e[0m"
  echo -e "If you cannot access the web interface, please run \e[33m\"aivudaos install\"\e[0m first to set up the system, \e[33m\"aivudaos start\"\e[0m to start the service, and ensure your device is on the same local network as your computer."
}

main "$@"
