# First independently authored room

Current working candidate: `outputs/office48-baseline-001/blender/furnished-v006/room.blend`.
This is an intermediate furnished reconstruction, not the selected final delivery.
No supplied office geometry or cameras were loaded for authoring.

## Source-based decisions

The agent inspected all five native source frames and locked reference geometry,
then plotted static, measurement-eligible points in plan/front/side and height
slices. Evidence lives under `evidence/geometry-v001/`. Height slices are manually
chosen spatial diagnostics, not independent object segmentation or hidden bounds.

`configs/office48_structure_landmarks_v1.json` records source frame/pixel selections.
`scripts/measure_office48_room.py` intersects source rays with reference-fitted wall
approximations and fits two ceiling planes to eligible static points. Its output
is `evidence/measurements-v001/measurements.json`. Glass depths were not used as
window dimensions. No known-length cue was supplied; all dimensions remain in
uncalibrated predicted metres.

| Decision | Source/reference evidence and limitation |
| --- | --- |
| Side walls and back wall | Orthogonal approximations X=-2.265, X=1.452, Y=4.24 from structural planes; small original wall slopes ignored |
| Floor | Existing Z=0 floor hypothesis; consistent with reference plan/side inspection, not measured ground truth |
| Pitched ceiling | Two robust fitted planes with median residuals about 8-9 mm against the same predictions; no independent accuracy claim |
| Windows and double door | Native 78/146 window corners and source 0 door corners projected onto wall planes; sill and trim dimensions partly regularized |
| Entry jog/return | Source 0 valid samples near pixels (520,220) and (590,220) support a return wall near Y=.78; unseen extent simplified |
| Desk | Static Z=.66-.75 plan slice shows narrow X span and long Y span; source 146 pixel (270,348) has median eligible point (-1.273,2.606,.726) in radius-3 patch |
| Guest chairs | Two curved-back seats on +X side of desk; source 224 patch (253,270) gives approximate seat point (-.299,2.177,.469); facing toward -X |
| Office chair | Source 224 patch (220,125) supports upper back near (-2.013,3.151,.946); initial placement corrected to clear wall/window trim |
| Shelf | Source 0 patches (263,142)/(263,264) support upper/base positions near (1.036,4.212,1.674)/(1.005,3.946,-.007) |
| Chandelier | Source ring centers selected at 78:(285,173), 146:(372,137); two-ray triangulation gives (-.425,2.666,2.440), ray separation about .026 |

Wall/roof rectangular completion, shell thickness, timber cross sections, hidden
furniture backs and exterior appearance remain inferred. No dimensions were
copied from the supplied whitebox.

## Authoring and repair history

1. `architecture-v001`: walls, floor, three windows, double door, pitched ceiling,
   two timber frames, ridge and trim. Source-camera renders exposed missing entry
   return and visible light reflections.
2. `architecture-v002`: added source-observed entry jog and return; removed helper
   lights from glossy/transmission/camera rays. Source-camera framing preserved.
3. A custom upholstered chair prototype was separately rendered and inspected
   before two guest chairs were created. The asset index was searched for desks,
   chairs, shelving and storage; inspected candidates did not match the narrow
   trestle desk and solid curved upholstery. Source-shaped editable parts were
   authored with RoomKit primitives and semantic roots.
4. `furnished-v001`: desk, operator chair, guest chairs, rug, cabinet, ladder shelf,
   ring chandelier, clock, calendar, entry cabinet and small props. Actual image
   review found chair/wall interference and a chandelier placed too high.
5. `furnished-v002`: corrected operator chair clearance, triangulated chandelier
   height and initial colors. A dark entry strip remained.
6. `furnished-v003`: ray inspection located coincident entry-jog and return faces;
   trimmed the return to eliminate the overlap. The corresponding dark strip
   disappeared in source 0 render.
7. `furnished-v004`: door jambs/threshold stop at floor, baseboard stops at entry
   jog, calendar clears window trim, rug no longer reaches cabinet footprint.
8. `furnished-v005`: desk and supported props raised to actual rug surface; chair
   back face winding repaired before bevel; explicit chair/door facing recorded.
9. `furnished-v006`: ceiling and gable get 8 cm exterior shells while preserving
   observed interior surfaces; thickness is an assumption, not a measurement.

Earlier outputs and failures remain. The first native review script failed on
Blender collection membership after its placement report was written; this was
fixed to test object names, and current evidence was regenerated from the current
saved scene. Development checks were never treated as acceptance.

## Checks and review evidence

- All authoring stages reopen their saved scene and recheck 303 evaluated camera
  frames using upstream camera checks; source camera cache remains unchanged.
- Five source views are actually rendered using CPU Cycles, 640 x 360, 16 samples.
- `evidence/comparisons-v006/source_vs_model.jpg`: source RGB vs authored render,
  five native times. Source RGB is resized only for sheet display.
- `evidence/comparisons-v006/object_focus.jpg`: ten isolated object/structural
  silhouettes over actual source images. They intentionally show occluded target
  surfaces and do not represent visible-only segmentation or a numerical score.
- `evidence/comparisons-v006/cutaways.jpg`: plan/front/side with explicit visibility
  changes recorded in `evidence/furnished-v006/focus_manifest.json`.
- Upstream static placement report: `evidence/furnished-v006/placement/report.json`.
  Structural frame/trim assemblies are explicitly classified as structures;
  wall fixtures and tabletop supports are declared in
  `configs/office48_placement_v1.json`. Tolerances were not relaxed. Rigid-body
  simulation is off, mounting strength is not certified, and structural-structural
  joins are outside that collision check. A clean diagnostic is not source fidelity.

These are early review images, not the canonical upstream layout acceptance
packet. No final video, complete preview acceptance, final visual acceptance or
selected delivery exists yet. Furniture finishes are initial approximations;
windows show unmodeled exterior, and shelf/calendar/detail fidelity remains open.
Collar-tie proportions and chair silhouettes need further source-specific review.

## Reproduce this stage

Use the pinned source/reference setup and a compatible Blender executable. Run
the following scripts through `--background ... --python-exit-code 1 --python ... --`
with new output paths (Windows/WSL script filenames require `wslpath -w`):

1. `build_office48_room.py --config configs/office48_room_v002.json --out NEW_ARCH`
   with `reference-v001/reference_setup.blend` open.
2. `furnish_office48_room.py --out NEW_FURNISHED` with `NEW_ARCH/room.blend` open;
   the recorded custom-chair prototype review must be available. The current
   furnisher includes entry-face and chandelier repairs from the initial attempts.
3. `repair_office48_candidate.py --out NEW_REPAIRED` with the fresh furnished
   scene open. This is a one-time repair pass, not an idempotent operation.
4. `review_office48_room.py --out NEW_REVIEW` with the repaired saved scene open.
5. `make_office48_comparisons.py --candidate NEW_REPAIRED --review NEW_REVIEW --out NEW_SHEETS`
   with local Python/Pillow.

The preparation stage must already be registered. The initial 16 input hashes
remain unchanged. During this turn an unrelated local modification appeared in
upstream `examples/office48/whitebox.blend`; it was preserved and not consumed.
Strict `check_office48_inputs.py` therefore reports the dirty upstream checkout
even though consumed input files and upstream runtime source remain unchanged.
Do not reset someone else's file or silently describe the whole checkout as clean.

Next: refine remaining visible mismatches, generate the full upstream layout
packet and preview, then render/fully decode the requested final video and bind
acceptance to that exact scene revision. Record all costs as unknown unless
actually measured; no new Great Lakes inference job was used for this stage.
