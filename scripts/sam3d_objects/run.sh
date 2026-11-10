#!/bin/bash
# Lightweight stage dispatcher; only generation activates the SAM 3D environment.
set -eo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/paths.sh"
if [[ "${1:-}" == generate ]]; then
    source "$SAM3D_PROJECT_ROOT/scripts/sam3d_objects/env.sh"
fi
if [[ -x "$SAM3D_ENV/bin/python" ]]; then
    SAM3D_CONTROL_PY="$SAM3D_ENV/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    SAM3D_CONTROL_PY="$(command -v python3)"
else
    module load "$SAM3D_CONDA_MODULE"
    SAM3D_CONTROL_PY="$(command -v python)"
fi
exec "$SAM3D_CONTROL_PY" "$SAM3D_PROJECT_ROOT/scripts/sam3d_objects/workflow.py" "$@"
