# Preliminary review package

The user explicitly requested viewing a deliverable version before continuing
source-fidelity repairs. This authorizes a preliminary package, not closure of
the original findings or a weaker final acceptance scope.

Working package: `outputs/office48-baseline-001/pre-delivery-v002/package/`.
Archive: `outputs/office48-baseline-001/pre-delivery-v002/office48_preliminary_review.zip`.
The earlier `pre-delivery-v001` directory is a 32-sample keyframe test, not the
selected review package. Version 002 uses eight samples for a fast full clip.

## Contents and boundaries

- `office48_preview.blend`: authored room and baked 303-frame camera. The hidden
  Pi3X reference collection was removed from this copy; materials are packed and
  linked-library/external-image checks passed after reopening. Original authored
  and reference scenes remain unchanged.
- `office48_preview.mp4`: full source-duration review video, 303 frames at 30 fps,
  1280 x 720, no audio. Fast material rendering uses EEVEE, raytracing off, eight
  samples and the existing exposure. This is not a source-fidelity repair.
- Five-time source/video comparison sheet, three full-resolution keyframes and
  diagnostic plan/front/side views.
- Technical validation, artifact hashes, provenance and known open findings.

The renderer and encoder are `scripts/render_office48_preview.py` and
`scripts/package_office48_preview.py`. Frames stay in the run's `work/frames/`
outside the distributable package. FFmpeg/FFprobe are existing local executables;
no shared environment was modified or installed for encoding.

The original acceptance ledger still contains `source-appearance-v006` and
`source-shape-review-v006`. There is no accepted final delivery or baseline
completion claim. The preview is a separate portable copy of furnished-v006;
its rendering can differ from the earlier CPU Cycles inspection stills.

## Validation evidence

Before the full clip, representative first/middle/last keyframes were rendered,
and the portable scene was reopened with all 303 evaluated camera poses and
intrinsics checked. The final receipt is written only after all frame PNGs are
decoded, MP4 encoding completes, FFmpeg fully decodes the MP4, FFprobe verifies
303 frames / 30 fps / 10.1 seconds / 1280 x 720, and ZIP CRC checks pass.

Actual output: `pre-delivery-v002/package_receipt.json`,
`package/validation.json`, and `package/manifest.json`. A decoded-video sample
contact sheet is retained in `pre-delivery-v002/encoded_video_contact_sheet.jpg`.
Visual sampling is distinct from full technical decoding and final visual
acceptance. User-facing links should resolve this exact package, not whichever
output file happens to be newest.

Continue the original reconstruction later by repairing the open findings and
running the complete layout, preview and final acceptance workflow. Do not waive
or resolve those findings merely because this review package is viewable.
