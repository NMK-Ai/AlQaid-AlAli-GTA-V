#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) == 0 ]] || exit 1
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
marker=/etc/frogpilot-gta-project
if [[ -f "$marker" && $(cat "$marker") != "$project" ]]; then
  echo 'Distribution belongs to another clone' >&2
  exit 1
fi
printf '%s\n' "$project" > "$marker"
