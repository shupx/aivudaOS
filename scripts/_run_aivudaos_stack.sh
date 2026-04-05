#!/usr/bin/env bash
set -euo pipefail

# Run complete AivudaOS stack in foreground (backend + optional dev frontend watch + Caddy).
# This script expects runtime Caddyfile to already contain a concrete HTTPS host
# like: https://robot-abc.local[:port] (not {$AVAHI_HOSTNAME}).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_ROOT="${AIVUDAOS_WS_ROOT:-${HOME}/aivudaOS_ws}"
DEV_MODE=0

usage() {
  cat <<EOF
Usage: $0 [--dev]

Options:
  --dev    Run backend with uvicorn reload and frontend with vite build --watch
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dev)
      DEV_MODE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

CADDY_BIN="${RUNTIME_ROOT}/.tools/caddy/caddy"
CADDY_TEMPLATE="${REPO_DIR}/Caddyfile_template"
CADDY_CONFIG="${RUNTIME_ROOT}/config/Caddyfile"
FRONTEND_DIST="${REPO_DIR}/ui/dist"

if [[ ! -x "${CADDY_BIN}" ]]; then
  echo "Caddy binary not found or not executable: ${CADDY_BIN}" >&2
  exit 1
fi

mkdir -p "$(dirname "${CADDY_CONFIG}")"
if [[ ! -f "${CADDY_CONFIG}" ]]; then
  if [[ ! -f "${CADDY_TEMPLATE}" ]]; then
    echo "Caddy template not found: ${CADDY_TEMPLATE}" >&2
    exit 1
  fi
  cp "${CADDY_TEMPLATE}" "${CADDY_CONFIG}"
fi

if [[ ! -f "${CADDY_CONFIG}" ]]; then
  echo "Caddy config not found: ${CADDY_CONFIG}" >&2
  exit 1
fi
if grep -Eq 'https://(\{\$AVAHI_HOSTNAME\}|__AVAHI_HOSTNAME__)\.local(:[0-9]+)?' "${CADDY_CONFIG}"; then
  echo "Caddy config has unresolved AVAHI_HOSTNAME placeholder: ${CADDY_CONFIG}" >&2
  echo "Run: ./scripts/install_user_services.sh to sync Avahi hostname into Caddy config." >&2
  # exit 1
fi
if [[ "${DEV_MODE}" -eq 0 && ! -d "${FRONTEND_DIST}" ]]; then
  echo "Frontend dist not found: ${FRONTEND_DIST}" >&2
  echo "Run: cd ui && npm run build" >&2
  exit 1
fi
if [[ "${DEV_MODE}" -eq 1 ]]; then
  mkdir -p "${FRONTEND_DIST}"
fi

cd "${REPO_DIR}"

# Backend process: uvicorn reload in dev, gunicorn in production-like mode.
if [[ "${DEV_MODE}" -eq 1 ]]; then
  PYTHONPATH=. /usr/bin/env python3 -m uvicorn gateway.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir gateway --reload-dir core &
else
  PYTHONPATH=. /usr/bin/env python3 -m gunicorn -w 1 -k uvicorn.workers.UvicornWorker gateway.main:app -b 127.0.0.1:8000 &
fi
backend_pid=$!

vite_pid=""
if [[ "${DEV_MODE}" -eq 1 ]]; then
  # Frontend watch build feeds Caddy static root (ui/dist) continuously.
  (
    cd "${REPO_DIR}/ui"
    npm exec vite build -- --watch
  ) &
  vite_pid=$!
fi

"${CADDY_BIN}" run --config "${CADDY_CONFIG}" &
caddy_pid=$!

sleep 2.5
AVAHI_HOSTNAME=$(grep -E '^host-name=' /etc/avahi/avahi-daemon.conf | cut -d= -f2); [ -n "$AVAHI_HOSTNAME" ] && echo ${AVAHI_HOSTNAME} || hostname
echo -e "Open \e[32mhttps://${AVAHI_HOSTNAME}.local\e[0m in your remote browser or \e[32mhttp://127.0.0.1\e[0m in the local browser to access AivudaOS UI."

shutdown() {
  kill "${backend_pid}" >/dev/null 2>&1 || true
  kill "${caddy_pid}" >/dev/null 2>&1 || true
  if [[ -n "${vite_pid}" ]]; then
    kill "${vite_pid}" >/dev/null 2>&1 || true
  fi
  wait "${backend_pid}" >/dev/null 2>&1 || true
  wait "${caddy_pid}" >/dev/null 2>&1 || true
  if [[ -n "${vite_pid}" ]]; then
    wait "${vite_pid}" >/dev/null 2>&1 || true
  fi
}

trap shutdown TERM INT

set +e
if [[ -n "${vite_pid}" ]]; then
  wait -n "${backend_pid}" "${caddy_pid}" "${vite_pid}"
else
  wait -n "${backend_pid}" "${caddy_pid}"
fi
exit_code=$?
set -e

shutdown
exit "${exit_code}"