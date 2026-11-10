#!/bin/bash
#SBATCH --job-name=sam3d-stage
#SBATCH --account=eecs442f26_class
#SBATCH --partition=spgpu
#SBATCH --gres=gpu:a40:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=slurm-sam3d-stage-%j.out
set -euo pipefail
: "${SAM3D_PROJECT_ROOT:?Source scripts/sam3d_objects/paths.sh before submitting}"
case "${1:-}" in
    segment|generate|reference) ;;
    *) echo 'Usage: sbatch .../sam3d_workflow.sbatch segment|generate|reference --case /absolute/case' >&2; exit 2 ;;
esac
cd "$SAM3D_PROJECT_ROOT"
echo "Started $(date -u +%FT%TZ) job=$SLURM_JOB_ID host=$(hostname)"
exec srun bash scripts/sam3d_objects/run.sh "$@"
