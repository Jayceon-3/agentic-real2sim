"""Build a readable, chronologically sorted view of the preserved operation journal."""
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

RUN = Path(__file__).resolve().parents[1]
entries = [json.loads(line) for line in (RUN / 'operations.jsonl').read_text().splitlines() if line.strip()]
entries.sort(key=lambda entry: datetime.fromisoformat(entry['time']))
lines = [
    '# Operation log: six Office48 B candidates', '',
    'The requested B continuation is complete: six fixed generated assets were aligned, imported into six individual replacement scenes, frozen, rendered and scored. This log records agent-operated work after generation. Original GLBs, source inputs and non-target room objects were preserved.', '',
    'All times below use America/New_York (EST, UTC-05:00). The append-only [raw journal](operations.jsonl) retains original UTC timestamps, full search parameters, decisions and failures. Entries below are sorted by timestamp because concurrent stages appended completion records out of order.', '',
    '## Inputs and outputs', '',
    '- Input identity and source hashes: [provenance.json](provenance.json).',
    '- Six GLBs: `../generation-001/{cabinet,chair}/seed-{42,43,44}/object.glb`.',
    '- Selected transforms: `placements/*.json`; final scenes: `scenes/*-final/scene.blend`.',
    '- Freeze before evaluation: [frozen-candidates.json](frozen-candidates.json).',
    '- Production views: 12 alignment and 18 evaluation RGB/binary-mask pairs in `renders/`.',
    '- Results and scene links: [README.md](README.md); [summary CSV](summary/summary.csv).',
    '- Final checksum, raster, camera and invariant validation: [completion.json](completion.json).', '',
    '## Procedure and decisions', '',
    '1. Registered a separate experimental writer scope; inspected source evidence, shared room and all six native asset geometries.',
    '2. Exported triangulated room occluders and the two alignment cameras per target. Compiled a CPU triangle silhouette rasterizer. Fixed an inspection-only missing-world error without changing source files.',
    '3. Preserved an initial search attempt that admitted implausible tilt/front ambiguity. Selected a refined upright, positive uniform-scale search with source-verified facing, exact floor contact and the common target bounds as a layout prior. Only alignment masks were used for placement optimization.',
    '4. Imported each selected transform into a separate copy of the common room. Checked all non-target transforms, geometry, semantic identity and material assignments. Added reviewed facing metadata; rendered source-aligned development views and isolated plan/front/side inspections.',
    '5. Switched production rendering to CUDA after a saved CPU/CUDA cabinet development-mask comparison returned pixel-identical masks. Retained 1280 x 720, Cycles, 32 samples, fixed seed 0 and original cameras.',
    '6. Investigated an apparent missing-vertex-color issue. The hypothesis was disproved: Blender already supplied its default vertex-color material, and explicit/implicit layer emission renders were identical. Removed the unused fallback code and retained original materials. Diagnostic attempts remain in the logs.',
    '7. Reviewed static placement diagnostics. Five candidates had no reported issues; chair seed 44 had open geometry and unavailable inside/outside volume tests. Preserved that sample and reported the unresolved check.',
    '8. An initial freeze assertion rejected the open-geometry result, and evaluation correctly stopped before rendering because no all-six freeze existed. Recorded this preflight failure, explicitly retained the unresolved check, and froze all six scene/placement hashes before evaluation.',
    '9. Rendered the 18 fixed evaluation views, scored visible-mask IoU, and inspected all six evaluation review sheets. Made no placement changes from evaluation results.',
    '10. Validated all six scene hashes, six placement hashes, unchanged original inputs/assets, 30 production image pairs, binary masks, saved camera checks and non-target invariants. Saved scripts, console logs, search traces and final reports.', '',
    '## Implementation and execution evidence', '',
    'Task-specific scripts are preserved under `source/`: `export_geometry.py`, `align.py`, `raster.cpp`, `blender_stage.py`, `blender_batch.py`, `inspection.py`, `collect.py`, `final_report.py` and this log writer. These scripts are bound to this historical run directory; use a new directory for a new experiment.', '',
    'Repository changes: `experiments/office48-sam3d-ab/scene.py` adds explicit optional CUDA selection and records the actual device. Its CPU default remains available. The experiment README documents the setting. The importer has no remaining code change from the disproved color hypothesis.', '',
    'Console evidence: `logs/development-batch.log`, `logs/evaluation-batch.log`, `logs/collect-evaluation.log`, `logs/final-validation.log`, per-candidate search logs and preserved failed/debug attempts. Regression logs record seven experiment tests and 39 SAM 3D script tests passing. The real Blender production run exercises the CUDA path.', '',
    '## Chronological events', '',
    '| Local time | Operation | Details |',
    '| --- | --- | --- |',
]
for entry in entries:
    local = datetime.fromisoformat(entry['time']).astimezone(ZoneInfo('America/New_York'))
    detail = {key: entry[key] for key in ('candidate', 'stage', 'status', 'reason', 'wall_seconds', 'scenes', 'evaluation_views', 'evidence', 'note') if key in entry}
    if not detail:
        detail = {'record': 'Full structured detail in operations.jsonl'}
    text = json.dumps(detail, ensure_ascii=True).replace('|', '&#124;')
    lines.append(f"| {local:%Y-%m-%d %H:%M:%S %Z} | {entry['action']} | {text} |")
lines += ['', '## Scope and limits', '',
    'B-only results do not establish an improvement over AHa-3D. The three seeds describe SAM generation variability within this ongoing agent session. Cabinet occlusion, outline mismatch and the open chair-44 mesh are retained. Fixed evaluation views were visible during earlier annotation and are not strictly unseen. Static diagnostics are not dynamics certification or full-room acceptance. No commits or pushes were performed by this continuation.', '',
    'The experimental writer claim is released as a handoff because upstream full-room reconstruction acceptance is outside this task. This does not leave any requested B rendering, scoring or logging work pending. No background writer jobs remain.', '']
(RUN / 'OPERATION_LOG.md').write_text('\n'.join(lines))
print(f'Wrote {len(entries)} chronological events to {RUN / "OPERATION_LOG.md"}')
