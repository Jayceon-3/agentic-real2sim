# SAM 3D Objects: Three-request model reuse pilot

Question: how much total wall time does one process with one model instance save
over three serial fresh processes? Do later requests change outputs or retain
additional allocated GPU memory?

## Protocol

| Setting | A: `fresh` | B: `reuse` |
| --- | --- | --- |
| Requests | 3 | 3 |
| Processes | 3, serial | 1 |
| Runtime imports / model initializations | 3 / 3 | 1 / 1 |
| Input | The same cabinet RGB/mask for every request | Identical |
| Seed | 42 for every request | Identical |
| Storage/environment/export settings | Existing paths and request export setting | Identical |

The controller forces seed 42 and inherits `save_splat` from the old request.
Use the reviewed cabinet request below, which enables splat export. Inspect the
new resolved `request.json` to confirm. No storage staging, cache clearing,
`empty_cache()`, step changes or precision changes are performed. Both groups
use the same worker and wrapper code, preparation, export, garbage collection
and synchronization. A worker for A processes one request and exits; B processes
all three while retaining only the session model/runtime between requests.

This is a feasibility pilot, not a statistically robust benchmark. A runs first
by default, so B can benefit from file/JIT caches populated by A. Fresh processes
are not cold-cache runs. Use a separate BA run to check order sensitivity before
making a speedup claim. Three requests cannot establish long-term memory stability.

## Submit on Great Lakes

First transfer the changed repository files to the existing Great Lakes checkout
using your normal code synchronization method. In particular, transfer
`scripts/sam3d_objects/infer.py` and this entire experiment directory. The existing
`experiments/sam3d-startup-profile/` helpers are required. Nothing installs packages
or downloads weights. Do not change environments, source or weights during a run.

In Bash on the login node, from the project root:

```bash
source scripts/sam3d_objects/paths.sh
export REUSE_OUT="$SAM3D_PROJECT_ROOT/outputs/sam3d-model-reuse/cabinet-3req-ab-001"

test -f "$MODEL_CONFIG"
test -f "$SAM3D_SRC/notebook/inference.py"
test -x "$SAM3D_ENV/bin/python"
test ! -e "$REUSE_OUT"

sbatch experiments/sam3d-model-reuse/run.sbatch \
  --request "$SAM3D_PROJECT_ROOT/outputs/sam3d-objects/office48-cabinet-20261109-215313/request.json" \
  --image "$SAM3D_PROJECT_ROOT/data/local/sam3d-objects/office48-wall-cabinet-f000-v001/image.png" \
  --mask "$SAM3D_PROJECT_ROOT/data/local/sam3d-objects/office48-wall-cabinet-f000-v001/mask.png" \
  --input-metadata "$SAM3D_PROJECT_ROOT/data/local/sam3d-objects/office48-wall-cabinet-f000-v001/source.json" \
  --upstream "$SAM3D_SRC" --checkpoint "$MODEL_CONFIG" \
  --cuda-home "$SAM3D_CUDA_HOME" \
  --requests 3 --order AB --timeout 0 --out "$REUSE_OUT"
```

These paths match the earlier cabinet experiment; verify they exist in your
checkout. Path overrides prevent dependence on old machine-specific paths in
the saved request. Run output directories must be new. Input/code hashes and
checkpoint size/mtime inventories are checked before and after each worker.
Weights are not fully hashed, and this is not proof of weight-byte immutability.

Default allocation: one A40, four CPU cores, 32 GB host RAM, seven hours.
The internal timeout is disabled by default (`--timeout 0`); Slurm still enforces
the overall job time limit. Earlier pilots exceeded 30- and 60-minute worker
deadlines during model initialization, so this pilot no longer assumes startup
fits those budgets. A positive `--timeout N` enables an N-second deadline for
each A worker and a 3 x N-second deadline for the entire B worker, not a separate
enforced timeout for each B request. The chosen policy is printed in the log and
recorded in `experiment.json`. No automatic retry is performed.
One failed worker aborts the pilot. Partial logs/reports are retained.

After transferring this update, check `python run.py --help` using the full script
path to confirm that zero is accepted before submitting. Keep previous failed
output directories and use a new output path; failed initialization cannot be
resumed by a new process. Increasing only the Slurm time limit does not change
an explicitly supplied positive internal timeout.

For a later reverse-order check, repeat the command with `--order BA` and a new
output path such as `cabinet-3req-ba-001`. Submit it after reviewing the pilot;
do not run both groups concurrently on one GPU.

Within an existing GPU allocation, source `scripts/sam3d_objects/env.sh` and use
`python -u experiments/sam3d-model-reuse/run.py` with the same arguments instead
of `sbatch .../run.sbatch`. Do not run inference on the login node.

## Watch progress

```bash
squeue -u "$USER"
tail -n 40 slurm-sam3d-reuse-JOBID.out
tail -n 40 "$REUSE_OUT/fresh/process-001.log"
sacct -j JOBID --format=JobID,State,ExitCode,Elapsed,MaxRSS
```

The controller prints each process start/end. B's `reuse/process-001.log` prints
each request completion and PID. Inspect `experiment.json` and Slurm status;
submission success alone does not prove experiment success. A hard scheduler kill
can prevent final summaries; raw logs and per-request reports remain evidence.

## Artifacts and interpretation

```text
cabinet-3req-ab-001/
  request.json                    # Resolved fixed request
  experiment.json                 # Identity, paths, commands, process wall times
  resources.jsonl                 # Continuous process-group and GPU samples
  summary.json
  infer_snapshot.py
  runner_snapshot.py
  monitor_snapshot.py
  fresh/
    process-001.log ... process-003.log
    process-001-time.txt ...       # GNU time, if installed
    process-001/
      worker.json                 # PID, request wall, memory after cleanup
      request-001/                # Standard infer.py outputs and events
    process-002/request-001/
    process-003/request-001/
  reuse/
    process-001.log
    process-001-time.txt
    process-001/
      worker.json
      request-001/
      request-002/
      request-003/
```

Read the summary:

```bash
python3 -m json.tool "$REUSE_OUT/summary.json"
```

Check these in order:

1. `status` is `completed`, both groups have `completed_requests: 3`, and the
   worker PID is the same across B's three requests. A has three distinct worker
   launches (PIDs can theoretically be reused).
2. `reused` is `[false, false, false]` for A and `[false, true, true]` for B.
3. `active_process_wall_seconds` sums actual external worker lifetimes, including
   Python startup/shutdown. It excludes controller baseline, identity checks and
   the 10-second inter-group gap. There are no deliberate inter-request gaps.
   `speedup` is A's total divided by B's total, for the same three outputs.
4. `first_object_wall_seconds` includes worker startup through first completed
   request cleanup (Unix clock based). The top-level
   `reuse_first_request_seconds` is narrower: worker-internal request processing
   and cleanup, excluding interpreter startup. Later-request median has only
   two observations. Also inspect the individual values.
5. Reused `runtime_import` and `model_init` values describe the reuse path,
   not repeated import/load measurements. The per-request `session` field points
   to the original output directory holding the adapted runtime and patch receipt.
6. `torch_allocated_after_cleanup_bytes` should be inspected across B requests.
   A rise followed by a plateau may be lazy initialization. A steady rise needs
   a longer run to investigate. Reserved memory includes allocator caching;
   neither this nor three stable samples proves absence of a leak. Torch metrics
   exclude external allocators; also inspect sampled GPU memory in telemetry.
7. `all_artifact_hashes_equal` includes GLB, pose and optional splat. Equality is
   strong evidence of identical saved artifacts for this input. Inequality is
   not automatically state pollution: compare A repeats, geometry and fixed-view
   renders before attributing it to reuse. No automatic geometric equivalence
   or visual-quality score is claimed.

The monitor is best-effort. Inspect its device/process errors and actual GPU
samples; `status: completed` alone does not establish valid GPU telemetry.
Stage memory peaks include resident weights and are not additive. Historical
five-run startup summaries are context, not the A group of this experiment.

If the pilot passes, run BA next, then test mixed inputs and a longer request
sequence. Preserve the pilot as recorded; do not overwrite or silently replace it.

## Local checks

```bash
python3 -m unittest discover -s scripts/tests -p test_sam3d_objects.py -v
python3 -m unittest discover -s experiments/sam3d-model-reuse/tests -v
bash -n experiments/sam3d-model-reuse/run.sbatch
```

CPU fake-runtime tests verify reuse, result release and reporting. They do not
validate CUDA behavior, real output equivalence, memory stability or speedup.
