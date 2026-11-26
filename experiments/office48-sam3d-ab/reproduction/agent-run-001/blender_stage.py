"""Apply one selected placement, verify invariants, or render one frozen candidate."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
RUN = ROOT / 'outputs/office48-sam3d-ab/agent-run-001'
BASE = RUN.parent
sys.path.insert(0, str(ROOT / 'third_party/aha-3d/src'))
spec = importlib.util.spec_from_file_location('b_scene_tool', ROOT / 'experiments/office48-sam3d-ab/scene.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def event(action, **values):
    with (RUN / 'operations.jsonl').open('a') as stream:
        stream.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(),
                                 'action': action, **values}) + '\n')


def invariants(target):
    scene = bpy.context.scene
    scene.frame_set(1)
    bpy.context.view_layer.update()
    result = {}
    for obj in scene.objects:
        if tool.owner(obj) == target:
            continue
        record = {'type': obj.type, 'matrix': np.round(np.array(obj.matrix_world), 6).tolist(),
                  'materials': [s.material.name if s.material else None for s in obj.material_slots],
                  'instance_id': obj.get('instance_id'), 'semantic_class': obj.get('semantic_class')}
        if obj.type == 'MESH':
            coordinates = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
            obj.data.vertices.foreach_get('co', coordinates)
            record.update(vertices=len(obj.data.vertices), polygons=len(obj.data.polygons),
                          coordinates_sha256=hashlib.sha256(coordinates.tobytes()).hexdigest())
        result[obj.name] = record
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['import', 'alignment', 'diagnostics', 'evaluation'], required=True)
    parser.add_argument('--candidate', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    identity, _, seed_text = args.candidate.partition('-seed-')
    seed = int(seed_text)
    lock_path = BASE / 'frozen-v1/lock.json'
    lock = tool.read(lock_path)
    obj = next(o for o in lock['objects'] if o['id'] == identity)
    scene_folder = RUN / 'scenes' / (args.candidate + '-final')
    final_scene = scene_folder / 'scene.blend'
    common_scene = ROOT / lock['resources']['scene']['path']
    started = time.perf_counter()
    event('blender_stage_start', stage=args.stage, candidate=args.candidate)
    if args.stage == 'import':
        bpy.ops.wm.open_mainfile(filepath=str(common_scene))
        before = invariants(obj['instance_id'])
        tool.import_asset(SimpleNamespace(root=ROOT, lock=lock_path,
                          placement=RUN / 'placements' / (args.candidate + '.json'),
                          glb=BASE / 'generation-001' / identity / f'seed-{seed}' / 'object.glb',
                          out=scene_folder), lock, obj)
        # Retain the raw imported scene and write a distinct orientation-reviewed
        # scene. Native -Y front / Z up was inspected before optimization.
        from aha3d.blender.orientation import tag_orientation, facing_report
        from aha3d.blender.semantics import export_semantics
        raw_scene = scene_folder / 'scene-before-orientation.blend'
        final_scene.rename(raw_scene)
        bpy.ops.wm.open_mainfile(filepath=str(raw_scene))
        target_root = next(o for o in bpy.context.scene.objects if o.get('instance_id') == obj['instance_id'])
        orientation = {'schema_version': 1, 'front_axis': '-Y', 'up_axis': 'Z',
                       'symmetry': 'none', 'origin': 'source_root',
                       'semantic_front': 'seating' if identity == 'chair' else 'generic',
                       'status': 'reviewed',
                       'evidence': 'Agent inspected native four-direction geometry views; chair upper-back geometry lies toward +Y and seat access faces -Y. Cabinet drawer/open-storage front faces -Y. Source development views establish the scene-facing direction.'}
        tag_orientation(target_root, orientation)
        target_root['facing_target_json'] = json.dumps({'direction': [-1,0,0] if identity == 'chair' else [0,-1,0], 'tolerance_degrees': 10})
        facing = facing_report(target_root)
        if facing['status'] != 'pass':
            raise ValueError(f'Inspected asset facing is inconsistent with source intent: {facing}')
        bpy.ops.wm.save_as_mainfile(filepath=str(final_scene))
        bpy.ops.wm.open_mainfile(filepath=str(final_scene))
        imported = tool.read(scene_folder / 'import_report.json')
        imported['raw_import_output'] = {'path': str(raw_scene), 'sha256': tool.digest(raw_scene)}
        imported['orientation_review'] = facing
        imported['output'] = {'path': str(final_scene), 'sha256': tool.digest(final_scene)}
        tool.write(scene_folder / 'import_report.json', imported)
        export_semantics(scene_folder / 'semantics.json')
        after = invariants(obj['instance_id'])
        differences = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        report = {'status': 'passed' if not differences else 'failed',
                  'non_target_objects_checked': len(before), 'differences': differences,
                  'common_scene_sha256': tool.digest(common_scene),
                  'candidate_scene_sha256': tool.digest(final_scene),
                  'scope': 'Names, semantic IDs/classes, frame-1 transforms, material assignments and mesh coordinate/count fingerprints; full camera trajectory checked during rendering.'}
        tool.write(scene_folder / 'non_target_invariants.json', report)
        if differences:
            raise ValueError(f'Non-target scene objects changed: {differences}')
    elif args.stage in ['alignment', 'evaluation']:
        if args.stage == 'evaluation':
            frozen = tool.read(RUN / 'frozen-candidates.json')
            record = next(v for v in frozen['candidates'] if v['candidate'] == args.candidate)
            if tool.digest(final_scene) != record['scene_sha256']:
                raise ValueError('Final scene changed after all-six-candidate freeze')
        output = RUN / 'renders' / args.stage / args.candidate
        tool.render(SimpleNamespace(out=output, lock=lock_path, scene=final_scene,
                    role=args.stage, label=f'B-seed-{seed}', samples=32, root=ROOT, device='CUDA'), lock, obj)
    else:
        from aha3d.blender.placement_check import check
        from aha3d.placement.report import write_report
        bpy.ops.wm.open_mainfile(filepath=str(final_scene))
        reference = bpy.data.collections.get('REFERENCE_ONLY - hide for authored-room delivery')
        if reference:
            reference.hide_render = True
        config = tool.read(ROOT / 'configs/office48_placement_v1.json')
        report = check(config)
        folder = scene_folder / 'placement'
        folder.mkdir(exist_ok=False)
        write_report(folder, report)
        target_issues = [v for v in report.get('issues', []) if obj['instance_id'] in v.get('objects', [])]
        tool.write(scene_folder / 'target_placement_summary.json', {
            'summary': report.get('summary'), 'target': obj['instance_id'], 'target_issues': target_issues,
            'scene_sha256': tool.digest(final_scene),
            'scope': 'Static geometry/support diagnostics only; rigid-body physics disabled.'})
    event('blender_stage_complete', stage=args.stage, candidate=args.candidate,
          wall_seconds=time.perf_counter() - started)
    print('B_AGENT_STAGE_COMPLETED', args.stage, args.candidate, flush=True)


if __name__ == '__main__':
    main()
