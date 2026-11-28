# Task 4 Scale Audit and Coordinate Alignment

The Office48 chair experiment measures and corrects an injected object-level
transform error. The archived TUM RGB-D office runs reproduce an 8.31%
underscale in the original Pi3X camera trajectory. A synthetic TUM control
checks the scale convention on held-out motion-capture camera centers.

| Task 4 check | Evidence |
| --- | --- |
| Camera, world, SAM 3D and Blender axes, units and transform order | [Coordinate contract](#coordinate-contract) |
| Read-only object dimensions, position, rotation, scale and floor clearance | [Object audit](../../scripts/audit_blender_placement.py) · [Measured chair](results/office48-sam3d-chair-seed42.json) |
| Scale and placement correction on the team's SAM 3D result | [Office48 reproduction](#office48-team-sam-3d-chair) · [Per-view silhouette scores](results/office48-sam3d-chair-seed42-silhouettes.json) |
| Historical discrepancy and check for a missing or repeated transform | [TUM reproduction](#historical-tum-scale-audit) · [Camera fit and transform measurements](results/tum-historical-scale.json) |

## Runtime and inputs

Run the commands from the repository root in Bash with a Python 3.11+
environment named `eecs545_env`, with NumPy and Pillow available. The TUM
checks need only Python and NumPy. Office48 additionally uses Blender 5.2.1
and `jq` for creating placement JSON. The Mac run reused the archived model
outputs and rendered with Cycles on CPU. It did not need CUDA, gated model
weights or a Slurm job.

Use a Blender application binary for the public whitebox smoke test. For the
team chair, create a separate Python 3.13 environment with Blender's
`bpy` wheel, as in the tested Mac setup.

```bash
export BLENDER_BIN=/Applications/Blender.app/Contents/MacOS/Blender
tools_dir="$PWD/outputs/task4-scale-audit/runtime"
mkdir -p "$tools_dir"
python3.13 -m venv "$tools_dir/blender-python"
export BLENDER_PY="$tools_dir/blender-python/bin/python"
"$BLENDER_PY" -m pip install 'bpy==5.2.1'
conda run -n eecs545_env python -c 'import numpy, PIL'
```

Use distinct output directories or report filenames for each run. Store the
shared Office48 bundle and TUM EXP archives locally. The extracted scenes,
meshes, masks, videos, original run records and renders live in Git-ignored
directories. The result JSONs in this guide record hashes and measurements.

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

This optional smoke test uses the public editable Office48 scene with its saved
cameras. The run used the static `furniture/guest_chair_0` hierarchy and
`furniture/rug` as the horizontal
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

## Office48 team SAM 3D chair

This run uses the team's archived `furniture/chair-guest-1` mesh (seed 42),
original placement, room camera track, and frozen evaluation masks. The shared
`office48-chair-seed42.tar.gz` supplies the placed scene, GLB and generation
receipts, frozen protocol inputs, furnished baseline scene, and camera cache.
Extract its `outputs/` tree at the repository root. Obtain the source video
separately. The render and score commands verify the locked source assets and
24 frozen files.
[Team run record](../office48-sam3d-ab/results/agent-run-001/README.md)

| Input | Repository-relative location |
| --- | --- |
| Final chair scene and import receipts | `outputs/office48-sam3d-ab/agent-run-001/scenes/chair-seed-42-final/` |
| Seed-42 GLB and generation receipts | `outputs/office48-sam3d-ab/generation-001/chair/seed-42/` |
| Evaluation masks, ignore regions and input lock | `outputs/office48-sam3d-ab/frozen-v1/` |
| Furnished baseline scene | `outputs/office48-baseline-001/blender/furnished-v006/room.blend` |
| Baked camera cache | `outputs/office48-baseline-001/inputs/camera-v001/camera.npz` |
| Source video | `data/local/office48/source.mp4` |

```bash
mkdir -p data/local/office48
video=data/local/office48/source.mp4
if [ ! -f "$video" ]; then
  curl -fL https://raw.githubusercontent.com/KevinXu02/aha-3d/main/references/office48/source.mp4 -o "$video"
fi

ab=outputs/office48-sam3d-ab
placed="$ab/agent-run-001/scenes/chair-seed-42-final/scene.blend"
out=outputs/task4-scale-audit/office48-sam3d-chair-seed42-rerun
mkdir -p "$out"
shasum -a 256 -c <<EOF
993af1f9c6a58d9df39a0d95309e4ed5fec489cce3d25a5d8c7b503827d0a724  $video
057f830499136ff2ff65bdac630e4b9281af1eae83376e97b1c0fb1962f5c083  $placed
50cd21a4d65e0f2e225b74d1f0ff205b1a7ead1b203ae2da6bd5294941c1c457  $ab/generation-001/chair/seed-42/object.glb
3ddca3bfe840d75e1c01369fe19ac9b5ad139feacd134df3a4f84268d01aa36f  $ab/frozen-v1/lock.json
EOF

conda run -n eecs545_env "$BLENDER_PY" -B scripts/audit_blender_placement.py \
  --scene "$placed" --object furniture/chair-guest-1 \
  --support architecture/floor --demo --scale-factor 1.08 --lift-z 0.10 \
  --eval-blender-frames 31 196 241 --out "$out/audit.json"
```

The original chair measures 0.666466 × 0.568162 × 0.897567 scene units
along world X, Y and Z, with a root placement scale of 0.897315 and a
Z rotation of −94.1254°. Its world translation is approximately
`[-0.244041, 2.372124, 0.465780]`. The audit measures evaluated Blender
meshes at saved frame 147. To correct the perturbation, scale about the
object origin by `original_height / perturbed_height`, then translate in
world Z by `original_clearance - clearance_after_scaling`. The three
evaluation views are scored after the transforms are fixed.

| Measurement | Original placement | Perturbed | Corrected |
| --- | ---: | ---: | ---: |
| Chair height in scene units | 0.897567 | 0.969373 | 0.897567 |
| Clearance above the floor in scene units | 0.017052 | 0.117052 | 0.017052 |
| Projected box edge error, source frame 30 | 0 px | 22.48 px | 0 px |
| Projected box edge error, source frame 195 | 0 px | 26.40 px | 0 px |
| Projected box edge error, source frame 240 | 0 px | 39.92 px | 0 px |

The fitted factor was 0.92592594. The audit took 0.084 s after Blender
startup on an Apple M4. The original placement serves as the reference for
this controlled correction. Absolute dimensions and floor contact still
require independent physical measurements. [Audit JSON](results/office48-sam3d-chair-seed42.json)

For silhouette verification, create the perturbed and corrected placements
from the audit, import the same GLB into the locked baseline for each, and
render all three candidates with the same settings. The locked scorer applies
the source masks and ignore regions at source frames 30, 195 and 240. Use the
repository's AHa-3D checkout when available. The Mac reproduction used the
public AHa-3D revision `82f4b1110cfe4b55fff19df3b3790852ce07b171` for the
Blender semantics and camera check because the pinned revision was unavailable.
If `third_party/aha-3d` is uninitialized, use a separate public checkout for
the tested fallback.

```bash
git clone --filter=blob:none --no-checkout https://github.com/KevinXu02/aha-3d.git "$tools_dir/aha3d-public"
git -C "$tools_dir/aha3d-public" sparse-checkout set src/aha3d
git -C "$tools_dir/aha3d-public" checkout --detach 82f4b1110cfe4b55fff19df3b3790852ce07b171
export PYTHONPATH="$tools_dir/aha3d-public/src"
```

```bash
# BLENDER_PY is the Python 3.13 executable with bpy 5.2.1.
# Reuse ab, placed and out from the audit command above.
lock="$ab/frozen-v1/lock.json"
glb="$ab/generation-001/chair/seed-42/object.glb"
placement=experiments/office48-sam3d-ab/results/agent-run-001/placements/chair-seed-42.json
blender_stage() {
  conda run -n eecs545_env "$BLENDER_PY" -Bc \
    'import bpy, runpy; bpy.context.preferences.filepaths.use_scripts_auto_execute = False; runpy.run_path("experiments/office48-sam3d-ab/scene.py", run_name="__main__")' \
    -- "$@"
}
for variant in original perturbed corrected; do
  candidate="$placed"
  if [ "$variant" != original ]; then
    jq -s --arg variant "$variant" '
      .[1].demo as $d
      | ($d.injected_uniform_scale
         * (if $variant == "corrected" then $d.fitted_uniform_scale else 1 end)) as $factor
      | .[0]
      | .scale |= map(. * $factor)
      | .translation_m = $d[$variant].location_world
      | .note = "Controlled Task 4 placement derived from the archived chair audit."
    ' "$placement" "$out/audit.json" > "$out/$variant-placement.json"
    blender_stage --stage import --object chair --lock "$lock" --glb "$glb" \
      --placement "$out/$variant-placement.json" --out "$out/$variant-scene"
    candidate="$out/$variant-scene/scene.blend"
  fi
  blender_stage --stage render --object chair --lock "$lock" --label B-seed-42 \
    --role evaluation --scene "$candidate" --samples 32 --device CPU \
    --out "$out/$variant-renders"
  conda run -n eecs545_env python -B experiments/office48-sam3d-ab/run.py score \
    --lock "$lock" --renders "$out/$variant-renders" --out "$out/$variant-score"
done
```

| Source frame | Original IoU | Perturbed IoU | Corrected IoU |
| --- | ---: | ---: | ---: |
| 30 | 0.878101 | 0.477458 | 0.878101 |
| 195 | 0.908482 | 0.450388 | 0.908482 |
| 240 | 0.848354 | 0.486584 | 0.848354 |
| Mean | 0.878312 | 0.471476 | 0.878312 |

The original per-view IoUs matched the historical results exactly. The
correction restored all three scores and increased the perturbed mean
by 0.406836. All candidates passed the camera check across 303 frames, with
a maximum intrinsic error of 1.080 px and maximum absolute camera-to-world
matrix element error of 4.91 × 10⁻⁷. On the Apple M4, the three CPU render
passes took 35.8, 41.3 and 38.6 s. Reimporting a variant took less than 0.5 s
after startup. These measurements exclude SAM 3D inference, which was reused
from the archive. The result covers one mesh and one combined controlled
perturbation. Height and clearance were supplied by the original scene.
The team's evaluation split had already been visible during mask annotation.
[Silhouette results](results/office48-sam3d-chair-seed42-silhouettes.json)

## Historical TUM scale audit

The [course proposal](../../proposal_dingxuan_yingzeng_yikeyuan_xshaoyi_nuvole.pdf)
reports approximately 8% scene-scale error after two early TUM RGB-D office
runs. The archived EXP-002 and EXP-003 run records identify the metric as
camera-center absolute trajectory error (ATE) after a similarity fit to the
metric motion-capture track. Each run used 32 poses from the 750-frame clip at
zero-based RGB indices 1350–2099 of `freiburg3_long_office_household`. The two
runs' raw prediction archives and corresponding camera exports are
byte-identical. They provide one independent camera trajectory for this audit.
[Experiment archive index](../README.md#layout)

The original evaluator at commit `465cd037` reproduced the archived
output for the Pi3X and alignment exports of both runs. All 32 poses matched
within 0.02 s on a 6.59 m reference path. The updated evaluator also fit on
16 poses and evaluated the other 16.

| Camera fit | GT / estimated scale | Estimate relative to GT | Rigid RMSE | Similarity RMSE |
| --- | ---: | ---: | ---: | ---: |
| Pi3X, all 32 | 1.090690 | −8.31% | 11.62 cm | 1.11 cm |
| Room-aligned, all 32 | 1.090690 | −8.31% | 11.62 cm | 1.11 cm |
| Pi3X, 16 fit / 16 held out | 1.090227 | −8.28% | 11.73 cm | 1.16 cm |

The correction multiplier is 1.090690 because the inverse scale,
`1 / 1.090690`, is the estimate as a fraction of the truth. Applying the
stored Pi3X world transform once to the 32 raw model poses reproduces
their exported camera matrices exactly. The room-aligned pose matrices
agree with `world_aligned @ inverse(world_pi3x) @ c2w_pi3x` within
`9e-16` per element. Both world transforms have unit scale to within
`5e-8` by the singular values of their 3 × 3 bases. The scale
discrepancy is already present in the raw camera trajectory and survives
room alignment. It measures the camera path's metric scale. Individual
room dimensions and object sizes still need independent measurements.
[TUM historical result JSON](results/tum-historical-scale.json)

Extract `EXP-002-baseline-tum-office.zip` and
`EXP-003-baseline-tum-office-auto-r2.zip` into `experiments/`. Each archive
expands to its own `EXP-*` directory. Section 3 of each `record.md`
identifies the source clip. Section 8.3 records the original metric.
Rebuild the frame map from the documented clip indices using the public
RGB index mirror and the official TUM motion-capture trajectory.
[TUM RGB-D benchmark](https://webshare.cvg.cit.tum.de/g/rgbd/dataset/)

```bash
work=outputs/task4-scale-audit/tum-historical-rerun
rgb=data/local/tum/freiburg3_long_office_household-rgb.txt
truth=data/local/tum/freiburg3_long_office_household-groundtruth.txt
exp002=experiments/EXP-002-baseline-tum-office-auto/worktree_outputs/runs/tum_office/reference32
exp003=experiments/EXP-003-baseline-tum-office-auto-r2/worktree_outputs/runs/tum_office/whitebox/reference
mkdir -p "$work" data/local/tum
curl -fL https://huggingface.co/datasets/voviktyl/TUM_RGBD-SLAM/resolve/main/rgbd_dataset_freiburg3_long_office_household/rgb.txt \
  -o "$rgb"
curl -fL https://webshare.cvg.tum.de/rgbd/dataset/freiburg3/rgbd_dataset_freiburg3_long_office_household-groundtruth.txt \
  -o "$truth"
shasum -a 256 -c <<EOF
9bc53b49d65090bf7fe519123a7c1d0561c53672576d781a81b63088765c15dd  $rgb
e255d5d9c5bab915132c7ac5ec4e23f9f1efe98f765b0c9b26ac74e40b02533f  $truth
EOF

conda run --no-capture-output -n eecs545_env python -B - "$rgb" "$work/frames.json" <<'PY'
import json
from pathlib import Path
import sys

rgb, output = map(Path, sys.argv[1:])
rows = [line.split() for line in rgb.read_text().splitlines()
        if line.strip() and not line.startswith("#")]
assert len(rows) >= 2100
mapping = {
    "source": "rgbd_dataset_freiburg3_long_office_household/rgb.txt",
    "tum_index_range": [1350, 2100],
    "frames": [{"video_frame": i, "tum_timestamp": float(stamp), "file": name}
               for i, (stamp, name) in enumerate(rows[1350:2100])],
}
with output.open("x") as stream:
    json.dump(mapping, stream, indent=1, allow_nan=False)
    stream.write("\n")
PY
git show 465cd037:scripts/eval_pi3x_tum_ate.py > "$work/historical-evaluator.py"
for run in exp002 exp003; do
  root="$exp002"
  if [ "$run" = exp003 ]; then root="$exp003"; fi
  for stage in pi3x alignment; do
    camera="$root/$stage/cameras.json"
    conda run -n eecs545_env python "$work/historical-evaluator.py" "$camera" "$work/frames.json" "$truth"
    conda run -n eecs545_env python scripts/eval_pi3x_tum_ate.py \
      "$camera" "$work/frames.json" "$truth" --out "$work/$run-$stage.json"
  done
done
conda run -n eecs545_env python scripts/eval_pi3x_tum_ate.py \
  "$exp002/pi3x/cameras.json" "$work/frames.json" "$truth" \
  --holdout-every 2 --out "$work/exp002-pi3x-holdout.json"
```

Check the raw-to-export transform and the scale of both world bases using
the same camera archives.

```bash
conda run --no-capture-output -n eecs545_env python -B - "$exp002" <<'PY'
import json
from pathlib import Path
import sys

import numpy as np

root = Path(sys.argv[1])
pi3x, aligned = [
    json.loads((root / stage / "cameras.json").read_text())
    for stage in ("pi3x", "alignment")
]
pi3x_world = np.array(pi3x["world_transform"])
aligned_world = np.array(aligned["world_transform"])
pi3x_poses = np.array([frame["c2w"] for frame in pi3x["frames"]])
aligned_poses = np.array([frame["c2w"] for frame in aligned["frames"]])
with np.load(root / "pi3x" / "predictions.npz", allow_pickle=False) as data:
    raw_poses = data["camera_poses"]
print("Raw-to-Pi3X max error:", np.abs(pi3x_world @ raw_poses - pi3x_poses).max())
expected = aligned_world @ np.linalg.inv(pi3x_world) @ pi3x_poses
print("Pi3X-to-room max error:", np.abs(expected - aligned_poses).max())
for label, matrix in (("Pi3X", pi3x_world), ("Room", aligned_world)):
    print(label, "world basis singular values:", np.linalg.svd(matrix[:3, :3], compute_uv=False))
PY
```

## Synthetic TUM scale control

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

## Next experiment

Use the geometry audit as a preflight for SAM 3D imports. For an unknown
placement error, obtain an independent target dimension and support height
before applying a correction. Test whether a single scale correction carries
from the TUM camera path to independent depth or room dimensions.
