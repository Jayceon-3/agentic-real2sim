# Office48 static baseline instructions, version 1

Reconstruct the indoor room in the locked office48 RGB video using the pinned
AHa-3D workflow. Use `configs/office48_static_baseline_v1.json` and verify
`experiments/office48-baseline-001/inputs.lock.json` before consuming inputs.
These are project experiment files, not executable AHa-3D recipes.

## Scope

- Author a new editable Blender room from an empty scene. Exclude source people.
- Match visible architecture, openings, ceiling beams, major furniture, orientation,
  proportions and spatial relationships. After whitebox review, match visible
  materials and finishes; whitebox is an intermediate result.
- Preserve the full source timeline: 303 frames at 30 fps, 1280 x 720 final output.
  Native source indices are zero-based; Blender frame = source frame + 1.
- Use the locked, structurally aligned cameras and geometry in one common world
  basis. There are 32 estimated cameras, not a measured full-rate camera track.
  Document any camera interpolation, intrinsics rescaling and coordinate conversion.
- Scale is uncalibrated predicted metres. Do not claim measured physical accuracy.
- Furniture and architecture remain static. Camera animation is permitted and
  required for source-view video comparison. No human reconstruction or generated
  motion is requested.

## Authoring and verification

Follow the pinned upstream AGENTS.md and stage-specific instructions when actual
reconstruction begins, including scene claims and acceptance intake. This initial
experiment workspace is preparation, not an upstream acceptance receipt.

The agent selects tools, measures source-supported reference surfaces, searches
the existing asset library, writes and executes Blender scripts, inspects actual
images and repairs findings. The human provides goals, infrastructure access and
feedback. Record every substantive human correction or manual geometry change.

Use existing AHa-3D geometry, RoomKit, asset and inspection tools. Record any
required compatibility patch. Do not introduce alternative reconstruction models
or new tool-selection policies in this baseline.

Keep original input files and upstream examples unchanged. Do not load, append,
copy, or derive authored geometry/cameras from `examples/office48/whitebox.blend`.
That example was already viewed for installation verification; record this prior
exposure. Scene dimensions and placement must be supported by source/reference
evidence, not copied from the example. Reference geometry is a guide, not the
authored room or the final static asset.

Start with room structure and source cameras. Review matched early/middle/late
views before adding furniture detail and materials. Inspect plan/front/side views
and isolated object views where useful. Record exact source frame IDs and evidence
paths; distinguish automatic validation from agent visual review. Retain failed
attempts and unresolved findings. Use new output paths for revisions.

Do not treat reference self-consistency, a successful command, or an output file's
existence as proof of reconstruction quality. Keep source fidelity, structural
alignment, support/collision checks and render completeness separate.

## Delivery and experiment accounting

Deliver a new editable `.blend`, full-length rendered video, five matched
source-view comparisons, layout/support checks, and a repair ledger. Use native
source IDs 0, 78, 146, 224 and 302 for the fixed comparison set. Compare source RGB
and rendered geometry; reference overlays alone are insufficient.

Store scripts/configuration and small experiment records in Git; large generated
artifacts go under `outputs/office48-baseline-001/`. Record agent model and settings
when known, prompt identity, code changes, runtime, peak memory where available,
token/cost data when available, manual interventions and remaining errors. Use
null/unknown for unavailable measurements. Report reference preparation and new
scene authoring costs separately. Bind final acceptance to the exact saved revision.
