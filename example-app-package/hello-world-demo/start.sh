#!/usr/bin/env bash
set -e
echo "[hello-world-demo] started at $(date)"
while true; do
  echo "[hello-world-demo] heartbeat $(date '+%H:%M:%S')"
  sleep 5
done
