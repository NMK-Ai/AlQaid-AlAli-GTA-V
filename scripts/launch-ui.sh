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
export GTA_SIMULATION=1
python - <<'PY'
from openpilot.common.params import Params
from openpilot.system.version import terms_version, training_version
p = Params()
# Same onboarding state used by the upstream simulator; no cloud registration.
p.put('HasAcceptedTerms', terms_version)
p.put('CompletedTrainingVersion', training_version)
p.put_bool('OpenpilotEnabledToggle', True)
PY
cd selfdrive/ui
exec ./ui
