# Office48 B results: agent run 001

Six fixed SAM 3D assets were aligned and evaluated on November 26, 2026.
Each scene replaces one object; the common room and non-target objects remain
fixed. Two alignment views per object were used for placement. All six scene
and placement hashes were frozen before three evaluation views per object.

| Object | Seeds | Evaluation mean IoU | Sample standard deviation |
| --- | --- | ---: | ---: |
| Cabinet | 42, 43, 44 | 0.258628 | 0.004557 |
| Chair | 42, 43, 44 | 0.866870 | 0.010135 |

Standard deviation is across the three per-seed mean IoUs. These are asset
variability samples from one ongoing agent session, not three independent
AHa-3D agent runs. A has not been scored in this continuation; no A/B gain is
claimed. Cabinet occlusion and silhouette mismatch remain. Chair seed 44 has
open mesh components and incomplete volume collision verification. Evaluation
views were visible during earlier annotation and are fixed rather than strictly
unseen. Static checks do not establish full-room acceptance or dynamics validity.

This directory contains compact result evidence, all 18 per-view IoUs, selected
placements, frozen input/scene identities, visual-review notes and timings.
Files are copied without rewriting historical metadata; paths inside them refer
to the original run layout. Original source assets, masks, rendered views,
scenes, search traces, console logs, `operations.jsonl` and `OPERATION_LOG.md`
remain under `outputs/office48-sam3d-ab/agent-run-001/` and are distributed
separately. They are not included in Git. The input lock alone does not contain
the referenced image/mask files. This compact record is not a complete runtime
artifact bundle.

Historical scripts are archived at `../../reproduction/agent-run-001/`.
All source inputs and original GLBs were hash-verified unchanged, and the six
selected scenes and 30 production RGB/mask pairs passed final technical checks.
See `completion.json` for candidate-specific scores and limitations.
