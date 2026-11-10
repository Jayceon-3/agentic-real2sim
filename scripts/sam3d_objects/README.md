# SAM 3D Objects wrapper

This wraps the inference route exercised in the Great Lakes official-input smoke
test: upstream commit `f91db411c50efee93d8db7aeb323885650f6f722`, Python 3.11,
Torch 2.5.1+cu121, one A40, cluster CUDA module `cuda/12.1.1`, and locally built
Kaolin 0.17.0. That smoke test predates this wrapper; this wrapper still needs its
own real GPU validation. No weights, accounts or environments are installed by it.

The upstream [entry point](https://github.com/facebookresearch/sam-3d-objects/blob/f91db411c50efee93d8db7aeb323885650f6f722/notebook/inference.py)
overwrites `CUDA_HOME` with `CONDA_PREFIX`. The wrapper replaces exactly that line
in a saved, run-local copy before importing it, and sets `LIDRA_SKIP_INIT=true`.
It records both hashes and the substitution and never edits the external checkout.
Unknown entry-point layouts fail explicitly. Conda's CUDA toolkit crashed on the
recorded machine; the cluster CUDA toolkit passed a minimal compilation test.

## Inputs

- `--image`: source RGB image. The original bytes are retained; inference uses RGB.
- `--mask`: same-size, single-channel mask. Foreground is `value > --mask-threshold`
  (default 0, compatible with 0/1 or 0/255 masks). RGB overlays are rejected.
  No crop, resizing, EXIF rotation, inpainting or automatic instance selection occurs.
- `--checkpoint`: a `pipeline.yaml` file or directory containing it, with its model
  files in the downloaded layout. This is not a single `.safetensors` path.
- `--upstream`: external SAM 3D Objects source checkout.
- `--out`: a new directory. Existing directories, including failed runs, are refused.
- `--seed`: default 42. This records the seed passed to the model; it does not
  promise bitwise determinism for all GPU kernels.
- `--input-metadata`: optional JSON recording video, frame, timestamp, object ID,
  mask generation/review and any frame preparation. It is retained as supplied
  metadata, not independently validated source evidence.
- `--checkpoint-revision`: optional downloaded HF revision. This is explicitly a
  user assertion, not a cryptographic binding of every weight file.
- `--save-splat`: additionally save the Gaussian PLY. GLB is always required.

Paths are resolved relative to the invoking shell's working directory. Use absolute
paths for remote/batch runs. Credentials belong in the existing HF authentication
store, never CLI flags, input metadata or logs.

## First run: repeat the official example with the wrapper

After syncing this project to Great Lakes, in its checkout:

```bash
export SAM3D_PROJECT_ROOT="$PWD"
export SAM3D_WORK="$(cd ~/eecs442_scratch/sam3d-objects && pwd -P)"
export SAM3D_SRC="$SAM3D_WORK/src/sam-3d-objects"
export EXAMPLE_INPUT="$SAM3D_SRC/notebook/images/shutterstock_stylish_kidsroom_1640806567"
export MODEL_CONFIG="$SAM3D_WORK/checkpoints/hf-download/checkpoints/pipeline.yaml"
```

For a cheap input/provenance check, use the dedicated environment's Python. Choose
a new directory for the subsequent GPU run; validation directories are immutable too.

```bash
"$SAM3D_WORK/envs/sam3d-objects/bin/python" scripts/sam3d_objects/infer.py \
  --upstream "$SAM3D_SRC" --checkpoint "$MODEL_CONFIG" \
  --image "$EXAMPLE_INPUT/image.png" --mask "$EXAMPLE_INPUT/14.png" \
  --object-id official-toy --seed 42 \
  --out "$SAM3D_PROJECT_ROOT/outputs/sam3d-objects/official-validate-001" \
  --validate-only
```

`validated_only` means paths, input dimensions/mask and provenance preparation
passed. It does not check weight loadability, CUDA, segmentation identity or quality.
Inspect the saved overlay yourself.

Submit from a persistent directory. Slurm writes `slurm-sam3d-JOBID.out` there;
the directory must exist before submission. The runtime variables above are
inherited by the batch job via the normal `sbatch` environment export.

```bash
sbatch scripts/slurm/sam3d_objects.sbatch \
  --checkpoint "$MODEL_CONFIG" \
  --image "$EXAMPLE_INPUT/image.png" --mask "$EXAMPLE_INPUT/14.png" \
  --object-id official-toy --seed 42 --save-splat \
  --checkpoint-revision "$(cat "$SAM3D_WORK/logs/checkpoint_revision.txt")" \
  --out "$SAM3D_PROJECT_ROOT/outputs/sam3d-objects/official-gpu-001"
```

Replace the image/mask/object ID with one reviewed Office48 furniture instance for
the next experiment. Do not regenerate Pi3X references or render the whole room.

The batch defaults are `eecs442f26_class`, `spgpu`, one A40, four CPU cores, 32 GB
host RAM and two hours. Override Slurm options **before** the script filename, e.g.
`sbatch --time=01:00:00 scripts/slurm/sam3d_objects.sbatch ...`. Environment overrides
are `SAM3D_ENV`, `SAM3D_SRC`, `SAM3D_CONDA_MODULE`, `SAM3D_CUDA_MODULE` and
`SAM3D_CUDA_HOME`. These are machine configuration; do not commit personal paths.
The launcher uses `srun` and propagates the Python exit status. Disconnecting SSH
after successful `sbatch` submission does not stop the batch job.

```bash
squeue -u "$USER"
sacct -j JOBID --format=JobID,State,ExitCode,Elapsed,MaxRSS
tail -n 80 slurm-sam3d-JOBID.out
cat outputs/sam3d-objects/official-gpu-001/report.json
```

For direct execution within an existing GPU allocation, activate the dedicated
environment, load the validated toolkit **after** activation and run:

```bash
module load cuda/12.1.1
export CUDA_HOME=/sw/pkgs/arc/cuda/12.1.1
export PATH="$CUDA_HOME/bin:$PATH"
unset NVCC_PREPEND_FLAGS NVCC_APPEND_FLAGS
python -u scripts/sam3d_objects/infer.py \
  --upstream "$SAM3D_SRC" --cuda-home "$CUDA_HOME" \
  --checkpoint "$MODEL_CONFIG" \
  --image "$EXAMPLE_INPUT/image.png" --mask "$EXAMPLE_INPUT/14.png" \
  --out "$SAM3D_PROJECT_ROOT/outputs/sam3d-objects/official-direct-001"
```

## Outputs and interpretation

| File | Meaning |
| --- | --- |
| `request.json` | Resolved arguments |
| `inputs/`, `inputs.json` | Original bytes, RGB/binary normalization, overlay and hashes |
| `checkpoint.json` | Config hash and weight-directory size/mtime inventory; optional claimed revision |
| `provenance.json`, `wrapper_snapshot.py`, `upstream_code/` | Code/runtime/package identities and notebook helper snapshot |
| `runtime/` | Actual adapted inference entry point and exact patch receipt |
| `object.glb` | Native exported mesh; no wrapper placement or scaling |
| `pose.json` | Native model rotation/translation/scale; not a Blender transform contract |
| `splat.ply` | Optional Gaussian splat, not a triangle mesh |
| `artifacts.json` | Output byte sizes and SHA256 |
| `report.json` | Status, stage, timing, GPU memory and explicit limitations |
| `error.txt` | Failure traceback when Python can catch the error |

Do not apply `pose.json` blindly to the GLB: audit native/exporter conventions
before aligning to AHa-3D. The wrapper does not replace furniture, import into
Blender, measure scale, run a geometric verifier or record visual acceptance.

Timing uses wall clock and CUDA synchronization around model load, inference and
export. Preparation and runtime imports are separate. End-to-end starts at wrapper
entry and includes input copying, provenance, model work, exports and artifact
hashing; it excludes Slurm queue time, shell/process startup and final report
serialization. First-use downloads/JIT compilation remain part of observed time;
this is not a warmed inference benchmark. Export timing depends on `--save-splat`.

Memory fields cover PyTorch allocated/reserved memory, not total process/device
memory (Kaolin, Warp and other allocators may be outside Torch). Stage peaks include
already resident weights and caches; they are not incremental allocations.

Python failures write `status=failed`, retain the failing stage and exit nonzero.
If Slurm kills the process for timeout/OOM, or the machine disappears, `report.json`
may remain `running`; use Slurm state/logs to identify interruption. No automatic
retry/resume, result caching or worker persistence is implemented in v1. Use a new
output directory for every retry and retain the failed one.

## Local checks

```bash
python3 -m unittest discover -s scripts/tests -v
bash -n scripts/slurm/sam3d_objects.sbatch
```

The tests use a fake runtime for control flow and output checks. They do not
validate real model quality, GPU performance, CUDA kernels or a live Slurm cluster.
