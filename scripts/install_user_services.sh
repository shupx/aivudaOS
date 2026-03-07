#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
USER_SYSTEMD_DIR="${HOME}/.config/systemd/user"

STACK_UNIT="${USER_SYSTEMD_DIR}/aivudaos.service"
CADDY_BIN="${REPO_DIR}/.tools/caddy/caddy"
CADDY_CONFIG="${REPO_DIR}/Caddyfile"
FRONTEND_DIST="${REPO_DIR}/ui/dist"
STACK_RUN_SCRIPT="${REPO_DIR}/scripts/run_aivudaos_stack.sh"
AIVUDAOS_PUBLIC_HTTPS_HOST="${AIVUDAOS_PUBLIC_HTTPS_HOST:-}"
AIVUDAOS_PRIVATE_HTTPS_HOST="${AIVUDAOS_PRIVATE_HTTPS_HOST:-}"

list_local_ipv4_candidates() {
  local ip_list=()
  local token

  if command -v hostname >/dev/null 2>&1; then
    for token in $(hostname -I 2>/dev/null || true); do
      if [[ "${token}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] && [[ "${token}" != "127.0.0.1" ]]; then
        ip_list+=("${token}")
      fi
    done
  fi

  if command -v ip >/dev/null 2>&1; then
    while IFS= read -r token; do
      if [[ "${token}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] && [[ "${token}" != "127.0.0.1" ]]; then
        ip_list+=("${token}")
      fi
    done < <(ip -o -4 addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
  fi

  if [[ ${#ip_list[@]} -gt 0 ]]; then
    printf "%s\n" "${ip_list[@]}" | awk '!seen[$0]++'
  fi
}

prompt_private_https_host() {
  local candidates=()
  local idx=0
  local pick=""

  while IFS= read -r line; do
    [[ -n "${line}" ]] && candidates+=("${line}")
  done < <(list_local_ipv4_candidates)

  if [[ ${#candidates[@]} -eq 0 ]]; then
    read -r -p "Input HTTPS private IP/domain for Caddy (AIVUDAOS_PRIVATE_HTTPS_HOST): " AIVUDAOS_PRIVATE_HTTPS_HOST
    return
  fi

  echo "Detected local IPv4 addresses:"
  for idx in "${!candidates[@]}"; do
    printf "  [%d] %s\n" "$((idx + 1))" "${candidates[idx]}"
  done
  echo "  [m] Manual input"

  read -r -p "Select private IP [1-${#candidates[@]}] or m: " pick
  if [[ "${pick}" =~ ^[0-9]+$ ]] && (( pick >= 1 && pick <= ${#candidates[@]} )); then
    AIVUDAOS_PRIVATE_HTTPS_HOST="${candidates[pick-1]}"
    echo "Selected private host: ${AIVUDAOS_PRIVATE_HTTPS_HOST}"
  else
    read -r -p "Input HTTPS private IP/domain for Caddy (AIVUDAOS_PRIVATE_HTTPS_HOST): " AIVUDAOS_PRIVATE_HTTPS_HOST
  fi
}

ensure_https_hosts() {
  if [[ -z "${AIVUDAOS_PUBLIC_HTTPS_HOST}" ]]; then
    read -r -p "Input HTTPS public IP/domain for Caddy (AIVUDAOS_PUBLIC_HTTPS_HOST): " AIVUDAOS_PUBLIC_HTTPS_HOST
  fi

  if [[ -z "${AIVUDAOS_PRIVATE_HTTPS_HOST}" ]]; then
    prompt_private_https_host
  fi

  if [[ -z "${AIVUDAOS_PUBLIC_HTTPS_HOST}" ]]; then
    echo "AIVUDAOS_PUBLIC_HTTPS_HOST is required." >&2
    exit 1
  fi

  if [[ -z "${AIVUDAOS_PRIVATE_HTTPS_HOST}" ]]; then
    echo "AIVUDAOS_PRIVATE_HTTPS_HOST is required." >&2
    exit 1
  fi

  if [[ "${AIVUDAOS_PUBLIC_HTTPS_HOST}" =~ [[:space:]] ]]; then
    echo "AIVUDAOS_PUBLIC_HTTPS_HOST cannot contain spaces: ${AIVUDAOS_PUBLIC_HTTPS_HOST}" >&2
    exit 1
  fi

  if [[ "${AIVUDAOS_PRIVATE_HTTPS_HOST}" =~ [[:space:]] ]]; then
    echo "AIVUDAOS_PRIVATE_HTTPS_HOST cannot contain spaces: ${AIVUDAOS_PRIVATE_HTTPS_HOST}" >&2
    exit 1
  fi
}

ensure_caddy_bind_443_permission() {
  if [[ ! -x "${CADDY_BIN}" ]]; then
    echo "Caddy binary not found or not executable: ${CADDY_BIN}" >&2
    exit 1
  fi

  if command -v getcap >/dev/null 2>&1; then
    if getcap "${CADDY_BIN}" 2>/dev/null | grep -q "cap_net_bind_service=ep"; then
      return
    fi
  fi

  echo ""
  echo "Caddy needs permission to bind privileged port 80."
  echo "Running: sudo setcap cap_net_bind_service=+ep ${CADDY_BIN}"
  sudo setcap cap_net_bind_service=+ep "${CADDY_BIN}"

  if command -v getcap >/dev/null 2>&1; then
    if ! getcap "${CADDY_BIN}" 2>/dev/null | grep -q "cap_net_bind_service=ep"; then
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

ensure_https_hosts
ensure_caddy_bind_443_permission
ensure_user_linger_enabled

cat > "${STACK_UNIT}" <<EOF
[Unit]
Description=AivudaOS Stack (backend + caddy)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${REPO_DIR}
Environment=AIVUDAOS_PUBLIC_HTTPS_HOST=${AIVUDAOS_PUBLIC_HTTPS_HOST}
Environment=AIVUDAOS_PRIVATE_HTTPS_HOST=${AIVUDAOS_PRIVATE_HTTPS_HOST}
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
echo "HTTPS public host: ${AIVUDAOS_PUBLIC_HTTPS_HOST}"
echo "HTTPS private host: ${AIVUDAOS_PRIVATE_HTTPS_HOST}"

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
echo "Manage commands:"
echo "  systemctl --user restart aivudaos.service"
echo "  systemctl --user stop aivudaos.service"
echo "  systemctl --user status aivudaos.service"
echo "  journalctl --user -u aivudaos.service -f"