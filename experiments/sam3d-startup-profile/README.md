# SAM 3D Objects: Fresh-Process Startup Profiling

Question: are runtime import (~139 s) and model initialization (~130 s) stable
costs for the fixed Office48 cabinet request? Correlate phase timings with CPU,
GPU and I/O activity before choosing a deeper profiling or optimization experiment.
This experiment does not change model precision, inference steps, caches or inputs.

## Contents

| File | Purpose |
| --- | --- |
| `run.py` | Five serial fresh-process trials, fixed-input checks, per-trial timeout, logs and automatic summary |
| `monitor.py` | Continuous best-effort GPU and Linux process-group sampling |
| `summarize.py` | CSV/JSON/Markdown summary and optional standalone PNG figures |
| `run.sbatch` | One Great Lakes A40 allocation for all five trials |
| `tests/` | CPU-only process orchestration and telemetry tests |

The shared `scripts/sam3d_objects/infer.py` adds an opt-in `--events` flag for
`events.jsonl`. It keeps the existing timing/memory fields and inference behavior.
All five trials enable events, keeping instrumentation consistent. Event writes
add a small overhead; compare these trials with one another rather than claiming
exact equivalence with older uninstrumented runs.

## Protocol

- Reuse one reviewed RGB/mask pair, seed, checkpoint, source revision and export
  setting. The existing `request.json` supplies these settings, including
  `save_splat`. Its previous output directory is ignored.
- Run five sequential Python processes in one allocation on one GPU. This is
  not model reuse. Keep GPU workloads from overlapping within the allocation.
- Record five seconds of baseline, sample every second, and wait ten seconds
  between trials. First run is retained and reported separately; successful
  runs 002–005 get median/min/max statistics. No P95 claim from four samples.
- No cache clearing. A fresh Python process does not imply cold OS, filesystem,
  shared-storage or JIT caches. Input/code hashing and checkpoint stat operations
  also touch files before timing. This experiment measures the existing wrapper
  under that protocol, not pristine storage cold starts.
- A failed/timed-out trial is retained and the next scheduled trial runs. There
  are no automatic replacement trials. Final exit is nonzero if any trial fails.
  Fixed-input changes abort the experiment. SIGTERM/Ctrl-C terminates the active
  process group and retains partial data; hard Slurm termination may prevent final
  summaries, which can be rebuilt manually.

## Great Lakes: Submit One Batch Job

Sync this code to the existing Great Lakes checkout. No packages are installed
by these scripts. Collection uses the Python standard library, `/proc`,
`nvidia-smi`, and optionally `/usr/bin/time`. The dedicated SAM 3D environment
still supplies model dependencies. Matplotlib is only needed later for plotting.

From the project root, in Bash on the login node:

```bash
source scripts/sam3d_objects/paths.sh
export PROFILE_OUT="$SAM3D_PROJECT_ROOT/outputs/sam3d-startup-profile/cabinet-001"

sbatch experiments/sam3d-startup-profile/run.sbatch \
  --request "$SAM3D_PROJECT_ROOT/outputs/sam3d-objects/office48-cabinet-20261109-215313/request.json" \
  --image "$SAM3D_PROJECT_ROOT/data/local/sam3d-objects/office48-wall-cabinet-f000-v001/image.png" \
  --mask "$SAM3D_PROJECT_ROOT/data/local/sam3d-objects/office48-wall-cabinet-f000-v001/mask.png" \
  --input-metadata "$SAM3D_PROJECT_ROOT/data/local/sam3d-objects/office48-wall-cabinet-f000-v001/source.json" \
  --upstream "$SAM3D_SRC" --checkpoint "$MODEL_CONFIG" \
  --cuda-home "$SAM3D_CUDA_HOME" \
  --out "$PROFILE_OUT"
```

The explicit path overrides avoid relying on old absolute remote paths in the
request. Verify they name the intended cabinet inputs and reviewed mask. Relative
paths resolve against the invoking working directory, not the request's folder.
If an optional input-metadata path is supplied, it must exist.

Defaults: five trials, 1 s target sampling interval, 10 s gaps, 5 s baseline,
1800 s per-trial timeout. The example requests one hour total: five ordinary
5.4-minute runs should fit, but repeated 30-minute timeouts would not. Override
Slurm time **before** the script path when necessary. Run outputs must be new;
no overwrite or resume is performed.

```bash
squeue -u "$USER"
tail -n 60 slurm-sam3d-profile-JOBID.out
sacct -j JOBID --format=JobID,State,ExitCode,Elapsed,MaxRSS
```

Submission success alone does not mean trials completed. Check Slurm state and
`experiment.json`. The controller prints a line at each trial start/end; detailed
model logs are retained under each `run-NNN/console.log`.

Within an **existing GPU allocation**, direct execution is also supported:

```bash
source scripts/sam3d_objects/env.sh
python -u experiments/sam3d-startup-profile/run.py \
  --request /absolute/path/to/verified/request.json \
  --out "$SAM3D_PROJECT_ROOT/outputs/sam3d-startup-profile/cabinet-002"
```

Use the same path overrides if that request references another machine. Do not
start this command on a login node or run it concurrently with the batch job.

## Artifacts and Metrics

```text
cabinet-001/
  experiment.json          # Host/allocation, allowed environment fields, identities, trial status
  request.json             # Resolved fixed request
  experiment_code/         # Controller/collector/summary code snapshot
  infer_snapshot.py
  resources.jsonl          # Continuous telemetry including baseline and inter-run gaps
  run-001/ ... run-005/
    command.json
    trial.json             # Exit code, process group, external wall time, timeout/failure
    console.log
    time.txt               # GNU time -v, if available; whole command summary
    results/
      events.jsonl         # Stage start/end, PID, Unix and monotonic timestamps
      report.json          # Existing phase timings and Torch peak allocated/reserved bytes
      object.glb ...       # Normal inference outputs and provenance
  summary.csv
  summary.json
  SUMMARY.md
```

Input/config/code SHA256 and weight size/mtime inventories are checked before and
after trials. Weight bytes are not fully hashed, so this is not cryptographic
proof that all weights remained identical. Do not edit environments or weights
during the allocation. Snapshot files retain evidence; the runner uses the live
checkout and aborts if checked identities change.

Stage events cover preparation, runtime_import, model_init, inference, export and
artifact_receipt. Successful phase timings retain CUDA synchronization. A failed
phase's duration is diagnostic, not a valid latency benchmark. A killed process
may have an unmatched start event. Event boundaries include instrumentation and
need not exactly equal the inner timings in `report.json`.

`process_wall_seconds` includes process startup and GNU time overhead; wrapper
`end_to_end` has its existing narrower scope. Neither includes Slurm queue time.
The first-run and later-run summaries include only valid successful timings in
their respective comparison groups; failures remain visible in the trial table.

Sampling records:

- CPU time rate: 100% means one full CPU core, so multiple cores can exceed 100%.
- RSS: summed resident bytes in the launch process group; shared pages can count
  more than once. Processes that leave the group and short-lived processes between
  samples are not covered. PID plus start-time identity prevents PID-reuse errors.
- I/O: cumulative Linux `read_bytes`, `write_bytes`, `rchar`, `wchar` and rates for
  processes observed in both consecutive samples, plus minor/major fault rates.
  First observations have null rates, not zero. Kernel I/O counters are not a full
  measure of network/shared-filesystem traffic or throughput.
- GPU devices: UUID, utilization %, used/total MiB, power W and SM clock MHz.
  All devices visible to `nvidia-smi` are retained, along with compute-process PID,
  UUID and memory when available. `CUDA_VISIBLE_DEVICES` is recorded separately;
  use UUID/process membership to identify the allocated device. Other processes
  may affect device-level values; do not sum unrelated GPUs.
- `devices_error`, `processes_error`, `proc_errors` and `monitor_error` explicitly
  retain missing telemetry. An inference success with no GPU samples is not a
  successful GPU-monitoring experiment. Check sample counts before conclusions.

The target interval is best-effort: two GPU queries have bounded timeouts, actual
timestamps and sample duration are retained. Sampling can miss peaks and slow
queries increase spacing. The sampler does not import Torch or initialize CUDA.
Keep it enabled for all comparisons. Torch memory excludes external allocators;
reserved-minus-allocated alone does not prove leakage or fragmentation.

## Summaries and Plots

The runner automatically writes CSV, JSON and Markdown summaries. Plot after the
GPU experiment, locally or in an environment with existing Matplotlib/NumPy:

```bash
python3 experiments/sam3d-startup-profile/summarize.py \
  --root outputs/sam3d-startup-profile/cabinet-001 --plots
```

This writes `stage-times.png` and `run-NNN-resources.png` with stage-boundary lines,
CPU, RSS, I/O, GPU utilization, device memory and power panels. Missing values
are gaps, not invented zeros. Re-running summarization updates derived summaries
only. Preserve reports/events/logs as raw evidence.

If startup dominates consistently, next inspect import/initialization internals.
If the first run differs, investigate cache-sensitive behavior without assuming
the cache mechanism. Low GPU utilization with I/O or CPU activity is a lead, not
proof of a root cause. Keep deep profiler runs separate from this baseline.

## Local Validation

```bash
python3 -m unittest discover -s experiments/sam3d-startup-profile/tests -v
python3 -m unittest discover -s scripts/tests -v
bash -n experiments/sam3d-startup-profile/run.sbatch
```

Tests use stand-in inference and GPU telemetry. A real A40 experiment must run
on Great Lakes; local unit tests are not GPU performance evidence. Commit this
directory and the inference instrumentation, not the generated `outputs/` tree.
