#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/environment.sh"
[[ $(id -un) == frogpilot ]] || { echo 'Build as frogpilot, not root'; exit 1; }
cd /data/openpilot
# scons spawns sub-shells (cythonize, etc.) that resolve tools from PATH;
# expose the project venv so the build works without prior activation.
export PATH="/data/openpilot/.venv/bin:$PATH"
# Pin the package manager, then use the upstream frozen Python lockfile.
if [[ ! -x "$HOME/.local/bin/uv" ]]; then
  python3 -m venv "$HOME/.local/share/frogpilot-gta-uv"
  "$HOME/.local/share/frogpilot-gta-uv/bin/pip" install uv==0.12.16
  mkdir -p "$HOME/.local/bin"
  ln -s "$HOME/.local/share/frogpilot-gta-uv/bin/uv" "$HOME/.local/bin/uv"
fi
uv sync --frozen --all-extras
uv pip install --python .venv/bin/python --target /data/gta-models/validation-deps onnxruntime==1.30.0
export PYTHONPATH=/data/openpilot
export PYOPENCL_CTX=0
.venv/bin/python "$project/scripts/apply-pc-patches.py"
# Apply Qt changes BEFORE building, including GTA-specific longitudinal settings,
# and rebrand the Arabic UI translations for the NMK-Ai distribution.
.venv/bin/python "$project/scripts/rebrand-translations.py"
.venv/bin/scons -j"${1:-4}"
.venv/bin/python "$project/scripts/download-model.py"
bash "$project/scripts/compile-macrostiff.sh"
.venv/bin/python "$project/scripts/validate-macrostiff.py"
.venv/bin/python "$project/scripts/install-macrostiff-profile.py"
echo 'FrogPilot and the locally compiled Macrostiff model are ready.'
