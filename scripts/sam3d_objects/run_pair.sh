#!/usr/bin/env bash
# Run from the repository root on an allocated Great Lakes GPU node.
set -eo pipefail
inputs="$PWD/rear_chair_inputs"
source scripts/sam3d_objects/env.sh
set -u
for frame in 1350 1530; do
  "$SAM3D_ENV/bin/python" -u scripts/sam3d_objects/infer.py --image "$inputs/$frame/rgb.png" \
    --mask "$inputs/$frame/mask.png" --input-metadata "$inputs/$frame/source.json" \
    --upstream "$SAM3D_SRC" --checkpoint "$MODEL_CONFIG" --seed 42 \
    --object-id rear-wooden-chair --out "$inputs/results/$frame"
done
