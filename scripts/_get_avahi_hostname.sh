#!/usr/bin/env bash
set -euo pipefail

RUNTIME_ROOT="${AIVUDAOS_WS_ROOT:-${HOME}/aivudaOS_ws}"
RUNTIME_OS_CONFIG="${RUNTIME_ROOT}/config/os.yaml"

warn() {
  echo -e "\033[0;33mwarn: $*\033[0m" >&2
}

get_avahi_hostname() {
  local debug_mode="${1:-}"
  local is_debug="0"
  local hostname_os_config=""
  local hostname_avahi_conf=""
  local host_name=""
  local has_warn="0"

  if [[ "${debug_mode}" == "--debug" ]]; then
    is_debug="1"
  fi

  hostname_os_config="$(resolve_avahi_hostname_from_os_config "${RUNTIME_OS_CONFIG}")"
  hostname_avahi_conf="$(get_avahi_hostname_from_avahi_daemon_config)"

  if [[ -z "${hostname_os_config}" ]]; then
    if [[ "${is_debug}" == "1" ]]; then
      warn "missing avahi_hostname in ${RUNTIME_OS_CONFIG}"
    fi
    has_warn="1"
  else
    if [[ "${is_debug}" == "1" ]]; then
      echo -e "avahi hostname from aivuda os.yaml: \033[0;32m${hostname_os_config}\033[0m"
    fi
  fi

  if [[ -z "${hostname_avahi_conf}" ]]; then
    if [[ "${is_debug}" == "1" ]]; then
      warn "missing host-name in /etc/avahi/avahi-daemon.conf"
    fi
    has_warn="1"
  else
    if [[ "${is_debug}" == "1" ]]; then
      echo -e "avahi hostname from avahi-daemon.conf: \033[0;32m${hostname_avahi_conf}\033[0m"
    fi
  fi

  if [[ -n "${hostname_os_config}" && -n "${hostname_avahi_conf}" && "${hostname_os_config}" != "${hostname_avahi_conf}" ]]; then
    if [[ "${is_debug}" == "1" ]]; then
      warn "avahi hostname mismatch: os_config=${hostname_os_config}, avahi_conf=${hostname_avahi_conf}"
    fi
    has_warn="1"
  fi

  if [[ "${has_warn}" == "1" && "${is_debug}" != "1" ]]; then
    return 1
  fi

  if [[ "${has_warn}" == "0" ]]; then
    host_name="${hostname_os_config}"
    if [[ "${is_debug}" == "1" ]]; then
      echo -e "\033[0;32m${host_name}\033[0m"
    else
      echo -n "${host_name}"
    fi
  fi
}

resolve_avahi_hostname_from_os_config() {
  local path="$1"
  local value=""
  if [[ ! -f "${path}" ]]; then
    return 0
  fi

  value="$(grep -E '^[[:space:]]*avahi_hostname[[:space:]]*:' "${path}" | tail -n1 | sed -E 's/^[^:]*:[[:space:]]*//; s/[[:space:]]+#.*$//' | tr -d '"' | tr -d "'" | tr '[:upper:]' '[:lower:]')"
  value="$(echo -n "${value}" | xargs)"
  if [[ "${value}" =~ ^[a-z0-9][a-z0-9-]{0,62}$ ]]; then
    echo -n "${value}"
  fi
}

get_avahi_hostname_from_avahi_daemon_config() {
  local host=""

  if [[ ! -f /etc/avahi/avahi-daemon.conf ]]; then
    return 0
  fi

  host="$(grep -E '^[[:space:]]*host-name=' /etc/avahi/avahi-daemon.conf | tail -n1 | cut -d= -f2 | tr -d '"' | tr "'" ' ' | xargs | tr '[:upper:]' '[:lower:]')"
  if [[ "${host}" =~ ^[a-z0-9][a-z0-9-]{0,62}$ ]]; then
    echo -n "${host}"
  fi
}

# 仅在直接执行脚本时运行，被source时不运行
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    get_avahi_hostname "$@"
fi