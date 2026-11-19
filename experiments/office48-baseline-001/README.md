# Office48 baseline 001

Status: an independent furnished room candidate has been authored; refinement and final acceptance remain pending. Created 2026-11-04
(America/New_York). This record does not claim reconstruction acceptance.

## Fixed experiment

- Specification: [configuration](../../configs/office48_static_baseline_v1.json).
- Agent task instructions: [prompt v1](../../prompts/office48_static_baseline_v1.md).
- Input/code identities: [lock](inputs.lock.json).
- Runtime evidence and limitations: [preparation](PREPARATION.md).
- Human interventions and preparation history: [events](events.jsonl).
- Current scope, executed Blender import checks and continuation: [registration](REGISTRATION.md).
- Authoring decisions, repairs and current artifacts: [building](BUILDING.md).
- User-requested review copy before fidelity repairs: [pre-delivery](PREDELIVERY.md).
- Baseline project HEAD: `25380c79d60cefc38e1f647dca640fba58a76f4e`.
- AHa-3D: `82f4b1110cfe4b55fff19df3b3790852ce07b171`.

The project HEAD identifies the checkout before these experiment files were added.
README.md already had an uncommitted edit and the proposal PDF was untracked;
neither was changed by this preparation. The new protocol is a working-tree
snapshot until committed. Do not describe it as an already committed experiment.

## Input acquisition and timing

Official source: https://raw.githubusercontent.com/KevinXu02/aha-3d/main/references/office48/source.mp4

The URL follows a mutable upstream branch; the lock fixes the downloaded bytes.
The video was downloaded by the human and copied from Great Lakes. It contains
303 frames at 30 fps, 1280 x 720. Clip duration is 10.1 seconds; the last frame
starts at 10.0666667 seconds. Pi3X used 32 native frames, including both endpoints,
resized to 672 x 378 without cropping. Exact indices and timestamps are locked.
Source usage/distribution terms have not been independently established here;
retain attribution and confirm applicable terms before redistributing footage.

## Workspace and continuation

Large local artifacts live in ignored `outputs/office48-baseline-001/`:

```text
inputs/       Small metadata snapshots and a portable path index; large inputs stay in place
scripts/      Reserved for generated run-local scripts (reusable code belongs in scripts/)
blender/      New versioned scenes; initially empty
renders/      Versioned test and final renders; initially empty
evidence/     New review/check artifacts; initially empty
logs/         Execution logs; initially empty
```

Validate the locked inputs from the project root:

```bash
python3 scripts/check_office48_inputs.py
```

The upstream reconstruction claim and acceptance scope are initialized. A new
room with architecture, major furnishings and source cameras has been authored
in background Blender; see [building](BUILDING.md) for the exact working revision.
The reference setup and initial candidate are not accepted final deliveries.

Append findings, repairs, human feedback, exact evidence paths and stage outcomes
as work proceeds. Save changed inputs or protocol versions as a new version/run;
do not silently overwrite this initial lock. Keep runtime-specific paths in
ignored local configuration. No credentials or model weights belong in Git.
