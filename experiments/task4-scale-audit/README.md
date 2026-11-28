# Task 4 Scale Audit and Coordinate Alignment

The Office48 chair experiment measures and corrects a known object-level
transform error. The TUM experiment checks recovery of a known global scale
factor on a held-out set of motion-capture camera centers. Both are controlled
experiments. The historical TUM measurement of approximately 8% remains open.

## Coordinate contract

| Stage | Coordinates and checks |
| --- | --- |
| Video and camera | Source frame indices are zero-based. In the baked Office48 timeline, source frame `n` maps to Blender frame `n + 1`. Camera poses are `c2w` in the OpenCV camera basis, with X right, Y down and Z forward. Prepare `K` for the destination raster. The Office48 preparation adds 0.5 to the integer-index principal point before resizing from 672 × 378 to 1280 × 720. [Camera preparation](../../scripts/prepare_office48_import.py) |
| Pi3X and aligned room world | The reference geometry and cameras must agree on `world_transform`. The saved `display_vertices` and `c2w` already share the aligned Z-up world, so the Blender reference importer uses those coordinates directly. The recorded scene scale length of 1 establishes a unit convention. Physical scale still needs a metric reference. [Reference importer](../../scripts/blender_import_office48.py) · [Input lock](../office48-baseline-001/inputs.lock.json) |
| Blender camera | For column vectors, `C_blender = C_opencv @ diag(1, -1, -1, 1)` changes the camera-local basis while preserving the world position. Blender looks along local `-Z` with local `+Y` up. Apply this camera basis conversion once when translating an OpenCV camera to Blender. To project a world point with OpenCV intrinsics, use `inverse(C_opencv)` first. [Camera registration](../office48-baseline-001/REGISTRATION.md) |
| SAM 3D and GLB | Treat native `pose.json` as model output and the exported `object.glb` as an asset. Confirm the exporter convention before attempting a native-pose conversion. glTF uses a right-handed, Y-up asset coordinate system and specifies metres. Blender's glTF importer handles its basis conversion. The observed asset size and facing still need inspection. [SAM 3D interface](../../scripts/sam3d_objects/README.md#outputs-and-interpretation) · [glTF coordinate specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#coordinate-system-and-units) |
| Imported asset and Blender room | The placement JSON maps the already imported geometry into room world with `p_world = T @ R_xyz @ S @ p_imported`. Positive scale factors act about the imported root origin, XYZ Euler input is in degrees, and translation follows the room unit convention. The adapter applies the matrix at the semantic root while retaining child transforms. [Placement implementation](../../scripts/sam3d_objects/import_blender.py) |

Check incorrect axis swaps by inspecting the world matrix, expected forward/up,
and determinant. Check inherited scale using both the root's local scale and
world-axis lengths. The audit reports the maximum dot product between normalized
world basis columns so a non-orthogonal basis is visible before interpreting
Euler angles. Check misplaced support using the object's bounding-box minimum Z
and an explicitly selected horizontal support's maximum Z. This metric assumes
a flat surface at that height and does not measure mesh contact or penetration.

Global and local scale need separate checks. A uniform factor applied to camera
centers and scene geometry scales each camera-relative 3D vector equally. In a
perspective image, division by depth cancels the factor, so even good silhouettes
can coexist with a global metric error. A single mesh's placement scale records
the change from imported mesh size to room size. To measure metric scene scale,
use an independent known length, depth, or a time-matched metric camera path.

## Office48 controlled object correction

Use the public editable Office48 scene with its saved cameras. The run used the
static `furniture/guest_chair_0` hierarchy and `furniture/rug` as the horizontal
support. The shared SAM 3D B-run target is `furniture/chair-guest-1` in a separate
team scene. Use the existing B-run files and visible source masks to measure that
target. Its mesh and the original baseline scene are distributed separately.
[Public Office48 scene](https://github.com/KevinXu02/aha-3d/blob/main/examples/office48/whitebox.blend) · [Team input lock](../office48-sam3d-ab/results/agent-run-001/input-lock.json) · [B-run artifact notes](../office48-sam3d-ab/results/agent-run-001/README.md)

Run from the repository root with Blender 5.2. On macOS set `BLENDER_BIN` to the
executable inside the app bundle, for example
`/Applications/Blender.app/Contents/MacOS/Blender`. An isolated Python 3.13
runtime with the official `bpy==5.2.1` module also works. In that case use
`"$BLENDER_PY" scripts/audit_blender_placement.py` followed by the same script
arguments. Use a new JSON output path for each run. Data and generated files
belong under the existing ignored directories.

```bash
mkdir -p outputs/task4-dev outputs/task4-scale-audit
curl -fL https://raw.githubusercontent.com/KevinXu02/aha-3d/main/examples/office48/whitebox.blend \
  -o outputs/task4-dev/whitebox.blend
shasum -a 256 outputs/task4-dev/whitebox.blend

conda run -n eecs545_env "$BLENDER_BIN" --background --python-exit-code 1 \
  --python scripts/audit_blender_placement.py -- \
  --scene outputs/task4-dev/whitebox.blend \
  --object furniture/guest_chair_0 --support furniture/rug \
  --demo --scale-factor 1.08 --lift-z 0.10 --eval-blender-frames 31 196 241 \
  --out outputs/task4-scale-audit/office48-rerun.json
```

The input SHA-256 is `a2836f1b6ecf24291b554b75c5d16d42e5b7f1cc252c812f855282990bcf1f97`.
For a read-only audit, omit `--demo`, its scale/lift parameters and evaluation
frames. `--object` accepts a semantic `instance_id` or an exact Blender name.
The report contains the world bounds of the evaluated mesh hierarchy, position,
rotation, local and world scale information, the transform, and optional support
clearance. Demo edits are in memory and the source file hash is checked again.

The demo injected a uniform scale of 1.08 and increased Z clearance by 0.10
scene units. The correction fits scale from the known clean height, then matches
the known clean clearance. It reads no score from an evaluation view. We then
project the clean, perturbed and corrected world boxes at Blender frames 31,
196 and 241, the source indices 30, 195 and 240 used for the team's chair
evaluation split. The projected edge error is the mean absolute difference of
the four pixel edges relative to the clean scene. The boxes include occluded
geometry and measure projected extent. Visible-mask IoU and source fidelity
are outside this run. [Blender projection function](https://docs.blender.org/api/5.2/bpy_extras.object_utils.html#bpy_extras.object_utils.world_to_camera_view)

| Measurement | Clean | Perturbed | Corrected |
| --- | ---: | ---: | ---: |
| Chair height in scene units | 0.866185 | 0.935480 | 0.866185 |
| Clearance above the rug in scene units | 0.008110 | 0.108110 | 0.008110 |
| Projected edge error, frame 31 | 0 px | 15.61 px | < 0.0001 px |
| Projected edge error, frame 196 | 0 px | 18.89 px | < 0.0001 px |
| Projected edge error, frame 241 | 0 px | 24.70 px | < 0.0001 px |

The fitted factor was `0.92592583`. The audit and demo took about 0.04 s in
Blender 5.2.1 on an Apple M4 MacBook Air once the Blender runtime was loaded.
They used CPU geometry and projection and excluded process startup, rendering
and model inference. [Office48 run JSON](results/office48-whitebox.json)

## TUM global-scale control and historical audit

The [course proposal](../../proposal_dingxuan_yingzeng_yikeyuan_xshaoyi_nuvole.pdf)
reports approximately 8% scene-scale error after two early TUM RGB-D office
runs. The proposal does not specify the error direction, measured length, or
method. The [experiment archive index](../README.md#layout) documents that the
early TUM records and outputs live outside Git. The saved estimated trajectory
and its clip-specific source-frame map are unavailable in the current checkout.

The calibration control fetches the public motion-capture trajectory of
`freiburg3_long_office_household`. It creates 24 estimated positions by scaling
the truth by 1.08, rotating about Z and translating. The evaluator matches
timestamps within 0.02 seconds, fits a rigid transform and a similarity
transform on 12 matches, and reports camera-center absolute trajectory error
(ATE) on the other 12. Estimated positions in this control are constructed from
motion capture. A real Pi3X run supplies its own `cameras.json` instead.
[TUM RGB-D benchmark](https://webshare.cvg.cit.tum.de/g/rgbd/dataset/)

```bash
mkdir -p data/local/tum outputs/task4-scale-audit
curl -fL https://webshare.cvg.cit.tum.de/g/rgbd/dataset/freiburg3/rgbd_dataset_freiburg3_long_office_household-groundtruth.txt \
  -o data/local/tum/freiburg3_long_office_household-groundtruth.txt

conda run -n eecs545_env python experiments/task4-scale-audit/build_tum_scale_control.py \
  --ground-truth data/local/tum/freiburg3_long_office_household-groundtruth.txt \
  --out outputs/task4-scale-audit/tum-rerun
conda run -n eecs545_env python scripts/eval_pi3x_tum_ate.py \
  outputs/task4-scale-audit/tum-rerun/cameras.json \
  outputs/task4-scale-audit/tum-rerun/frames.json \
  data/local/tum/freiburg3_long_office_household-groundtruth.txt \
  --holdout-every 2 --out outputs/task4-scale-audit/tum-rerun/scale-audit.json
```

The correction factor `GT / estimate` was `0.9259259259`, corresponding to an
estimate **8.00% larger than the reference**. Held-out rigid-only RMSE was
**0.16886 m**. Similarity-aligned RMSE was below `10⁻¹² m` in this exact control.
It validates the sign of the reported scale and the implementation's ability
to recover an injected bias. [TUM control JSON](results/tum-scale-control.json)

For historical verification, recover the original TUM `cameras.json`, its
matching video-frame-to-TUM timestamp map and the original run's metric ground
truth or measured lengths. Run the same evaluator with those three files. Use
the original frame selection and fit protocol to reproduce the reported
number, and use `--holdout-every 2` for an additional held-out check. A metric
camera trajectory estimates the scale of the camera path. Apply it to room
geometry only after confirming the room and cameras share the same world basis
and that the residuals support one uniform factor. A distorted or poorly
associated trajectory needs inspection before accepting a scale factor.

## Next experiment

Continue the geometry audit as a preflight for SAM 3D imports. For the team
chair, recover the saved scene and its reference assets, document how target
dimensions are established, and measure the correction with the team's fixed
visible-mask verifier. Keep the TUM metric check separate from that object
test. The current results justify both checks in the pipeline while leaving
the prevalence and cause of real scene-scale errors undetermined.
