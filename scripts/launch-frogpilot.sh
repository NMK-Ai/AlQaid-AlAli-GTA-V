#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/environment.sh"
cd /data/openpilot
source .venv/bin/activate
export PYTHONPATH=/data/openpilot
export QT_QPA_PLATFORM=xcb
export SCALE=$(python -c 'import json,sys; from pathlib import Path; p=Path(sys.argv[1]); c=json.loads((p/"config/project.json").read_text()); q=p/"config/local.json"; c.update(json.loads(q.read_text(encoding="utf-8-sig")) if q.exists() else {}); v=float(c.get("uiScale",.75)); assert .4 <= v <= 1.; print(v)' "$project")
export QT_SCALE_FACTOR=1
export QT_AUTO_SCREEN_SCALE_FACTOR=0
export GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA
export POCL_MAX_PTHREAD_COUNT=2
export OMP_NUM_THREADS=2
export GTA_SIMULATION=1
if [[ -f selfdrive/modeld/models/driving_vision_gta_cuda.pkl && -f selfdrive/modeld/models/driving_policy_gta_cuda.pkl ]]; then
  export GTA_MODEL_BACKEND=CUDA
fi
export SIMULATION=1
# Keep the ordinary CUDA artifacts intact for rollback. Select exactly one
# ModelState in modeld; the small model is never loaded alongside Cinque.
model_profile=default
profile_file="$project/runtime/model-profile.txt"
if [[ -f "$profile_file" ]]; then model_profile=$(tr -d '\r\n' < "$profile_file"); fi
unset GTA_BIG_MODEL GTA_BIG_MODEL_STATUS GTA_REGULAR_MODEL GTA_REGULAR_MODEL_STATUS
case "$model_profile" in
  default) ;;
  macrostiff)
    export GTA_REGULAR_MODEL=/data/gta-models/macrostiff
    export GTA_REGULAR_MODEL_STATUS=/dev/shm/gta-regular-model-status.json
    export GTA_MODEL_BACKEND=CUDA
    ;;
  cinque-driving)
    export GTA_BIG_MODEL=/data/gta-models/cinque-driving
    export GTA_BIG_MODEL_STATUS=/dev/shm/gta-big-model-status.json
    export GTA_MODEL_BACKEND=CUDA
    export LD_LIBRARY_PATH=/data/gta-models/cuda-runtime/nvidia/cublas/lib:/data/gta-models/cuda-runtime/nvidia/cudnn/lib:/data/gta-models/cuda-runtime/nvidia/cuda_runtime/lib:/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
    ;;
  *) echo "Unknown GTA model profile: $model_profile" >&2; exit 1 ;;
esac
export NOBOARD=1
export PASSIVE=0
export SKIP_FW_QUERY=1
export PYOPENCL_CTX=0
# Keep genuine rlogs for steering/performance diagnosis. Video encoding and
# service integrations still need PC adaptations.
# The GTA bridge owns livePose using actual game camera motion. Do not launch
# a second publisher (locationd). Model/planner/controls/UI remain genuine.
export BLOCK=mapd,manage_athenad,uploader,frogpilot_telemetry,speed_limit_filler,camerad,card,encoderd,micd,locationd
python "$project/scripts/apply-pc-patches.py"
python - <<'PY'
from openpilot.selfdrive.test.helpers import set_params_enabled
set_params_enabled()
PY
cd system/manager
# Background shells inherit SIGINT ignored. Reset it before exec so Python's
# normal KeyboardInterrupt handler is installed in manager and its children.
# Otherwise every onroad->offroad transition waits for repeated kill timeouts.
exec python -c 'import os, signal, sys; signal.signal(signal.SIGINT, signal.SIG_DFL); os.execv(sys.executable, ["python", "manager.py"])'
