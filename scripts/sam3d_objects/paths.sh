#!/bin/bash
# Source to configure paths only: no activation, installation or GPU allocation.
SAM3D_PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)" || return 1
export SAM3D_PROJECT_ROOT
if [[ -f "${SAM3D_MACHINE_CONFIG:-$SAM3D_PROJECT_ROOT/configs/sam3d_objects.local.sh}" ]]; then
    source "${SAM3D_MACHINE_CONFIG:-$SAM3D_PROJECT_ROOT/configs/sam3d_objects.local.sh}" || return 1
fi
export SAM3D_WORK="${SAM3D_WORK:-$HOME/eecs442_scratch/real2sim/sam3d-objects}"
export SAM3D_ENV="${SAM3D_ENV:-$SAM3D_WORK/envs/sam3d-objects}"
export SAM3D_SRC="${SAM3D_SRC:-$SAM3D_WORK/src/sam-3d-objects}"
export MODEL_CONFIG="${MODEL_CONFIG:-$SAM3D_WORK/checkpoints/hf-download/checkpoints/pipeline.yaml}"
export AHA_ROOT="${AHA_ROOT:-$SAM3D_PROJECT_ROOT/third_party/aha-3d}"
export SAM3_RUNTIME="${SAM3_RUNTIME:-$AHA_ROOT/.runtime/sam3-segmentation}"
export SAM3_PY="${SAM3_PY:-$SAM3_RUNTIME/venv/bin/python}"
if [[ -z "${PI3X_PY:-}" ]]; then
    PI3X_PY="$AHA_ROOT/.runtime/pi3x-inference/venv/bin/python"
    if [[ ! -x "$PI3X_PY" && -x "$AHA_ROOT/.runtime/pi3x/venv/bin/python" ]]; then
        PI3X_PY="$AHA_ROOT/.runtime/pi3x/venv/bin/python"
    fi
fi
export PI3X_PY
export PI3X_MESH_PY="${PI3X_MESH_PY:-$AHA_ROOT/.runtime/pi3x-mesh/venv/bin/python}"
export PI3X_UPSTREAM="${PI3X_UPSTREAM:-$AHA_ROOT/external/Pi3}"
export PI3X_CHECKPOINT="${PI3X_CHECKPOINT:-$AHA_ROOT/.runtime/pi3x/checkpoint/model.safetensors}"
export SAM3D_CUDA_HOME="${SAM3D_CUDA_HOME:-/sw/pkgs/arc/cuda/12.1.1}"
export SAM3D_CONDA_MODULE="${SAM3D_CONDA_MODULE:-python3.11-anaconda/2024.02}"
export SAM3D_CUDA_MODULE="${SAM3D_CUDA_MODULE:-cuda/12.1.1}"
export SAM3D_ACCOUNT="${SAM3D_ACCOUNT:-eecs442f26_class}"
export SAM3D_PARTITION="${SAM3D_PARTITION:-spgpu}"
export SAM3D_GRES="${SAM3D_GRES:-gpu:a40:1}"
