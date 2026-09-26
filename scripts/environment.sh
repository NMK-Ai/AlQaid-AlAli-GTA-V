#!/usr/bin/env bash
# Shared by all Linux entry points; works when the clone path contains spaces.
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
export GTA_PROJECT_ROOT="$project"
mkdir -p "$project/runtime" "$project/reports"
export PATH="$HOME/.local/bin:$PATH"
# The tested tinygrad version can compile PTX without a Linux CUDA toolkit.
# The NVIDIA Windows driver supplies libcuda through WSL.
export CUDA_PTX=1
export LD_LIBRARY_PATH=/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
