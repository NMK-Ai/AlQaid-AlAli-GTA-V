#!/usr/bin/env bash
set -euo pipefail
for file in "$(dirname "${BASH_SOURCE[0]}")"/*.sh; do bash -n "$file"; done
echo 'All shell entry points parse.'
