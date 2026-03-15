#!/usr/bin/env bash
set -euo pipefail

# Install/update user-level AivudaOS systemd service and make runtime hostname wiring deterministic.
# - Resolve one Avahi hostname source of truth.
# - Write it into /etc/avahi/avahi-daemon.conf ([server] host-name=...).
# - Rewrite runtime Caddyfile HTTPS site address to concrete <hostname>.local.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
USER_SYSTEMD_DIR="${HOME}/.config/systemd/user"
RUNTIME_ROOT="${AIVUDAOS_WS_ROOT:-${HOME}/aivudaOS_ws}"

STACK_UNIT="${USER_SYSTEMD_DIR}/aivudaos.service"
CADDY_BIN="${REPO_DIR}/.tools/caddy/caddy"
CADDY_TEMPLATE="${REPO_DIR}/Caddyfile_template"
CADDY_CONFIG="${RUNTIME_ROOT}/config/Caddyfile"
FRONTEND_DIST="${REPO_DIR}/ui/dist"
STACK_RUN_SCRIPT="${REPO_DIR}/scripts/run_aivudaos_stack.sh"
UPSERT_AVAHI_HELPER="${REPO_DIR}/scripts/helpers/upsert_avahi_hostname_conf.py"
RENDER_CADDY_HELPER="${REPO_DIR}/scripts/helpers/render_caddy_hostname.py"
RUNTIME_OS_CONFIG="${RUNTIME_ROOT}/config/os.yaml"
AVAHI_HOSTNAME=""

log() {
  echo "[install_user_services] $*"
}

generate_robot_hostname() {
  local sec rand num
  sec="$(date +%S)"
  rand=$((RANDOM % 4096))
  num=$(( (10#${sec} + rand) % 4096 ))
  printf 'robot-%03x' "${num}"
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

ensure_avahi_packages() {
  if ! command -v apt-get >/dev/null 2>&1; then
    return
  fi
  if [[ ! -f /etc/debian_version ]]; then
    return
  fi

  echo "Installing avahi-daemon and avahi-utils (Debian/Ubuntu)..."
  sudo apt-get update -y
  sudo apt-get install -y avahi-daemon avahi-utils
}

ensure_passwordless_sudo_for_current_user() {
  local sudoers_file="/etc/sudoers.d/${USER}"
  local expected_line="${USER} ALL=(ALL) NOPASSWD:ALL"
  local tmpfile=""

  if sudo test -f "${sudoers_file}" && sudo grep -Fxq "${expected_line}" "${sudoers_file}"; then
    return
  fi

  echo "Configuring passwordless sudo for user ${USER}..."
  tmpfile="$(mktemp)"
  printf '%s\n' "${expected_line}" > "${tmpfile}"
  chmod 0440 "${tmpfile}"
  sudo visudo -cf "${tmpfile}" >/dev/null
  sudo install -m 0440 "${tmpfile}" "${sudoers_file}"
  rm -f "${tmpfile}"
}

ensure_caddy_bind_443_permission() {
  if [[ ! -x "${CADDY_BIN}" ]]; then
    echo "Caddy binary not found or not executable: ${CADDY_BIN}" >&2
    exit 1
  fi

  if command -v getcap >/dev/null 2>&1; then
    if getcap "${CADDY_BIN}" 2>/dev/null | grep -q "cap_net_bind_service"; then
      return
    fi
  fi

  echo ""
  echo "Caddy needs permission to bind privileged port 80."
  echo "Running: sudo setcap cap_net_bind_service=+ep ${CADDY_BIN}"
  sudo setcap cap_net_bind_service=+ep "${CADDY_BIN}"

  if command -v getcap >/dev/null 2>&1; then
    if ! getcap "${CADDY_BIN}" 2>/dev/null | grep -q "cap_net_bind_service"; then
      echo "Failed to grant cap_net_bind_service on ${CADDY_BIN}" >&2
      exit 1
    fi
  fi
}

ensure_user_linger_enabled() {
  local linger_state=""
  linger_state="$(loginctl show-user "${USER}" -p Linger --value 2>/dev/null || true)"

  if [[ "${linger_state}" == "yes" ]]; then
    return
  fi

  echo ""
  echo "Enable user linger for boot auto-start before login."
  echo "Running: sudo loginctl enable-linger ${USER}"
  sudo loginctl enable-linger "${USER}"
}

upsert_avahi_hostname_and_restart() {
  local hostname="$1"
  local avahi_conf="/etc/avahi/avahi-daemon.conf"
  local tmpfile

  tmpfile="$(mktemp)"
  python3 "${UPSERT_AVAHI_HELPER}" --hostname "${hostname}" --output "${tmpfile}"

  sudo install -m 644 "${tmpfile}" "${avahi_conf}"
  rm -f "${tmpfile}"

  log "Restarting avahi-daemon.service"
  sudo systemctl restart avahi-daemon.service
}

replace_caddy_https_hostname() {
  local config_path="$1"
  local hostname="$2"
  local tmpfile
  local before_hash
  local after_hash

  tmpfile="$(mktemp)"
  before_hash="$(sha256sum "${config_path}" | awk '{print $1}')"
  python3 "${RENDER_CADDY_HELPER}" --config "${config_path}" --hostname "${hostname}" --output "${tmpfile}"
  after_hash="$(sha256sum "${tmpfile}" | awk '{print $1}')"
  install -m 644 "${tmpfile}" "${config_path}"
  rm -f "${tmpfile}"

  if [[ "${before_hash}" != "${after_hash}" ]]; then
    return 0
  fi
  return 1
}

reload_caddy_if_running() {
  if pgrep -af "${CADDY_BIN} run --config ${CADDY_CONFIG}" >/dev/null 2>&1; then
    log "Reloading running Caddy with updated config"
    if ! "${CADDY_BIN}" reload --config "${CADDY_CONFIG}"; then
      echo "Warning: Caddy reload failed. Please restart aivudaos.service or Caddy manually." >&2
    fi
  fi
}

mkdir -p "${USER_SYSTEMD_DIR}"
mkdir -p "${RUNTIME_ROOT}/config"

if [[ ! -f "${CADDY_CONFIG}" ]]; then
  # Step 1: Prepare runtime Caddy config from template when missing.
  if [[ ! -f "${CADDY_TEMPLATE}" ]]; then
    echo "Caddy template not found: ${CADDY_TEMPLATE}" >&2
    exit 1
  fi
  cp "${CADDY_TEMPLATE}" "${CADDY_CONFIG}"
fi

ensure_avahi_packages
  # Step 2: Ensure host prerequisites.
ensure_passwordless_sudo_for_current_user
ensure_caddy_bind_443_permission
ensure_user_linger_enabled

# Resolve one concrete hostname used by both Avahi and Caddy HTTPS endpoint.
  # Step 3: Resolve one concrete hostname used by both Avahi and Caddy HTTPS endpoint.
AVAHI_HOSTNAME="$(resolve_avahi_hostname_from_os_config "${RUNTIME_OS_CONFIG}")"
if [[ -z "${AVAHI_HOSTNAME}" ]]; then
  AVAHI_HOSTNAME="$(generate_robot_hostname)"
  echo "No valid avahi_hostname found in ${RUNTIME_OS_CONFIG}, generated random hostname: ${AVAHI_HOSTNAME}"
fi

log "Resolved AVAHI_HOSTNAME=${AVAHI_HOSTNAME}"

  # Step 4: Write Avahi host-name and restart avahi-daemon.
upsert_avahi_hostname_and_restart "${AVAHI_HOSTNAME}"

  # Step 5: Rewrite Caddy HTTPS host and hot-reload running Caddy when changed.
if replace_caddy_https_hostname "${CADDY_CONFIG}" "${AVAHI_HOSTNAME}"; then
  reload_caddy_if_running
fi

  # Step 6: Generate and enable user-level systemd service.
cat > "${STACK_UNIT}" <<EOF
[Unit]
Description=AivudaOS Stack (backend + caddy)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${REPO_DIR}
Environment=AIVUDAOS_WS_ROOT=${RUNTIME_ROOT}
ExecStartPre=/usr/bin/test -x ${CADDY_BIN}
ExecStartPre=/usr/bin/test -f ${CADDY_CONFIG}
ExecStartPre=/usr/bin/test -d ${FRONTEND_DIST}
ExecStartPre=/usr/bin/test -f ${STACK_RUN_SCRIPT}
ExecStart=/usr/bin/env bash ${STACK_RUN_SCRIPT}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

echo "User service generated:"
echo "  - ${STACK_UNIT}"
echo "Avahi/Caddy hostname: ${AVAHI_HOSTNAME}"

if pgrep -af "uvicorn gateway.main:app.*--port 8000|gunicorn.*gateway.main:app.*127.0.0.1:8000" >/dev/null; then
  echo ""
  echo "Warning: detected manually started backend process on port 8000."
  echo "Please stop it first, otherwise user service may fail to bind 127.0.0.1:8000."
fi

systemctl --user daemon-reload
systemctl --user enable --now aivudaos.service

echo ""
echo "Done. Current status:"
systemctl --user --no-pager --full status aivudaos.service || true

echo ""
echo "aivudaos.service is started and enabled to start at boot. You can manage it with:"
echo "  systemctl --user restart aivudaos.service"
echo "  systemctl --user stop aivudaos.service"
echo "  systemctl --user status aivudaos.service"
echo "  journalctl --user -u aivudaos.service -f"

echo ""
echo "domain: ${AVAHI_HOSTNAME}.local"
echo -e "Open \e[32mhttps://${AVAHI_HOSTNAME}.local\e[0m in your remote browser or \e[32mhttp://127.0.0.1\e[0m in the local browser to access AivudaOS UI."