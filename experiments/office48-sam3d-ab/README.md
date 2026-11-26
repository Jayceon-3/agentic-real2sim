# Office48 A/B object reconstruction: B with resident SAM 3D Objects

This protocol compares original AHa-3D object reconstruction (A) with the added
SAM 3D Objects route (B), using a fixed room, source cameras and evaluation views.
The current implementation prepares and runs B. The same renderer and scorer
can evaluate A later. B-only measurements do not establish improvement over A.

## Experiment contract

| Setting | Value |
| --- | --- |
| Source | Locked Office48 RGB video: 303 frames, 30 fps, 1280 x 720 |
| Common room | `outputs/office48-baseline-001/blender/furnished-v006/room.blend` |
| Common camera | `outputs/office48-baseline-001/inputs/camera-v001/camera.npz` |
| Cabinet | `furniture/cabinet`, the floor cabinet near the windows |
| Chair | `furniture/chair-guest-1`, confirm its identity against the source |
| B candidates | Two objects x seeds 42, 43, 44 = six assets and six saved scenes |
| Generation | One process, one model session, serial mixed-object requests |
| Per-object views | One generation, two alignment, three evaluation frames |
| Alignment | Translation, rotation, uniform scale; one transform for all views |
| Primary score | Mean visible-mask IoU across the three evaluation views |

Each B scene replaces **one** target in the common room. All other objects,
including the other target, remain fixed. The existing room is an unaccepted
historical candidate, not a certified reconstruction or independent ground truth.
Its scene units are uncalibrated predicted metres. This is a local object-quality
experiment, not an end-to-end room-reconstruction benchmark.

The earlier generated Office48 **wall cabinet** is a different target from the
floor cabinet. The root-level `rear_chair_inputs/` belongs to TUM, not Office48.
Neither is an input to this protocol. Old isolated orange object renders include
occluded geometry and must not be used as visible-mask ground truth.

## 1. Prepare paths and select frames

Run commands from the repository root. CPU preparation/scoring needs Python
3.11+, NumPy and Pillow. Extraction needs an existing `ffmpeg` executable; use
`--ffmpeg /absolute/path/to/ffmpeg` if it is not on PATH. GPU generation uses the
already installed Great Lakes SAM 3D environment. Import/render uses configured
Blender with Cycles; Blender 5.2 compositor compatibility is supported.

```bash
mkdir -p outputs/office48-sam3d-ab
cp experiments/office48-sam3d-ab/manifest.example.json \
  outputs/office48-sam3d-ab/manifest.json
```

Edit the copied manifest. Paths are relative to the repository root, not to the
manifest. Leave the tracked template unchanged. For each object:

1. Confirm its exact source identity and corresponding scene semantic root.
   Record that decision in `identity_review`.
2. Select one clear, minimally occluded generation frame.
3. Select two additional views for placement/alignment.
4. Select three additional views with useful viewpoint changes for evaluation.
5. Replace all `null` frame fields with zero-based source indices in [0, 302].

The six frame indices must be distinct within an object; different objects may
share RGB frames. Inspect source visibility before generation. Reject unusable
targets before inspecting generated quality. If a target lacks enough useful
views, revise and document the protocol before running it rather than filling
slots with nearly identical frames. Changing the target IDs requires a deliberate
protocol/code revision because validation intentionally fixes these two targets.
Source 224 and 302 are candidate inspection views, not preselected evaluation
frames. The historical baseline saw earlier reference views, so describe these
as fixed evaluation views, not a strictly unseen test set.

After selecting frame indices:

```bash
python3 experiments/office48-sam3d-ab/run.py extract \
  --manifest outputs/office48-sam3d-ab/manifest.json \
  --out outputs/office48-sam3d-ab/frames
```

This extracts native RGB images and records video/image hashes and exact decoder
commands in `frames.json`. To browse candidate frames first, use `extract --frames
0 78 146 224 302 --out NEW_BROWSE_DIR`; use a new directory for the final selected
frame extraction. Extraction never resizes, crops or synthesizes source images.

## 2. Make and review masks

Create the mask paths named in the copied manifest. SAM3 or another segmentation
editor can produce drafts; inspect and correct them before setting `reviewed`
to `true`. Existing SAM3 case commands are described in
[the workflow guide](../../scripts/sam3d_objects/WORKFLOW.md#2-gpu-choose-interactive-or-batch-execution).
This experiment does not automatically choose a segmentation candidate.

Every mask must be a native-resolution, single-channel **L-mode PNG containing
only 0 and 255**. White identifies the visible target; black includes background,
chair-leg gaps and occluded portions. Avoid colored overlays, alpha masks and
automatically grayscale-converted overlays. Each object needs six masks, even
when the underlying RGB image is shared with another object.

If a person occludes a target and the static scene has no person, prefer another
frame. If necessary, add `"ignore": "outputs/.../ignore.png"` to that view. The
ignore mask follows the same binary format; white pixels are excluded identically
for A and B. Freeze ignore masks before looking at scores. Avoid using ignore
regions to conceal geometry or camera errors.

Review evaluation masks independently of A/B renders. These are reference
annotations; an unreviewed SAM3 prediction is not established ground truth.

## 3. Freeze inputs

```bash
python3 experiments/office48-sam3d-ab/run.py freeze \
  --manifest outputs/office48-sam3d-ab/manifest.json \
  --out outputs/office48-sam3d-ab/frozen-v1
```

Freeze checks object identities, role counts, disjoint frames, review flags,
mask raster/binary values, extraction hashes and video identity. It copies RGB,
masks and optional ignore masks into a new snapshot and records source scene,
camera and video hashes in `lock.json`. It does not decide whether viewpoints
are sufficiently different or annotations are accurate; human review supplies
those judgments. Do not edit the lock or its inputs. Any revision needs a new
snapshot and new run outputs.

Keep repository-relative source resources and snapshot structure intact when
transferring between machines. They must have identical bytes. The source blend
may depend on external assets; sync those dependencies too. The frozen snapshot
is not a fully packed portable scene.

## 4. Validate and generate B on Great Lakes

Transfer the experiment directory, current `scripts/sam3d_objects/infer.py`,
frozen inputs and unchanged source resources to the existing cluster checkout.
The old `sam3d-model-reuse/run.py` benchmark repeats a single request; use this
experiment's runner for different objects and seeds.

```bash
source scripts/sam3d_objects/paths.sh
python3 experiments/office48-sam3d-ab/run.py generate \
  --lock outputs/office48-sam3d-ab/frozen-v1/lock.json \
  --upstream "$SAM3D_SRC" --checkpoint "$MODEL_CONFIG" \
  --cuda-home "$SAM3D_CUDA_HOME" --validate-only \
  --out outputs/office48-sam3d-ab/validation-001
```

Validation requires NumPy/Pillow and existing source/config paths, but loads no
model. Run with a configured CPU Python if the login-node Python lacks packages.
Its status is `validated_only`, not a successful reconstruction.

Submit the actual GPU batch:

```bash
sbatch experiments/office48-sam3d-ab/run.sbatch \
  --lock "$SAM3D_PROJECT_ROOT/outputs/office48-sam3d-ab/frozen-v1/lock.json" \
  --out "$SAM3D_PROJECT_ROOT/outputs/office48-sam3d-ab/generation-001"
```

The serial order is cabinet 42, chair 42, cabinet 43, chair 43, cabinet 44, chair
44. The first request initializes the model; the other five must report
`session.reused=true`. All requests use the same source, checkpoint and CUDA
toolkit. Each retains GLB, native pose, source identities, wrapper provenance,
timings and events. Optional splat export is off for all six.

`generation-001/batch.json` records request order, PID, statuses, cleanup memory
and total batch time including initialization. Per-request outputs live under
`cabinet/seed-42/`, `chair/seed-42/`, etc. Memory fields cover PyTorch allocations,
not the whole CUDA process. Mixed-input reuse still needs real GPU validation;
same-input historical timing is not proof of mixed-input quality or stability.

One failed request stops the batch and preserves completed/partial requests.
SIGTERM attempts to record interruption; SIGKILL/OOM may leave status `running`.
Check Slurm status and logs. No automatic retry or overwrite is implemented. A
new attempt uses a new directory/session and retains the old cost/failure record.
Do not select only the best seed or silently replace failures.

## 5. Import and align each candidate

Copy `configs/sam3d_placement.example.json` into the run's alignment directory for
each candidate. Fill in translation, XYZ Euler degrees and one repeated positive
scale factor. Set `semantic_class` to the value in the manifest. The example's
identity transform is only a starting placeholder, not an aligned placement.

```bash
blender --background --python-exit-code 1 \
  --python experiments/office48-sam3d-ab/scene.py -- \
  --stage import --object cabinet \
  --lock outputs/office48-sam3d-ab/frozen-v1/lock.json \
  --glb outputs/office48-sam3d-ab/generation-001/cabinet/seed-42/object.glb \
  --placement outputs/office48-sam3d-ab/alignment/cabinet-seed-42.json \
  --out outputs/office48-sam3d-ab/scenes/cabinet-seed-42-v001
```

The command checks generated-asset provenance and uniform scale, then explicitly
replaces the exact semantic target in a new copy of the common scene. It never
applies native `pose.json` as scene placement. Import success/reopen checks do
not establish correct alignment, collision freedom or visual quality.

For each candidate, use only the two alignment frames to adjust the imported
semantic root's translation, rotation and uniform scale. Preserve its child
geometry/materials and all non-target scene objects. Record final placement,
operator time, number of iterations, input/output paths and unresolved support
or collision issues in `alignment/record.json`. Use a preregistered budget,
such as at most 10 operator minutes per candidate, identically for future A.
The code does not implement an automatic alignment solver or enforce manual time.

Use `scene.py --stage render --role alignment` and the scoring command below to
inspect alignment-view IoU. Every iteration needs new output directories. The
same transform must explain both alignment frames. Save interactive edits as a
new candidate; export its final transform into placement JSON and rerun import
from the unchanged common scene to produce a reproducible final scene. Never
save over the common scene. No per-view transform or nonuniform stretch is allowed.

Repeat for both objects and all three seeds. For future A, give each independently
authored candidate the same alignment rules and budget.

## 6. Freeze candidates, render and score evaluation views

Finish alignment for **all six candidates before inspecting evaluation scores**.
Record the selected scene paths and their hashes. After evaluation, corrections
belong to a new development run; keep the original evaluation result.

```bash
blender --background --python-exit-code 1 \
  --python experiments/office48-sam3d-ab/scene.py -- \
  --stage render --object cabinet --label B-seed-42 --role evaluation \
  --lock outputs/office48-sam3d-ab/frozen-v1/lock.json \
  --scene outputs/office48-sam3d-ab/scenes/cabinet-seed-42-final/scene.blend \
  --out outputs/office48-sam3d-ab/renders/cabinet-seed-42

python3 experiments/office48-sam3d-ab/run.py score \
  --lock outputs/office48-sam3d-ab/frozen-v1/lock.json \
  --renders outputs/office48-sam3d-ab/renders/cabinet-seed-42 \
  --out outputs/office48-sam3d-ab/metrics/cabinet-seed-42
```

The renderer uses CPU Cycles, 32 samples, the saved room's source camera and the
frozen raster. It checks all 303 camera poses/intrinsics against the cache. Source
frame `n` maps to Blender frame `n+1`. RGB and binary Object Index masks come from
the same render. Other objects remain present and occlude the target. Reference
geometry is hidden. Index masks are un-antialiased numeric data, unaffected by
RGB tone mapping. Inspect their behavior around glass/transparent surfaces;
avoid interpreting reflections as target segmentation. Renderer settings must
remain the same for A/B. Lighting/material edits to non-target objects are outside
the experiment contract and require manual checking.

B evaluation checks `experiment.json` and `import_report.json` beside the scene:
the selected file must match the final import hash, object, seed and frozen lock.
Re-import the final reviewed placement before evaluation; an interactively edited
scene without an updated import receipt is suitable for alignment inspection only.

`render.json` binds the scene, lock, RGB and mask hashes. The scorer rejects
modified masks, wrong locks, incomplete view sets, nonbinary/wrong-size masks
and GT with no scored foreground. It uses the whole raster with frozen ignore
regions; it does not crop, translate or resize predictions. Empty predicted masks
score zero. It writes `scores.json` and `per_view.csv` with intersections, unions
and per-view IoU. The per-run primary score is the unweighted mean over views.
Open representative RGB/mask overlays to check target identity and visibility
before interpreting numerical improvements. Automatic exits do not close review.

When launching Windows Blender from WSL, convert the script path and **every**
file/directory argument using `wslpath -w`; launch from a Windows-accessible path.
For example, replace `blender` with the configured executable and use
`--python "$(wslpath -w "$PWD/experiments/office48-sam3d-ab/scene.py")"`.
Linux paths passed unchanged to Windows Blender will not resolve correctly.

## 7. Aggregate B now, compare A later

```bash
python3 experiments/office48-sam3d-ab/run.py summarize \
  --scores outputs/office48-sam3d-ab/metrics/*/scores.json \
  --out outputs/office48-sam3d-ab/summary-001
```

Aggregate within each object/method, first averaging views per run, then runs.
Report the individual seeds, mean and sample standard deviation, plus scored
versus planned runs. Three seeds probe generator variation; multiple frames are
not independent experimental runs. Report generation/import/alignment failures
and costs separately; missing scores are not successes or zero-valued estimates.
Fix seed 42 for the main illustration and show all seeds in supplementary views.

Future A requires three independent original-tool authoring runs per object,
starting from the same room context with that target removed. Keep original
asset retrieval and procedural modeling capabilities, agent model/effort,
development evidence, repair budget and acceptance rules comparable. Use the
same locked evaluation inputs and renderer, with labels `A-run-1`, `A-run-2`,
`A-run-3`. Existing historical furniture is a debugging reference; duplicated
copies are not independent A runs. A and B results must be identified separately.

The full experiment eventually has 12 candidates: six A and six B. Compare IoU,
per-object failure rate, physical diagnostics, total reconstruction/alignment
time, agent usage and human minutes. Include B model startup in batch cost and
report its allocation separately from warm inference. Segmentation/review costs
also belong in the ledger. Historical A authoring cost is unknown unless measured;
do not compare warm B inference with full A authoring as an end-to-end speedup.

## Checks and implementation boundaries

```bash
python3 -m unittest discover -s experiments/office48-sam3d-ab/tests -p 'test_*.py' -v
python3 -m unittest discover -s scripts/tests -v
bash -n experiments/office48-sam3d-ab/run.sbatch

blender --background --factory-startup --python-exit-code 1 \
  --python experiments/office48-sam3d-ab/tests/blender_mask_smoke.py -- NEW_SMOKE_DIR
```

CPU tests use the actual inference wrapper with a fake model to check two images,
three seeds and one initialization, failure retention, frozen-input tamper
rejection, mask scoring and run accounting. The synthetic Blender test checks
binary masks and confirms that a foreground occluder decreases visible target
area. Neither test establishes real SAM quality, GPU stability or Office48
alignment. Actual selected inputs, reviewed masks, GPU generation, final scene
alignment and A/B results remain experimental work.

Local validation on November 25, 2026: seven experiment CPU tests and 39 existing
script tests passed. The synthetic check passed on Windows Blender 5.2.1 through
WSL: target pixels decreased from 676 isolated to 390 occluded, and the saved PNG
was L-mode with values 0/255. Evidence is in the ignored
`outputs/office48-sam3d-ab-smoke-004/` directory. Earlier smoke attempts are retained;
they exposed Blender 5.2 compositor API changes that were corrected. No real GPU
inference or selected Office48 evaluation was run as part of this validation.
