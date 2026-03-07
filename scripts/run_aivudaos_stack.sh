#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

CADDY_BIN="${REPO_DIR}/.tools/caddy/caddy"
CADDY_CONFIG="${REPO_DIR}/Caddyfile"
FRONTEND_DIST="${REPO_DIR}/ui/dist"

if [[ ! -x "${CADDY_BIN}" ]]; then
  echo "Caddy binary not found or not executable: ${CADDY_BIN}" >&2
  exit 1
fi
if [[ ! -f "${CADDY_CONFIG}" ]]; then
  echo "Caddy config not found: ${CADDY_CONFIG}" >&2
  exit 1
fi
if [[ ! -d "${FRONTEND_DIST}" ]]; then
  echo "Frontend dist not found: ${FRONTEND_DIST}" >&2
  echo "Run: cd ui && npm run build" >&2
  exit 1
fi

cd "${REPO_DIR}"

PYTHONPATH=. /usr/bin/env python3 -m gunicorn -w 1 -k uvicorn.workers.UvicornWorker gateway.main:app -b 127.0.0.1:8000 &
backend_pid=$!

"${CADDY_BIN}" run --config "${CADDY_CONFIG}" &
caddy_pid=$!

shutdown() {
  kill "${backend_pid}" >/dev/null 2>&1 || true
  kill "${caddy_pid}" >/dev/null 2>&1 || true
  wait "${backend_pid}" >/dev/null 2>&1 || true
  wait "${caddy_pid}" >/dev/null 2>&1 || true
}

trap shutdown TERM INT

set +e
wait -n "${backend_pid}" "${caddy_pid}"
exit_code=$?
set -e

shutdown
exit "${exit_code}"