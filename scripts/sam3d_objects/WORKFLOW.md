# Great Lakes: From Video to a Single-Object GLB

These entry points reuse the installed **separate Pi3X, SAM3 and SAM 3D Objects environments** without reinstalling or upgrading them. Each `CASE` fixes one video, source frame, object and text prompt. Model stages can be repeated, each in a new directory. Mask review and final asset review are recorded separately; a successful exit does not establish visual acceptance.

```text
Check runtime paths → Prepare source frame → SAM3 candidates → [Human mask review]
                                                                      ↓
                                               Validate inputs → SAM 3D → GLB
                                                                      ↓
                                                   [Human Blender review] → Bundle

Optional for a new room: Pi3X + SAM3 + Open3D → reference geometry/cameras → review
Reuse the existing Office48 reference when generating an individual furniture asset.
```

## 0. Sync Code and Configure Paths

Work in the existing `agentic-real2sim` checkout on Great Lakes and sync the new code first. The default runtime directory is `~/eecs442_scratch/real2sim/sam3d-objects`. If installed environments use other locations:

```bash
cp configs/sam3d_objects.example.sh configs/sam3d_objects.local.sh
# Edit local.sh with the actual SAM3_PY, SAM3_RUNTIME, PI3X_PY and other paths.
```

`local.sh` is gitignored. Never store tokens in it. In each new terminal:

```bash
source scripts/sam3d_objects/paths.sh
bash scripts/sam3d_objects/setup.sh
```

This checks file paths without loading models or allocating a GPU. Moving to a new machine still requires installation and authorized weights according to the official documentation. The script does not fabricate runtime.json or automatically patch dependencies. To also check Pi3X/Open3D dependencies for a new room:

```bash
bash scripts/sam3d_objects/setup.sh --reference
```

The existing installation retains the validated compatibility fixes: locally built Kaolin 0.17.0, cluster CUDA 12.1.1 and a run-local correction of the inference entry point's CUDA_HOME assignment. Preserve the working Kaolin build instead of replacing it with a precompiled wheel.

## 1. CPU: Prepare a Case

Choose a new directory rather than a directory from an existing manual experiment.

```bash
export CASE="$SAM3D_PROJECT_ROOT/outputs/sam3d-cases/office48-cabinet-f000-v001"

bash scripts/sam3d_objects/run.sh prepare \
  --case "$CASE" \
  --video "$SAM3D_PROJECT_ROOT/data/local/office48/source.mp4" \
  --frame 0 \
  --object-id office48-wall-cabinet \
  --label "wall-mounted wooden cabinet" \
  --bbox-relative 0.80 0.10 0.99 0.64
```

If a `reference_build.json` already exists, optionally add `--reference-build /absolute/reference_build.json`. This records its path and hash without recomputation or visual acceptance.

- `--frame` is the zero-based native video frame, not the Blender frame.
- `--label` is the text prompt supplied to SAM3.
- `--bbox-relative` specifies left, top, right and bottom in the range 0–1, scaled to the native image dimensions.
- Alternatively, use `--bbox LEFT TOP RIGHT BOTTOM` for native pixel coordinates. The two forms are mutually exclusive.
- The Office48 box above is the previously used rough selection, not a universal cabinet box.

Preparation uses **the Pi3X environment's Python and the existing decoding tool** to extract RGB; it does not load the Pi3X model. `source/` retains the image, video hash, frame ID, decoder-reported timestamp and dimensions. `sam3-request.json` retains the prompt. Create a new case when changing the frame, prompt or selection box instead of editing bound inputs. No GPU is needed, but perform substantial video decoding on permitted compute resources rather than login nodes.

## 2. GPU: Choose Interactive or Batch Execution

### Interactive

On the login node, request a two-hour A40 allocation and automatically enter the compute node:

```bash
bash scripts/sam3d_objects/gpu.sh
```

Override the duration with `bash scripts/sam3d_objects/gpu.sh --time=01:00:00`. The script rejects nested Slurm allocations. In the new compute-node shell:

```bash
cd /your/actual/path/agentic-real2sim
source scripts/sam3d_objects/paths.sh
export CASE="$SAM3D_PROJECT_ROOT/outputs/sam3d-cases/office48-cabinet-f000-v001"
```

For direct low-level `infer.py` calls, use `source scripts/sam3d_objects/env.sh`. The `run.sh generate` command below activates that environment automatically; other stages use their own Python executables.

### Batch: Recommended for Jobs That Must Survive SSH Disconnection

On the login node, source `paths.sh`, set an absolute `CASE` path and submit a stage:

```bash
sbatch scripts/slurm/sam3d_workflow.sbatch segment --case "$CASE"
```

No prior `gpu.sh` or `salloc` is needed. After review, submit `generate` through the same entry point. Each job independently requests one A40 for two hours by default. Stages are not automatically connected across human review. Concurrent writers to the same case are rejected; also run only one GPU task in each allocation. Put Slurm account, partition or time overrides before the script filename.

## 3. SAM3 Segmentation and Human Review

On an interactive GPU node:

```bash
bash scripts/sam3d_objects/run.sh segment --case "$CASE"
bash scripts/sam3d_objects/run.sh status --case "$CASE"
```

Candidates and logs are saved under:

```text
CASE/stages/segment-TIMESTAMP-SUFFIX/
  console.log
  segmentation_receipt.json
  results/manifest.json
  results/office48-wall-cabinet/text_0_overlay.jpg
  results/office48-wall-cabinet/text_0_cutout.png
  results/office48-wall-cabinet/text_0_mask.png
  ...other candidates
```

Text and box prompts produce separate candidate sets; the automatic recommendation is only a suggestion. Inspect the full source image, overlays, cutouts and binary masks. Confirm the entire visible target is selected, background is excluded and no major regions are missing. Do not accept a mask solely by its score.

Bundle the current candidates for download:

```bash
bash scripts/sam3d_objects/run.sh bundle --case "$CASE" --kind review \
  --out "$SAM3D_PROJECT_ROOT/outputs/office48-cabinet-mask-review-001.tar.gz"
```

From a local terminal, use `scp dingxuan@greatlakes.arc-ts.umich.edu:/actual/remote/path/review.tar.gz outputs/`, then `tar -xzf outputs/review.tar.gz -C outputs/`. Keep the original remote case in place. Release an interactive GPU while reviewing locally if it is no longer needed; generation can be submitted separately afterward.

## 4. CPU: Record the Selected Candidate

Run only after inspecting the actual images. This example records selection of `text_0`:

```bash
bash scripts/sam3d_objects/run.sh review-mask --case "$CASE" \
  --variant text_0 --reviewed --reviewer dingxuan \
  --note "Inspected overlay and cutout: complete visible cabinet, background excluded."
```

Each review creates a separate `review-mask-*` directory containing `mask.png`, source metadata in `source.json` and a hash-bound `review.json`. Original SAM3 candidates are unchanged. The latest segmentation is reviewed by default; to select an earlier round, add `--segmentation "$CASE/stages/specific-segment-directory"`.

Generation refuses missing review records, changed source images, modified candidate artifacts or changed selected masks. These are input-consistency checks, not automatic visual quality scores.

## 5. Validate Inputs and Generate the GLB

Validate without loading weights:

```bash
bash scripts/sam3d_objects/run.sh generate --case "$CASE" --validate-only
```

After inspecting the validation overlay, run on an interactive GPU node:

```bash
bash scripts/sam3d_objects/run.sh generate --case "$CASE" --seed 42 --save-splat
```

Or submit from the login node:

```bash
sbatch scripts/slurm/sam3d_workflow.sbatch generate \
  --case "$CASE" --seed 42 --save-splat
```

Output timestamps are assigned automatically. Each generation has its own directory, logs and complete inference-wrapper report:

```text
CASE/stages/generate-TIMESTAMP-SUFFIX/
  console.log
  command.json
  stage.json
  results/object.glb
  results/pose.json
  results/report.json
  results/inputs/...
```

For repeated performance experiments, run generate multiple times on the same reviewed case with fixed seed and export settings. Every call starts the model afresh; no persistent worker or result-cache substitution is implemented. `stage.json.wall_seconds` measures the control stage, while `results/report.json` measures inference-wrapper phases. Their boundaries differ, and both exclude Slurm queue time.

## 6. Blender Review and Result Preservation

Download the GLB. Inspect its front, sides, back and materials in an empty Blender scene, save and reopen it, then record your observations:

```bash
bash scripts/sam3d_objects/run.sh review-result --case "$CASE" \
  --reviewed --reviewer dingxuan --verdict usable \
  --note "Inspected geometry/materials and reopened the saved Blender scene."
```

Use `--verdict reject` and describe the problems for an unsuitable asset. The review covers only the generated asset, not scale alignment, object contact or scene reconstruction acceptance. Keep screenshots or saved Blender files in the local experiment directory as additional evidence.

Bundle the latest generation, matching reviewed mask, inputs, configuration and logs:

```bash
bash scripts/sam3d_objects/run.sh bundle --case "$CASE" --kind result \
  --out "$SAM3D_PROJECT_ROOT/outputs/office48-cabinet-result-001.tar.gz"
```

Bundle paths must be outside the case and cannot overwrite an existing archive. Bundles support backup and review; records retain original remote absolute paths and are not claimed to resume directly on another machine after extraction. Download to the local gitignored `outputs/` directory. Commit code, protocols and small experiment summaries, not large generated assets.

## Import a Generated Asset into an Existing Room

The shared entry point is `bash scripts/sam3d_objects/run.sh COMMAND ...`, or
`python3 scripts/sam3d_objects/workflow.py COMMAND ...`. Each invocation runs one
stage. Human mask review and placement/asset inspection remain explicit steps;
there is no unattended all-in-one command. The Shell wrapper activates the model
environment for `generate`; direct Python invocation requires a configured runtime.
`import-scene` uses Blender and does not activate SAM 3D or require a GPU allocation.

For a full workflow case, import its latest successful generation:

```bash
bash scripts/sam3d_objects/run.sh import-scene \
  --case "$CASE" \
  --scene /absolute/path/room.blend \
  --placement /absolute/path/placement.json \
  --object-id furniture/sam3d-cabinet \
  --blender /absolute/path/blender
```

The scene ID may differ from the segmentation ID. Use `--replace` only for an
existing static semantic target. Placement follows the contract documented in
[the import guide](README.md#import-an-existing-glb-into-an-aha-3d-scene).
The source room is preserved. Each invocation creates a new `import-scene-*`
stage containing copied GLB/placement inputs, command, logs, snapshots, an import
receipt and `results/scene.blend`, `results/import_report.json`, and
`results/semantics.json`. Inspect the scene separately; `review-result` still
reviews only the generated asset, not room alignment.

The controller accepts Linux paths. When the Blender executable ends in `.exe`,
it converts file arguments using `wslpath -w` automatically. Choose Blender with
`--blender`, an **exported** `BLENDER_BIN`, or an executable named `blender` on PATH.
Do not preconvert the controller's arguments to Windows paths.

### Existing GLB / local import-only case

For existing manual results or a GLB downloaded from Great Lakes, use a separate
new case with `--glb`; this does not claim model inference was run by the workflow:

```bash
python3 scripts/sam3d_objects/workflow.py import-scene \
  --case outputs/sam3d-cases/cabinet-local-import \
  --glb outputs/sam3d-objects/office48-cabinet-20261109-215313/object.glb \
  --scene outputs/office48-baseline-001/blender/furnished-v006/room.blend \
  --placement configs/sam3d_placement.example.json \
  --object-id furniture/sam3d-cabinet-test \
  --blender '/mnt/e/Blender Foundation/Blender 5.2/blender.exe'
```

The example uses identity placement only. Supply your experiment's placement JSON
for actual alignment. The new case directory is created automatically; do not
point it at an old manual experiment directory without `case.json`. Repeat the
command with the same case and `--glb` to create another import revision.
Import-only cases support `import-scene`, `status`, and `bundle --kind result`.
They cannot resume segmentation or generation; prepare a separate full case for
those stages. This route avoids rewriting historical remote absolute paths.
The controller does not submit SSH commands or transfer files between machines.

```bash
python3 scripts/sam3d_objects/workflow.py status --case "$CASE"
python3 scripts/sam3d_objects/workflow.py bundle --case "$CASE" --kind result \
  --out /absolute/path/new-scene-result.tar.gz
```

Result bundles include the latest successful scene import when present, with
hash checks on the scene, GLB, placement, semantics and report. A new successful
model generation clears the current scene-import pointer; previous stages remain
on disk. Failed imports retain their logs and do not replace the last successful
selection. Editing a saved scene in place invalidates its bundle receipt; preserve
manual revisions separately. Source scenes and external texture dependencies are
not copied into the bundle, so it is not guaranteed to be portable/self-contained.

## Optional: Generate a New Pi3X Room Reference

Skip this section when reusing the Office48 reference. For a new video, on a GPU node:

```bash
bash scripts/sam3d_objects/run.sh reference --case "$CASE" --num-frames 32
```

Or submit:

```bash
sbatch scripts/slurm/sam3d_workflow.sbatch reference --case "$CASE" --num-frames 32
```

This calls the existing `build_reference` route with Pi3X, SAM3 semantic segmentation and Open3D. It produces approximate geometry, cameras and source-view overlays, not a final editable room or a reviewed object-instance mask. Room references and individual-object segmentation serve different purposes. Inspect the reference before deciding how to align coordinates and scale.

## Failures, Disconnections and Retries

- Inspect state with `bash scripts/sam3d_objects/run.sh status --case "$CASE"`.
- Python/subprocess failures retain `stage.json`, `error.txt` and any console.log. Failed outputs are not selected.
- Retrying a stage creates a new directory and preserves prior failures. Use a new case after failed preparation.
- Slurm timeout/OOM termination may leave a `running` record. Check `squeue`/`sacct` to confirm the old process has ended before retrying. Kernel locks are released when processes exit; do not manually delete lock files.
- Successful `sbatch` return means submission only. Check job ExitCode, case state and model reports.
- In a new shell, source `paths.sh` and set CASE again rather than relying on the previous shell's variables.
- `infer.py` remains the inference entry point; the earlier standalone commands and `sam3d_objects.sbatch` are still available.

Local tests use stand-in decoders and models rather than real video decoding or GPU inference. The new staged workflow still needs an end-to-end Great Lakes validation run. Preserve existing manual results as historical evidence without rerunning them solely to populate the workflow.
