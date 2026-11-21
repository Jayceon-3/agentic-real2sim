#!/bin/bash
#SBATCH --job-name=sam3d-reuse
#SBATCH --account=eecs442f26_class
#SBATCH --partition=spgpu
#SBATCH --gres=gpu:a40:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=07:00:00
#SBATCH --output=slurm-sam3d-reuse-%j.out
set -eo pipefail
: "${SAM3D_PROJECT_ROOT:?Export SAM3D_PROJECT_ROOT before submission}"
cd "$SAM3D_PROJECT_ROOT"
source scripts/sam3d_objects/env.sh
exec srun python -u experiments/sam3d-model-reuse/run.py "$@"
