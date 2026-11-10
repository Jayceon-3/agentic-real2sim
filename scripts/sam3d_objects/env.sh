#!/bin/bash
# Source from a Great Lakes Bash session; this script does not allocate a GPU.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "Use: source scripts/sam3d_objects/env.sh" >&2
    exit 1
fi

if ! type module >/dev/null 2>&1; then
    echo "Great Lakes module command is unavailable in this shell." >&2
    return 1
fi

SAM3D_WORK="$(cd ~/eecs442_scratch/real2sim/sam3d-objects && pwd -P)" || return 1
export SAM3D_WORK

module load python3.11-anaconda/2024.02 || return 1
source "$(conda info --base)/etc/profile.d/conda.sh" || return 1
conda activate "$SAM3D_WORK/envs/sam3d-objects" || return 1

# Load after Conda activation so nvcc resolves to the validated cluster toolkit.
module load cuda/12.1.1 || return 1
export CUDA_HOME=/sw/pkgs/arc/cuda/12.1.1
export PATH="$CUDA_HOME/bin:$PATH"
unset NVCC_PREPEND_FLAGS NVCC_APPEND_FLAGS

export HF_HOME="$SAM3D_WORK/cache/huggingface"
export PIP_CACHE_DIR="$SAM3D_WORK/cache/pip"
export TORCH_EXTENSIONS_DIR="$SAM3D_WORK/cache/torch-extensions"
export WARP_CACHE_PATH="$SAM3D_WORK/cache/warp"
export LIDRA_SKIP_INIT=true
export MAX_JOBS=2
export TORCH_CUDA_ARCH_LIST="8.6"
export PIP_EXTRA_INDEX_URL="https://download.pytorch.org/whl/cu121"

# Resolve project paths from this file, independent of the current directory.
SAM3D_PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)" || return 1
export SAM3D_PROJECT_ROOT
export SAM3D_SRC="$SAM3D_WORK/src/sam-3d-objects"
export MODEL_CONFIG="$SAM3D_WORK/checkpoints/hf-download/checkpoints/pipeline.yaml"

printf 'SAM3D environment ready\nPython: %s\nCUDA: %s\nRuntime: %s\n' \
    "$(command -v python)" "$CUDA_HOME" "$SAM3D_WORK"
