# Project scripts

Run commands from the project root unless a guide says otherwise. SAM 3D Objects
is an experimental object-generation route; it does not change the pinned AHa-3D
baseline or automatically replace furniture in an accepted scene.

| Location | Purpose | Runtime |
| --- | --- | --- |
| [sam3d_objects/infer.py](sam3d_objects/infer.py) | Single-image/mask generation, provenance and profiling | Dedicated SAM 3D Objects GPU environment; validation only needs NumPy/Pillow |
| [slurm/sam3d_objects.sbatch](slurm/sam3d_objects.sbatch) | Great Lakes batch execution, independent of SSH | Slurm, course account, A40 |
| [tests/](tests/) | CPU checks for the new wrapper and batch launcher | Python, NumPy, Pillow; no model weights |
| Existing `*office48*.py` files below | Historical Office48 baseline authoring and review | See table |

The existing Office48 entry points remain at their original paths because scripts,
experiment records and artifact receipts refer to them. New tools are grouped by
capability instead of adding more unrelated files at the root. Do not move old
scripts without updating their root discovery, imports and provenance references.

## Office48 script map

| Stage | Existing scripts |
| --- | --- |
| Locked inputs and camera preparation | `check_office48_inputs.py`, `prepare_office48_import.py` |
| Reference import (Blender) | `blender_import_office48.py` |
| Measurements | `measure_office48_room.py` |
| Architecture and furniture (Blender) | `build_office48_room.py`, `furnish_office48_room.py`, `office48_furniture_parts.py` (helper module) |
| Repair and review (Blender) | `repair_office48_candidate.py`, `review_office48_room.py` |
| Comparison sheets | `make_office48_comparisons.py` |
| Preview preparation/rendering (Blender) | `render_office48_preview.py` |
| Preview packaging | `package_office48_preview.py` |

The historical invocation details live in
[BUILDING.md](../experiments/office48-baseline-001/BUILDING.md) and
[PREDELIVERY.md](../experiments/office48-baseline-001/PREDELIVERY.md).

## SAM 3D Objects

See [the run guide](sam3d_objects/README.md) for validation, direct execution,
Slurm submission, output schemas and performance boundaries.

```bash
python3 -m unittest discover -s scripts/tests -v
```
