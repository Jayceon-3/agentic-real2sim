# Project scripts

Run commands from the project root unless a guide says otherwise. SAM 3D Objects
is an experimental object-generation route; it does not change the pinned AHa-3D
baseline or automatically replace furniture in an accepted scene.

| Location | Purpose | Runtime |
| --- | --- | --- |
| [sam3d_objects/infer.py](sam3d_objects/infer.py) | Single-image/mask generation, provenance and profiling | Dedicated SAM 3D Objects GPU environment; validation only needs NumPy/Pillow |
| [sam3d_objects/import_blender.py](sam3d_objects/import_blender.py) | Import a generated static GLB into a saved room with explicit placement and AHa-3D semantics | Background Blender; no model inference |
| [sam3d_objects/env.sh](sam3d_objects/env.sh) | Source to restore the Great Lakes interactive environment | Bash and existing Anaconda/CUDA modules |
| [sam3d_objects/run.sh](sam3d_objects/run.sh) | Prepare, segment, record human review, generate and bundle one object case | Existing Pi3X/SAM3/SAM 3D runtimes |
| [sam3d_objects/setup.sh](sam3d_objects/setup.sh), [paths.sh](sam3d_objects/paths.sh) | Check/configure installed runtime paths | No model load or GPU allocation |
| [sam3d_objects/gpu.sh](sam3d_objects/gpu.sh) | Allocate and enter an interactive A40 session | Slurm |
| [slurm/sam3d_workflow.sbatch](slurm/sam3d_workflow.sbatch) | Run a single workflow GPU stage independently of SSH | Slurm |
| [slurm/sam3d_objects.sbatch](slurm/sam3d_objects.sbatch) | Great Lakes batch execution, independent of SSH | Slurm, course account, A40 |
| [tests/](tests/) | CPU checks for the new wrapper and batch launcher | Python, NumPy, Pillow; no model weights |
| [make_exp_worktree.sh](make_exp_worktree.sh) | Create a frozen `exp-*` worktree of `third_party/aha-3d` at a commit/tag | Git; shares runtimes by symlink |
| [new_experiment.sh](new_experiment.sh) | Open `experiments/EXP-NNN-slug/` with `env.json`, `record.md` and an `index.csv` row | Host shell, Codex, Blender, `nvidia-smi` |
| [exp_container.sh](exp_container.sh) | Run a command (usually `codex exec`) in the `aha3d-exp` container with only the worktree and records writable | Docker with GPU; image from `../docker/` |
| [codex_session_stats.py](codex_session_stats.py) | Sum tokens, time and API-equivalent cost over Codex session logs | Python standard library |
| [tum_contact_sheet.py](tum_contact_sheet.py), [tum_to_mp4.py](tum_to_mp4.py) | Pick a TUM RGB-D clip and write it as mp4 plus a frame/timestamp map | OpenCV |
| [eval_pi3x_tum_ate.py](eval_pi3x_tum_ate.py) | Pi3X camera ATE and Sim(3) scale against TUM ground truth | NumPy |
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
For the complete staged video/mask/GLB route with human review, use the
[Great Lakes workflow guide](sam3d_objects/WORKFLOW.md).

```bash
python3 -m unittest discover -s scripts/tests -v
```
