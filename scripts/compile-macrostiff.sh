#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/environment.sh"
cd /data/openpilot
export PYTHONPATH=/data/openpilot:/data/gta-models/validation-deps
export DEV=CUDA SELFTEST=1 OMP_NUM_THREADS=2
.venv/bin/python "$project/scripts/prepare-macrostiff.py"
for kind in vision policy; do
  logfile="/data/gta-models/macrostiff/${kind}-precise-compile.log"
  .venv/bin/python tinygrad_repo/examples/openpilot/compile3.py \
    "/data/gta-models/macrostiff/driving_${kind}_precise.onnx" \
    "/data/gta-models/macrostiff/driving_${kind}_gta_cuda.pkl" > "$logfile" 2>&1 || {
      tail -n 30 "$logfile"
      exit 1
    }
  tail -n 5 "$logfile"
done
