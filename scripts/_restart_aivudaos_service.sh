#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STOP_SCRIPT="${SCRIPT_DIR}/_stop_aivudaos_service.sh"
START_SCRIPT="${SCRIPT_DIR}/_start_aivudaos_service.sh"

echo "[aivudaos-systemd] Restarting aivudaos.service via stop -> start..."
"${STOP_SCRIPT}"
"${START_SCRIPT}"
