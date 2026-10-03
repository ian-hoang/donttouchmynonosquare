#!/bin/sh
# Pull new Stage A outputs and warm the identity cache every few minutes until stopped.
cd "$(dirname "$0")/.."
while true; do
  ./scripts/pull_hpg.sh >/dev/null 2>&1
  OMP_NUM_THREADS=1 .venv/bin/python scripts/identity_warm.py 2>/dev/null | tail -1
  sleep 60
done
