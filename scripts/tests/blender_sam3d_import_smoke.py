"""Run with background Blender and -- --out NEW_DIR; uses synthetic static assets."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('sam3d_import', ROOT / 'scripts/sam3d_objects/import_blender.py')
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    parent = bpy.data.objects.new('asset-parent', None)
    bpy.context.scene.collection.objects.link(parent)
    material = bpy.data.materials.new('asset-material')
    material.use_nodes = True
    for x in (0, 3):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, 0, 0))
        bpy.context.object.parent = parent
        bpy.context.object.data.materials.append(material)
    parent.location.z = 1
    bpy.ops.export_scene.gltf(filepath=str(out / 'asset.glb'), export_format='GLB')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.object.camera_add(location=(4, -4, 3))
    camera = bpy.context.object
    bpy.context.scene.camera = camera
    camera_name = camera.name
    bpy.ops.mesh.primitive_cube_add(location=(10, 10, 10))
    untouched = bpy.context.object.name
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'source.blend'))
    source_hash = importer.digest(out / 'source.blend')
    placement = json.loads((ROOT / 'configs/sam3d_placement.example.json').read_text())
    placement.update(translation_m=[2, 3, 4], rotation_euler_xyz_deg=[0, 0, 90], scale=[2, 3, 4])
    importer.write(out / 'placement.json', placement)
    request = SimpleNamespace(scene=out / 'source.blend', glb=out / 'asset.glb',
                              placement=out / 'placement.json', object_id='furniture/test',
                              replace=False, out=out / 'added')
    importer.run(request)
    report = json.loads((request.out / 'import_report.json').read_text())
    assert report['reopen_verified'] and len(report['mesh_objects']) == 2
    assert len(report['materials']) == 1
    assert bpy.context.scene.camera.name == camera_name
    assert tuple(bpy.data.objects[untouched].location) == (10, 10, 10)
    # A 90-degree Z rotation swaps X/Y bounds; this verifies hierarchy transforms
    # are applied once, including nonuniform scale and an off-origin asset parent.
    lo = report['imported_bounds_before_placement']['min']
    hi = report['imported_bounds_before_placement']['max']
    expected_lo = [2 - 3 * hi[1], 3 + 2 * lo[0], 4 + 4 * lo[2]]
    expected_hi = [2 - 3 * lo[1], 3 + 2 * hi[0], 4 + 4 * hi[2]]
    for key, expected in [('min', expected_lo), ('max', expected_hi)]:
        assert (Vector(report['world_bounds_m'][key]) - Vector(expected)).length < 1e-4
    request.scene = out / 'added/scene.blend'
    request.out = out / 'duplicate'
    try:
        importer.run(request)
    except ValueError as exc:
        assert 'Existing ID' in str(exc)
    else:
        raise AssertionError('Duplicate ID was accepted')
    assert not (request.out / 'scene.blend').exists()
    assert json.loads((request.out / 'import_report.json').read_text())['status'] == 'failed'
    request.replace = True
    request.out = out / 'replaced'
    importer.run(request)
    assert sum(obj.get('instance_id') == 'furniture/test' for obj in bpy.context.scene.objects) == 1
    assert len([obj for obj in bpy.context.scene.objects if obj.type == 'MESH']) == 3
    output_hash = importer.digest(request.out / 'scene.blend')
    try:
        importer.run(request)
    except FileExistsError:
        pass
    else:
        raise AssertionError('Existing output directory was accepted')
    assert importer.digest(request.out / 'scene.blend') == output_hash
    assert importer.digest(out / 'source.blend') == source_hash
    print('SAM3D_IMPORT_SMOKE_PASSED', out)


if __name__ == '__main__':
    main()
