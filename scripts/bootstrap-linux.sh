#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/environment.sh"
[[ $(id -u) == 0 ]] || { echo 'Run bootstrap as root in the dedicated project distribution.' >&2; exit 1; }
[[ $(cat /etc/frogpilot-gta-project) == "$project" ]] || { echo 'Distribution ownership mismatch'; exit 1; }
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || { echo 'Ubuntu 24.04 required'; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends git git-lfs ca-certificates sudo curl python3-venv
id frogpilot >/dev/null 2>&1 || useradd --create-home --shell /bin/bash frogpilot
mkdir -p /data /persist /cache
source_dir=/data/openpilot
git_user() { runuser -u frogpilot -- git "$@"; }
expected=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["frogpilot"]["commit"])' "$project/config/project.json")
if [[ ! -d "$source_dir/.git" ]]; then
  [[ ! -e "$source_dir" ]] || { echo 'Unexpected existing /data/openpilot; left untouched'; exit 1; }
  install -d -o frogpilot -g frogpilot "$source_dir"
  git_user init "$source_dir"
  git_user -C "$source_dir" remote add origin https://github.com/FrogAi/FrogPilot.git
fi
if ! git_user -C "$source_dir" rev-parse --verify HEAD >/dev/null 2>&1; then
  git_user -C "$source_dir" fetch --depth=1 origin "$expected"
  git_user -C "$source_dir" checkout --detach FETCH_HEAD
fi
[[ $(git_user -C "$source_dir" rev-parse HEAD) == "$expected" ]] || { echo 'FrogPilot source pin mismatch'; exit 1; }
cd "$source_dir"
git_user submodule update --init --recursive
git_user lfs pull
bash tools/install_ubuntu_dependencies.sh
apt-get install -y --no-install-recommends pocl-opencl-icd clinfo dbus-x11 mesa-utils libasound2-plugins pulseaudio-utils
chown -R frogpilot:frogpilot /data /persist /cache
echo 'Linux dependencies installed.'
