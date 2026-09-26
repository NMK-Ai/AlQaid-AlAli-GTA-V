#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/environment.sh"
exec 9>/tmp/openpilot-gta.lock
flock -n 9 || { echo 'Project already running'; exit 0; }
echo $$ > "$project/runtime/linux-supervisor.pid"
children=()
cleanup() {
  trap - EXIT INT TERM
  if ((${#children[@]})); then
    # manager's unblock_stdout forks a child which owns all process cleanup.
    # Signal that child before its stdout-forwarding parent can exit.
    manager_children=()
    for child in "${children[@]}"; do
      while read -r grandchild; do
        if [[ -n "$grandchild" ]]; then
          manager_children+=("$grandchild")
          kill -TERM "$grandchild" 2>/dev/null || true
        fi
      done < <(pgrep -P "$child" -f '^python manager.py' || true)
    done
    # Keep the stdout parent and supervisor alive until manager's own cleanup
    # finishes, so their inherited flock cannot outlive the readiness PID file.
    for grandchild in "${manager_children[@]}"; do
      while kill -0 "$grandchild" 2>/dev/null; do sleep .1; done
    done
    kill -TERM "${children[@]}" 2>/dev/null || true
    wait "${children[@]}" 2>/dev/null || true
  fi
  rm -f "$project/runtime/linux-supervisor.pid"
}
trap cleanup EXIT INT TERM
/data/openpilot/.venv/bin/python "$project/scripts/apply-pc-patches.py"
PYTHONPATH=/data/openpilot /data/openpilot/.venv/bin/python "$project/scripts/configure-gta-features.py"
bash "$project/scripts/launch-bridge.sh" --enable-controls > "$project/reports/linux-bridge.log" 2>&1 &
children+=("$!")
sleep 2
bash "$project/scripts/launch-frogpilot.sh" > "$project/reports/frogpilot-manager-cuda.log" 2>&1 &
children+=("$!")
wait -n "${children[@]}"
