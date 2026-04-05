#!/usr/bin/env bash
set -euo pipefail

start_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${start_script_dir}/helpers/_aivudaos_systemd_common.sh"
source "${start_script_dir}/helpers/_get_avahi_hostname.sh"

ensure_systemctl_user_available
ensure_stack_unit_exists

if is_stack_active; then
  log "${STACK_SERVICE_NAME} is already running."
  exit 0
fi

log "Starting ${STACK_SERVICE_NAME}..."
systemctl --user start "${STACK_SERVICE_NAME}"
log "${STACK_SERVICE_NAME} started."



AVAHI_HOSTNAME="$(resolve_avahi_hostname_from_os_config "${RUNTIME_OS_CONFIG}")"
if [[ -z "${AVAHI_HOSTNAME}" ]]; then
  echo -e "\e[33mNo valid avahi_hostname found in ${RUNTIME_OS_CONFIG}, waiting 3s then retry...\e[0m"
  sleep 3
  AVAHI_HOSTNAME="$(resolve_avahi_hostname_from_os_config "${RUNTIME_OS_CONFIG}")"
fi

if [[ -z "${AVAHI_HOSTNAME}" ]]; then
  echo -e "\e[33mRun _get_avahi_hostname.sh later to get the avahi hostname\e[0m"
else
  echo -e "Resolved AVAHI_HOSTNAME=\e[32m${AVAHI_HOSTNAME}\e[0m"
fi

echo ""
echo "domain: ${AVAHI_HOSTNAME}.local"
echo -e "Open \e[32mhttps://${AVAHI_HOSTNAME}.local\e[0m in your remote browser or \e[32mhttp://127.0.0.1\e[0m in the local browser to access AivudaOS UI."
