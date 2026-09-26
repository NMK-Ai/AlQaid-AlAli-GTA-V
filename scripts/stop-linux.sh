#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/environment.sh"
if [[ -f "$project/runtime/linux-supervisor.pid" ]]; then
  supervisor=$(cat "$project/runtime/linux-supervisor.pid")
  if [[ -r /proc/$supervisor/cmdline ]] && grep -aq "$project/scripts/run-linux.sh" /proc/"$supervisor"/cmdline; then
    managers=()
    while read -r manager; do
      [[ -n "$manager" ]] || continue
      while read -r manager_child; do
        [[ -n "$manager_child" ]] && managers+=("$manager_child")
      done < <(pgrep -P "$manager" -f '^python manager.py' || true)
    done < <(pgrep -P "$supervisor" -f '^python manager.py' || true)
    kill -TERM "$supervisor"
    # An older background launch inherited SIGINT ignored. Its manager has
    # entered cleanup, but children ignore its ordinary interrupt request.
    # Give cleanup time, then terminate only those owned children gracefully.
    sleep 3
    for manager_child in "${managers[@]}"; do
      if [[ -r /proc/$manager_child/cmdline ]] && grep -aq 'manager.py' /proc/"$manager_child"/cmdline; then
        while read -r child; do
          [[ -n "$child" ]] && kill -TERM "$child" 2>/dev/null || true
        done < <(pgrep -P "$manager_child" || true)
      fi
    done
    exit 0
  fi
fi
