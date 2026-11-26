"""Validate the completed six-candidate experiment and write its durable handoff."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
RUN = ROOT / 'outputs/office48-sam3d-ab/agent-run-001'
BASE = RUN.parent


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    frozen = read(RUN / 'frozen-candidates.json')
    assert read(RUN / 'logs/evaluation-batch.json')['status'] == 'completed'
    assert read(RUN / 'logs/development-batch.json')['status'] == 'completed'
    lock = read(BASE / 'frozen-v1/lock.json')
    for relative, checksum in lock['files'].items():
        assert sha(BASE / 'frozen-v1' / relative) == checksum
    for resource in lock['resources'].values():
        assert sha(ROOT / resource['path']) == resource['sha256']
    rows = []
    total_images = 0
    for record in frozen['candidates']:
        name = record['candidate']
        scene = RUN / record['scene']
        assert sha(scene) == record['scene_sha256']
        assert sha(RUN / record['placement']) == record['placement_sha256']
        imported = read(scene.parent / 'import_report.json')
        assert imported['output']['sha256'] == record['scene_sha256']
        assert imported['orientation_review']['status'] == 'pass'
        invariants = read(scene.parent / 'non_target_invariants.json')
        assert invariants['status'] == 'passed'
        physical = read(scene.parent / 'target_placement_summary.json')
        asset = BASE / 'generation-001' / name.split('-seed-')[0] / ('seed-' + name.split('-seed-')[1])
        assert sha(asset / 'object.glb') == read(asset / 'artifacts.json')['object.glb']['sha256']
        score = read(RUN / 'metrics/evaluation' / name / 'scores.json')
        development = read(RUN / 'metrics/alignment' / name / 'scores.json')
        for role, count in [('alignment', 2), ('evaluation', 3)]:
            folder = RUN / 'renders' / role / name
            render = read(folder / 'render.json')
            assert render['status'] == 'completed'
            assert render['scene_sha256'] == record['scene_sha256']
            assert render['device'] == 'CUDA' and render['samples'] == 32
            assert render['camera_check']['frames_checked'] == 303
            assert len(render['views']) == count
            for view in render['views']:
                assert sha(folder / view['rgb']) == view['rgb_sha256']
                assert sha(folder / view['mask']) == view['mask_sha256']
                with Image.open(folder / view['mask']) as image:
                    assert image.mode == 'L' and image.size == (1280, 720)
                    assert np.isin(np.array(image), [0, 255]).all()
                total_images += 1
        rows.append({'candidate': name, 'scene': record['scene'], 'scene_sha256': record['scene_sha256'],
                     'alignment_mean_iou': development['mean_iou'], 'evaluation_mean_iou': score['mean_iou'],
                     'evaluation_per_view': score['views'], 'static_check': physical['summary']['status'],
                     'static_target_issues': physical['target_issues'],
                     'alignment_search_seconds': read(RUN / 'optimization' / (name + '.json'))['wall_seconds']})
    assert len(rows) == 6 and total_images == 30
    now = datetime.now(timezone.utc).isoformat()
    report = {'status': 'completed_with_recorded_limitations', 'completed_at': now,
              'phase': 'B-only staged object replacement, alignment and fixed-view evaluation',
              'candidates': rows, 'technical_validation': 'passed', 'production_rgb_mask_pairs': total_images,
              'evaluation_views': 18, 'alignment_views': 12,
              'independent_A_comparison_completed': False, 'full_room_acceptance': 'not_assessed',
              'limitations': frozen['limits'] + [
                  'All six B candidates were aligned by the ongoing Codex session, not six independent agent sessions.',
                  'Initialization and search bounds use the common baseline target bounds. A must receive the same layout priors, alignment masks, facing constraints and search budget for a fair comparison.',
                  'Original imported materials and shared room lighting are retained; this is not a photometric fit.',
                  'Source dimensions are uncalibrated predicted metres. Static diagnostics are not measured physical accuracy or dynamics certification.',
                  'Full model/API token and subscription-cost accounting is unavailable for this interactive session. Raw stage times and failed/debug stages are retained.']}
    (RUN / 'completion.json').write_text(json.dumps(report, indent=2) + '\n')
    generation = read(BASE / 'generation-001/batch.json')
    timing = {'generation_batch_seconds': generation['total_wall_seconds'],
              'selected_alignment_search_seconds_sum': sum(r['alignment_search_seconds'] for r in rows),
              'development_blender_batch_seconds': read(RUN / 'logs/development-batch.json')['wall_seconds'],
              'evaluation_blender_batch_seconds': read(RUN / 'logs/evaluation-batch.json')['wall_seconds'],
              'scope': 'Stage wall times may overlap with preparation. Failed/debug work is separately preserved in logs and operations.jsonl. Sum is not interactive-session end-to-end time.'}
    (RUN / 'timing-summary.json').write_text(json.dumps(timing, indent=2) + '\n')
    for original, name in [('scripts/sam3d_objects/import_blender.py', 'snapshot-import_blender-final.py'),
                           ('experiments/office48-sam3d-ab/scene.py', 'snapshot-scene-final.py')]:
        shutil.copyfile(ROOT / original, RUN / 'source' / name)
    lines = [
        '# Six SAM 3D B candidates: agent run 001', '',
        'Status: completed with recorded limitations. This is a B-only staged experiment; no improvement over AHa-3D is claimed.', '',
        'The agent consumed the six fixed GLBs, preserved the original room and non-target objects, selected positive uniform transforms using only two development views per target, inspected geometry and source-camera views, froze all six candidates, then rendered and scored the three fixed evaluation views per target. All source inputs and generated assets remain unchanged.', '',
        '## Results', '',
        '| Candidate | Alignment mean IoU | Evaluation mean IoU | Static check | Scene |',
        '| --- | ---: | ---: | --- | --- |']
    for r in rows:
        lines.append(f"| {r['candidate']} | {r['alignment_mean_iou']:.4f} | {r['evaluation_mean_iou']:.4f} | {r['static_check']} | [scene.blend]({r['scene']}) |")
    lines += ['', 'Development and evaluation columns use different view sets and must not be interpreted as a before/after improvement.', '',
        '## Files', '',
        '- `summary/summary.csv`: per-object mean and sample standard deviation over the three B seeds.',
        '- `metrics/evaluation/*/per_view.csv`: all 18 individual evaluation IoUs.',
        '- `review/evaluation-*.jpg`: matched source/render/mask-error closeups for every candidate.',
        '- `review/*-isolated-sheet.jpg`: plan/front/side inspection views for all six generated objects.',
        '- `placements/*.json`: selected translation, XYZ Euler rotation and uniform scale.',
        '- `frozen-candidates.json`: immutable all-six selection before evaluation, with scene and placement hashes.',
        '- `operations.jsonl`: agent decisions, refinements, stage starts/completions and freeze event.',
        '- `OPERATION_LOG.md`: readable chronological operation log in America/New_York time.',
        '- `optimization/*.jsonl`: every numeric development-view search call; no evaluation feedback.',
        '- `logs/`: console output, stage journals, regression tests, failures and diagnostic checks.',
        '- `source/`: run scripts, triangle rasterizer, implementation snapshots and renderer patch.',
        '- `completion.json`, `provenance.json`, `timing-summary.json`: validation, input identity, scope and timing.', '',
        '## Decisions and preserved history', '',
        'An initial unconstrained silhouette search admitted implausible tilt/front ambiguity; its code, partial results and logs are retained under `*-attempt-001`. The selected search uses upright orientation and a source-verified front, with floor contact. Original target bounds initialize location and size; they are a shared layout prior, not geometric ground truth.', '',
        'Native four-direction views and upper-back geometry establish -Y front / Z up. Chair facing is approximately scene -X; cabinet facing is approximately scene -Y. Reviewed orientation metadata resolves the imported-chair facing coverage issue without changing mesh geometry.', '',
        'CPU and CUDA cabinet development masks were pixel-identical in the saved compatibility check. Production images use NVIDIA T550 CUDA, Cycles, 1280 x 720, fixed seed and 32 samples. A must use the same settings.', '',
        'A tentative missing-vertex-color diagnosis was disproved: Blender already connected its default material to vertex colors. Implicit and explicit color-layer lookups gave identical isolated emission renders. The unused fallback was removed; original materials and vertex colors are retained. Earlier scenes/renders and this diagnostic are preserved.', '',
        '## Limits', '']
    lines += ['- ' + limit for limit in report['limitations']]
    lines += ['', 'Chair seed 44 remains renderable but has open mesh components. Volume inside/outside collision tests are unavailable for them; it is not counted as a clean static physical pass. All other candidates have no reported static issues. Generated geometry was not repaired or selectively discarded.', '',
        'The cabinet has severe foreground desk/chair occlusion in development views. The unchanged approximate room also changes its visible area. Low scores and fixed-view annotation limitations are retained; do not use this run to assert universal reconstruction gains.', '',
        'The human supplied reviewed masks and previously generated assets. No human placement adjustment was consumed in this agent run. The existing full-room AHa-3D acceptance scope and dirty submodule were preserved.', '',
        '## Timing', '', f"Generation batch: {timing['generation_batch_seconds']:.2f} s. Selected six placement searches: {timing['selected_alignment_search_seconds_sum']:.2f} s in aggregate. Final development Blender batch: {timing['development_blender_batch_seconds']:.2f} s. Evaluation Blender batch: {timing['evaluation_blender_batch_seconds']:.2f} s.", '',
        'These figures exclude or separate one-time tool preparation and debugging; stage times overlap and are not an A/B cost result. See raw logs for all attempts. Full agent token cost is unavailable.', '',
        '## Continuation', '',
        'Keep the six selected scenes frozen. Evaluate the fixed original A condition with the same development evidence, layout priors, transform constraints, post-asset alignment budget and CUDA evaluation settings. Compare per-object results and validity outcomes. The three B seeds measure asset-generation variability; they are not three independent AHa-3D agent runs. An independent agent comparison would require a separately specified protocol and new authoring runs; copies of historical furniture are not independent A runs.', '',
        'Run scripts are bound to this run directory. Preserve it as evidence; use a new run directory and explicit path updates for any new development experiment. Evaluation findings must not trigger edits to these selected scenes.', '']
    (RUN / 'README.md').write_text('\n'.join(lines))
    with (RUN / 'operations.jsonl').open('a') as stream:
        stream.write(json.dumps({'time': now, 'action': 'completion_validation', 'status': report['status'],
                                 'selected_scenes': 6, 'evaluation_views': 18, 'source_inputs_unchanged': True}) + '\n')
    print('VALIDATED', len(rows), 'scenes;', total_images, 'RGB/mask pairs')
    print(json.dumps(read(RUN / 'summary/summary.json')['groups'], indent=2))


if __name__ == '__main__':
    main()
