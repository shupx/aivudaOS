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
STACK_RUN_SCRIPT="${REPO_DIR}/scripts/_run_aivudaos_stack.sh"
UPSERT_AVAHI_HELPER="${REPO_DIR}/scripts/helpers/upsert_avahi_hostname_conf.py"
RENDER_CADDY_HELPER="${REPO_DIR}/scripts/helpers/render_caddy_hostname.py"
GET_AVAHI_HOSTNAME_HELPER="${REPO_DIR}/scripts/helpers/_get_avahi_hostname.sh"
DOWNLOAD_CADDY_HELPER_URL="${REPO_DIR}/scripts/helpers/_download_caddy.sh"
RUNTIME_OS_CONFIG="${RUNTIME_ROOT}/config/os.yaml"
AVAHI_HOSTNAME=""

log() {
  echo "[install_user_services] $*"
}

source "${GET_AVAHI_HOSTNAME_HELPER}"

ensure_avahi_packages() {
  if ! command -v apt-get >/dev/null 2>&1; then
    return
  fi
  if [[ ! -f /etc/debian_version ]]; then
    return
  fi

  if dpkg -s avahi-daemon >/dev/null 2>&1 && dpkg -s avahi-utils >/dev/null 2>&1; then
    echo "Avahi packages already installed, skipping apt install."
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
  local caddy_source=""

  if [[ ! -x "${CADDY_BIN}" ]]; then
    echo -e "\e[33mCaddy binary not found or not executable: ${CADDY_BIN}\e[0m" >&2
    if [[ -t 0 ]]; then
      echo ""
      echo "Optional: provide a Caddy source (local binary/archive path or URL)."
      read -e -r -p "Press Enter to use default source: " caddy_source
    else
      echo "Non-interactive shell detected, using default Caddy source."
    fi

    if [[ -n "${caddy_source}" ]]; then
      "${DOWNLOAD_CADDY_HELPER_URL}" --source "${caddy_source}" --output "${CADDY_BIN}"
    else
      "${DOWNLOAD_CADDY_HELPER_URL}" --output "${CADDY_BIN}"
    fi
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

mkdir -p "${USER_SYSTEMD_DIR}"
mkdir -p "${RUNTIME_ROOT}/config"

ensure_avahi_packages
  # Step 2: Ensure host prerequisites.
ensure_passwordless_sudo_for_current_user
ensure_caddy_bind_443_permission
ensure_user_linger_enabled

  # Step 6: Generate and enable user-level systemd service.
systemctl --user stop aivudaos.service || true # stop first if running before
systemctl --user disable aivudaos.service || true # disable first if running before
systemctl --user daemon-reload
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
# ExecStartPre=/usr/bin/test -f ${CADDY_CONFIG}
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

systemctl --user daemon-reload
systemctl --user enable --now aivudaos.service

# echo ""
# echo "Done. Current status:"
# systemctl --user --no-pager --full status aivudaos.service || true

echo ""
echo "aivudaos.service is started and enabled to start at boot. You can manage it with:"
echo "  systemctl --user restart aivudaos.service"
echo "  systemctl --user stop aivudaos.service"
echo "  systemctl --user status aivudaos.service"
echo "  journalctl --user -u aivudaos.service -f"

# Resolve one concrete hostname used by both Avahi and Caddy HTTPS endpoint.
  # Step 3: Resolve one concrete hostname used by both Avahi and Caddy HTTPS endpoint.
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