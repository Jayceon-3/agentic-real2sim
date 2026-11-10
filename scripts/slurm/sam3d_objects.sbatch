#!/bin/bash
#SBATCH --job-name=sam3d-object
#SBATCH --account=eecs442f26_class
#SBATCH --partition=spgpu
#SBATCH --gres=gpu:a40:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=slurm-sam3d-%j.out

# Submit from any directory with SAM3D_PROJECT_ROOT pointing to this checkout.
# Pass infer.py arguments after the sbatch filename. CLI sbatch options override
# the course-specific defaults above. Never put HF tokens in this script.
set -euo pipefail
: "${SAM3D_PROJECT_ROOT:?Export the absolute agentic-real2sim checkout path before sbatch}"
: "${SAM3D_WORK:?Export the absolute sam3d-objects runtime storage path before sbatch}"
SAM3D_PROJECT_ROOT="$(cd "$SAM3D_PROJECT_ROOT" && pwd -P)"
SAM3D_WORK="$(cd "$SAM3D_WORK" && pwd -P)"

module load "${SAM3D_CONDA_MODULE:-python3.11-anaconda/2024.02}"
# Conda activation hooks can reference unset variables.
set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${SAM3D_ENV:-$SAM3D_WORK/envs/sam3d-objects}"
set -u
module load "${SAM3D_CUDA_MODULE:-cuda/12.1.1}"
export CUDA_HOME="${SAM3D_CUDA_HOME:-/sw/pkgs/arc/cuda/12.1.1}"
export PATH="$CUDA_HOME/bin:$PATH"
unset NVCC_PREPEND_FLAGS NVCC_APPEND_FLAGS
export LIDRA_SKIP_INIT=true
export HF_HOME="$SAM3D_WORK/cache/huggingface"
export PIP_CACHE_DIR="$SAM3D_WORK/cache/pip"
export TORCH_EXTENSIONS_DIR="$SAM3D_WORK/cache/torch-extensions"
export WARP_CACHE_PATH="$SAM3D_WORK/cache/warp"
export MAX_JOBS="${SLURM_CPUS_PER_TASK:-4}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-8.6}"
export PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cu121
mkdir -p "$HF_HOME" "$PIP_CACHE_DIR" "$TORCH_EXTENSIONS_DIR" "$WARP_CACHE_PATH"
cd "$SAM3D_PROJECT_ROOT"
echo "Started $(date -u +%FT%TZ) job=$SLURM_JOB_ID host=$(hostname)"
which python
"$CUDA_HOME/bin/nvcc" --version
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
srun python -u scripts/sam3d_objects/infer.py \
  --upstream "${SAM3D_SRC:-$SAM3D_WORK/src/sam-3d-objects}" \
  --cuda-home "$CUDA_HOME" "$@"
