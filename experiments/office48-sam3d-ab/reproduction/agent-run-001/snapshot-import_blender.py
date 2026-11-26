"""Import a static SAM 3D GLB into a saved AHa-3D scene in background Blender."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import traceback


ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def load_placement(path):
    """Strict placement contract, also testable without Blender installed."""
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    required = {'schema_version', 'coordinate_space', 'translation_m',
                'rotation_euler_xyz_deg', 'scale', 'semantic_class'}
    optional = {'support_id', 'note'}
    if not isinstance(value, dict) or set(value) - required - optional or required - set(value):
        raise ValueError('Placement has missing or unknown fields')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('Expected placement schema_version 1')
    if value['coordinate_space'] != 'blender_imported_to_scene_world':
        raise ValueError('Placement must map Blender-imported coordinates to scene world')
    for key in ('translation_m', 'rotation_euler_xyz_deg', 'scale'):
        vector = value[key]
        if not isinstance(vector, list) or len(vector) != 3 or any(
            type(x) not in (int, float) or not math.isfinite(x) for x in vector
        ):
            raise ValueError(key + ' must contain three finite numbers')
    if any(x <= 0 for x in value['scale']):
        raise ValueError('Scale must be positive; mirrored/degenerate placement is unsupported')
    for key in ('semantic_class', 'support_id', 'note'):
        if key in value and (not isinstance(value[key], str) or not value[key].strip()):
            raise ValueError(key + ' must be a nonempty string')
    if not value['semantic_class'].strip('/'):
        raise ValueError('semantic_class must name a class')
    return value


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scene', type=Path, required=True, help='Existing source .blend')
    p.add_argument('--glb', type=Path, required=True, help='Generated static object.glb')
    p.add_argument('--placement', type=Path, required=True, help='Explicit placement JSON')
    p.add_argument('--object-id', required=True, help='Scene semantic instance_id')
    p.add_argument('--replace', action='store_true', help='Replace an existing static semantic root')
    p.add_argument('--out', type=Path, required=True, help='New output directory; never overwritten')
    return p


def bounds(objects):
    from mathutils import Vector
    points = [obj.matrix_world @ Vector(corner) for obj in objects
              if obj.type == 'MESH' for corner in obj.bound_box]
    if not points:
        raise ValueError('GLB contains no mesh objects')
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    if not all(math.isfinite(x) for x in lo + hi) or max(b-a for a, b in zip(lo, hi)) <= 0:
        raise ValueError('Invalid or degenerate mesh bounds')
    return {'min': lo, 'max': hi, 'dimensions': [b-a for a, b in zip(lo, hi)]}


def run(args):
    import bpy
    from mathutils import Euler, Matrix, Vector
    sys.path.insert(0, str(ROOT / 'third_party/aha-3d/src'))
    from aha3d.blender.semantics import adopt_group, descendants, export_semantics, roots

    if not bpy.app.background:
        raise ValueError('Run in background Blender to protect interactive edits')
    for name, suffix in (('scene', '.blend'), ('glb', '.glb'), ('placement', '.json')):
        path = getattr(args, name).resolve()
        if not path.is_file() or path.suffix.lower() != suffix:
            raise ValueError(f'{name} must be an existing {suffix} file: {path}')
        setattr(args, name, path)
    if not args.object_id.strip():
        raise ValueError('object-id must be nonempty')
    placement = load_placement(args.placement)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    report = {'schema_version': 1, 'status': 'running', 'stage': 'open_scene',
              'object_id': args.object_id, 'replace': args.replace, 'timings_seconds': {},
              'blender_version': bpy.app.version_string,
              'inputs': {key: {'path': str(getattr(args, key)), 'sha256': digest(getattr(args, key))}
                         for key in ('scene', 'glb', 'placement')},
              'script_sha256': digest(__file__), 'placement': placement,
              'limitations': ['Placement is supplied, not estimated or visually accepted.',
                             'Native pose.json is not applied; glTF axis conversion is handled by Blender.',
                             'Static assets only; geometry bounds are not collision or silhouette checks.']}
    write(out / 'import_report.json', report)
    try:
        t = time.perf_counter()
        bpy.ops.wm.open_mainfile(filepath=str(args.scene))
        report['timings_seconds']['open_scene'] = time.perf_counter() - t
        scene = bpy.context.scene
        if not math.isclose(scene.unit_settings.scale_length, 1.0, abs_tol=1e-8):
            raise ValueError('Expected scene unit scale 1 (one Blender unit per metre)')
        original_camera = scene.camera
        original_frame = scene.frame_current
        known = {obj['instance_id']: obj for obj in roots()}
        target = known.get(args.object_id)
        if bool(target) != args.replace:
            raise ValueError('Existing ID requires --replace; --replace requires an existing ID')
        support = placement.get('support_id', target.get('support_id') if target else None)
        if support is not None and (support not in known or support == args.object_id):
            raise ValueError('support_id must identify another semantic root in this scene')
        removed = []
        if target:
            removed = [target] + descendants(target)
            if any(obj.get('instance_id') for obj in removed[1:]):
                raise ValueError('Replacement contains nested semantic roots; split the target first')
            if any(obj.animation_data or obj.constraints or obj.get('joint_id')
                   or obj.get('asset_articulated') for obj in removed):
                raise ValueError('Replacement of animated, constrained or articulated objects is unsupported')
            report['replaced_objects'] = [obj.name for obj in removed]
            report['previous_matrix_world'] = [list(row) for row in target.matrix_world]

        report['stage'] = 'import_glb'
        t = time.perf_counter()
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(args.glb))
        imported = list(set(bpy.data.objects) - before)
        if any(obj.type not in ('MESH', 'EMPTY') or obj.animation_data or obj.constraints
               or obj.modifiers or obj.get('instance_id') for obj in imported):
            raise ValueError('Expected untagged static mesh/empty GLB hierarchy')
        bpy.context.view_layer.update()
        report['imported_bounds_before_placement'] = bounds(imported)
        report['timings_seconds']['import_glb'] = time.perf_counter() - t

        report['stage'] = 'placement'
        t = time.perf_counter()
        for obj in reversed(removed):
            bpy.data.objects.remove(obj, do_unlink=True)
        # Group at identity first: adopt_group preserves imported world transforms.
        # Moving the root afterward applies T @ R_XYZ @ S to all imported geometry.
        root = adopt_group(imported, placement['semantic_class'], args.object_id,
                           support_id=support)
        rotation = Euler([math.radians(x) for x in placement['rotation_euler_xyz_deg']], 'XYZ')
        root.matrix_world = (Matrix.Translation(Vector(placement['translation_m']))
                             @ rotation.to_matrix().to_4x4()
                             @ Matrix.Diagonal((*placement['scale'], 1.0)))
        root['sam3d_glb_sha256'] = report['inputs']['glb']['sha256']
        root['sam3d_placement_sha256'] = report['inputs']['placement']['sha256']
        scene.camera = original_camera
        scene.frame_set(original_frame)
        bpy.context.view_layer.update()
        report['matrix_world'] = [list(row) for row in root.matrix_world]
        report['world_bounds_m'] = bounds(imported)
        report['mesh_objects'] = sorted(obj.name for obj in imported if obj.type == 'MESH')
        report['materials'] = sorted({slot.material.name for obj in imported for slot in obj.material_slots
                                      if slot.material})
        report['timings_seconds']['placement'] = time.perf_counter() - t

        report['stage'] = 'save_scene'
        t = time.perf_counter()
        target_path = out / 'scene.blend'
        # Make existing relative dependencies resolvable from the new directory.
        bpy.ops.file.make_paths_absolute()
        bpy.ops.wm.save_as_mainfile(filepath=str(target_path))
        report['timings_seconds']['save_scene'] = time.perf_counter() - t
        report['stage'] = 'reopen_check'
        t = time.perf_counter()
        bpy.ops.wm.open_mainfile(filepath=str(target_path))
        reopened = next(obj for obj in roots() if obj['instance_id'] == args.object_id)
        actual = [list(row) for row in reopened.matrix_world]
        if any(abs(a-b) > 1e-5 for row_a, row_b in zip(actual, report['matrix_world'])
               for a, b in zip(row_a, row_b)):
            raise ValueError('Saved placement changed after reopening')
        children = descendants(reopened)
        if sorted(obj.name for obj in children if obj.type == 'MESH') != report['mesh_objects']:
            raise ValueError('Imported mesh hierarchy changed after reopening')
        materials = sorted({slot.material.name for obj in children for slot in obj.material_slots if slot.material})
        if materials != report['materials']:
            raise ValueError('Material assignments changed after reopening')
        export_semantics(out / 'semantics.json')
        report['timings_seconds']['reopen_check'] = time.perf_counter() - t
        report.update(status='completed', stage='complete', visual_review='not_performed',
                      output={'path': str(target_path), 'sha256': digest(target_path)},
                      reopen_verified=True)
        print('SAM3D_IMPORTED', target_path)
    except Exception:
        report['status'] = 'failed'
        (out / 'error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise
    finally:
        report['timings_seconds']['total'] = time.perf_counter() - started
        write(out / 'import_report.json', report)


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    run(parser().parse_args(argv))
