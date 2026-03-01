#!/usr/bin/env bash
set -euo pipefail

echo "[pre_install] checking system prerequisites"
command -v bash >/dev/null 2>&1 || { echo "bash not found"; exit 1; }
command -v systemctl >/dev/null 2>&1 || echo "systemctl not found, fallback runtime may be used"

for i in {1..3}; do
  echo "正在安装中"
  sleep 1
done

echo "[pre_install] done"
