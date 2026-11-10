#!/bin/bash
# Acquire and enter one interactive allocation; no model is launched here.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/paths.sh"
if [[ -n "${SLURM_JOB_ID:-}" ]]; then
    echo "Already inside Slurm job $SLURM_JOB_ID; do not allocate a second GPU." >&2
    exit 1
fi
if [[ "${1:-}" == --help ]]; then
    echo 'Usage: bash scripts/sam3d_objects/gpu.sh [--time=02:00:00] [other salloc options]'
    exit 0
fi
# salloc runs srun as its command, entering the node automatically after allocation.
exec salloc --account="$SAM3D_ACCOUNT" --partition="$SAM3D_PARTITION" \
    --gres="$SAM3D_GRES" --nodes=1 --ntasks=1 --cpus-per-task=4 --mem=32G \
    --time=02:00:00 --chdir="$SAM3D_PROJECT_ROOT" "$@" srun --pty bash -l
