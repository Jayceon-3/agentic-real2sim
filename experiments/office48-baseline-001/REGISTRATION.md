# Reconstruction registration and reference import

Status: scope registered; diagnostic reference import verified in Blender.
No room has been authored and no final reconstruction has been accepted.

## Scope and ownership

- Scene/task: `office48-baseline-001`.
- Owner: `codex-office48-20261104`.
- Portable acceptance declaration: `configs/office48_acceptance_scope_v1.json`.
- Portable authoring request: `configs/office48_scene_request_v1.json`.
- Runtime scene: `third_party/aha-3d/scenes/office48-baseline-001/`.
- Runtime acceptance: `third_party/aha-3d/deliveries/office48-baseline-001/acceptance/office48-baseline-001/`.
- Intake resolved all required choices; status `ready_for_authoring`.
- Acceptance status remains `awaiting_review`; no candidate or delivery selected.

Upstream claims cover its scene, delivery and run directories. The upstream claim
tool rejects paths outside its root, so the parent project's script paths,
experiment records and `outputs/office48-baseline-001/` are documented as this same
owner's external paths in its handoff and local ownership record. No parallel
writer is assigned. Keep scope/claims for the full reconstruction; this stage's
completion is not reconstruction completion. Scene pointers and receipt hashes
are machine-local; initialize equivalent scope when moving to a new checkout.

## Scripts and executed checks

`scripts/prepare_office48_import.py` validates the initial lock and uses upstream
`workflow.camera.interpolate` and `workflow.preflight.camera_report` to create
303 camera samples. It uses PCHIP translation, SLERP rotation and linear
intrinsics, without extrapolation. Source integer-index principal points are
converted to image-boundary coordinates before scaling 672 x 378 to 1280 x 720.
Native keyframes are checked against source poses, allowing SLERP's normalization
of near-orthogonal rotations via an independent SVD comparison.

`scripts/blender_import_office48.py` runs only in background Blender and starts
from factory-empty settings. It reuses upstream triangle/color helpers and
`ensemble.bake_camera` / `ensemble.camera_check`. Display vertices and camera poses
are already aligned; their world transform is not applied again. It saves a new
scene, reopens it, checks all camera frames and optionally renders three views.

Actual tested setup: Windows Blender 5.2.1 LTS, build `9e2066aef7ef`, launched
through WSL. Exact executable location is in ignored local configuration.

| Check | Actual result |
| --- | --- |
| Input lock | All 16 files matched; pinned upstream tracked files clean |
| Native camera observations | 32 keys checked; raw pose normalization difference at most 1.78e-6 |
| Interpolated timeline | 303 frames, 30 fps, source frame + 1, no held/extrapolated samples |
| CPU intrinsics representability | Maximum K-element difference 1.07982 px; upstream tolerance 2 px |
| Evaluated Blender camera after save/reopen | All 303 frames; max c2w element error 4.91e-7, max K-element difference 1.07984 px |
| Reference mesh imported | 71,520 vertices, 133,597 triangles |
| CPU diagnostic renders | Source frames 0, 146, 302, each 640 x 360 |

The first development preflight rejected raw native rotation agreement at 1e-7:
the supplied matrices had orthogonality error 3.82e-6 and SLERP normalized them.
The check was corrected to compare normalized rotations independently using SVD;
translation and intrinsics checks remain strict. No source cameras were rewritten.

The default scene shows only the TSDF structural core, an explicitly labeled
diagnostic display. Full context remains in the locked NPZ; `--include-context`
adds its eligible triangles and uncertain layers. That optional import route has
not been executed in this initial test. Black/transparent holes around glazing,
people exclusions and depth boundaries are missing reference support, not walls.
Fallback point-only context is retained in the NPZ and not instantiated as meshes.

The agent inspected all three diagnostic images: room edges, ceiling and desk
follow the corresponding source views at a coarse level, with visibly incomplete
glazing, furniture and lights. This is useful reference setup evidence, not
independent accuracy, floor/scale acceptance or final authored-room review.

## Local artifacts

All paths below are relative to the project root:

```text
outputs/office48-baseline-001/inputs/camera-v001/
  camera.npz
  camera_preflight.json
  import_plan.json
outputs/office48-baseline-001/blender/reference-v001/
  reference_setup.blend
  import_report.json
  reference_source_000000.png
  reference_source_000146.png
  reference_source_000302.png
  source_views/                 Five exact cached source PNGs, 672 x 378
outputs/office48-baseline-001/logs/import-v001.log
```

The saved reference collection is visible in the viewport, unselectable, and
hidden from delivery rendering. `AUTHORED_ROOM - empty` is intentionally empty.
Switch reference visibility deliberately for diagnostics; do not render reference
geometry and label it as the authored room. Diagnostic render settings use CPU
Cycles with emission source colors; they are not final material/lighting settings.

## Repeat the import

Run preparation from the project root with a NumPy/SciPy Python environment:

```bash
python3 scripts/prepare_office48_import.py \
  --out outputs/office48-baseline-001/inputs/camera-v002
```

On Linux, use a compatible Blender binary with the script path directly. On WSL
with Windows Blender, set `BLENDER_BIN` to its mounted executable path and convert
the script filename for Windows. For example, after setting that environment var:

```bash
"$BLENDER_BIN" --background --factory-startup --python-exit-code 1 \
  --python "$(wslpath -w "$PWD/scripts/blender_import_office48.py")" -- \
  --prepared outputs/office48-baseline-001/inputs/camera-v002 \
  --out outputs/office48-baseline-001/blender/reference-v002 \
  --render-checks
```

Use new revision paths; existing outputs are refused. These imports do not require
Pi3X/SAM3 models or GPU inference.

## Next work

Open the new reference setup, inspect plan/side views and source landmarks to
review floor/upright, then save a distinct architecture blockout revision. Build
floor, walls, pitched ceiling, beams, doors and windows in `AUTHORED_ROOM` using
RoomKit semantic roots. Review native source cameras before adding furniture.
Do not reuse the supplied authored office. Preserve the locked references and
record findings and assumptions before changing geometry or camera basis.
