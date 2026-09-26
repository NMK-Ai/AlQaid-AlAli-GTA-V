#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/environment.sh"
cd /data/openpilot
source .venv/bin/activate
export PYTHONPATH=/data/openpilot
export PYOPENCL_CTX=0
export SIMULATION=1
export GTA_SIMULATION=1
export POCL_MAX_PTHREAD_COUNT=2
exec python "$project/bridge/linux_bridge.py" "$@"
