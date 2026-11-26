"""Export unchanged scene/asset triangles and native-orientation inspection views."""
import json
from pathlib import Path
import sys
import time

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[4]
RUN = ROOT / 'outputs/office48-sam3d-ab/agent-run-001'
BASE = RUN.parent
sys.path.insert(0, str(ROOT / 'third_party/aha-3d/src'))
from aha3d.blender.body import camera_matrices


def owner(obj):
    while obj:
        if obj.get('instance_id'):
            return obj['instance_id']
        obj = obj.parent
    return ''


def triangles(objects):
    vertices, faces = [], []
    offset = 0
    dg = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        if obj.type not in {'MESH', 'CURVE', 'FONT'} or obj.hide_render:
            continue
        evaluated = obj.evaluated_get(dg)
        mesh = evaluated.to_mesh()
        if not mesh:
            continue
        mesh.calc_loop_triangles()
        points = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertices.foreach_get('co', points)
        points = points.reshape(-1, 3)
        matrix = np.array(obj.matrix_world, dtype=np.float64)
        points = points @ matrix[:3, :3].T + matrix[:3, 3]
        indices = np.array([t.vertices[:] for t in mesh.loop_triangles], dtype=np.int32)
        if len(indices):
            vertices.append(points.astype(np.float32))
            faces.append(indices + offset)
            offset += len(points)
        evaluated.to_mesh_clear()
    return np.concatenate(vertices), np.concatenate(faces)


def save_geometry(name, objects):
    vertices, faces = triangles(objects)
    np.savez_compressed(RUN / 'geometry' / (name + '.npz'), vertices=vertices, faces=faces)
    return {'vertices': len(vertices), 'triangles': len(faces),
            'min': vertices.min(0).tolist(), 'max': vertices.max(0).tolist()}


started = time.perf_counter()
lock = json.loads((BASE / 'frozen-v1/lock.json').read_text())
bpy.ops.wm.open_mainfile(filepath=str(ROOT / lock['resources']['scene']['path']))
scene = bpy.context.scene
reference = bpy.data.collections.get('REFERENCE_ONLY - hide for authored-room delivery')
excluded = set(reference.all_objects) if reference else set()
objects = [o for o in scene.objects if o not in excluded and not o.hide_render]
report = {'scene': {}, 'assets': {}, 'export_seconds': None}
for identity, target in [('cabinet', 'furniture/cabinet'), ('chair', 'furniture/chair-guest-1')]:
    report['scene'][identity] = save_geometry('original-' + identity, [o for o in objects if owner(o) == target])
    save_geometry('occluders-' + identity, [o for o in objects if owner(o) != target])
    roots = [o for o in objects if o.get('instance_id') == target]
    report['scene'][identity]['root_matrix'] = [list(row) for row in roots[0].matrix_world]
    views = next(o for o in lock['objects'] if o['id'] == identity)['views']
    for view in views:
        if view['role'] != 'alignment':
            continue
        scene.frame_set(view['frame'] + 1)
        scene.render.resolution_x, scene.render.resolution_y = 1280, 720
        scene.render.resolution_percentage = 100
        k, rt, *_ = camera_matrices(scene, bpy.context.evaluated_depsgraph_get())
        np.savez(RUN / 'geometry' / f'camera-{view["frame"]}.npz', K=k, rt=rt)

for identity in ['cabinet', 'chair']:
    for seed in [42, 43, 44]:
        name = f'{identity}-seed-{seed}'
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(BASE / 'generation-001' / identity / f'seed-{seed}' / 'object.glb'))
        bpy.context.view_layer.update()
        report['assets'][name] = save_geometry(name, list(bpy.context.scene.objects))
        if seed != 42:
            continue
        scene = bpy.context.scene
        scene.render.engine = 'BLENDER_WORKBENCH'
        scene.render.resolution_x = scene.render.resolution_y = 320
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = 'PNG'
        scene.display.shading.color_type = 'MATERIAL'
        scene.display.shading.light = 'STUDIO'
        scene.display.shading.show_shadows = True
        scene.display.shading.show_cavity = True
        scene.display.shading.background_type = 'WORLD'
        if scene.world is None:
            scene.world = bpy.data.worlds.new('Inspection world')
        scene.world.color = (.08, .08, .08)
        bounds = report['assets'][name]
        center = (Vector(bounds['min']) + Vector(bounds['max'])) * .5
        extent = max(b-a for a,b in zip(bounds['min'], bounds['max']))
        bpy.ops.object.camera_add()
        cam = bpy.context.object
        scene.camera = cam
        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = extent * 1.5
        for label, direction in [('plus-x',(1,0,.55)),('minus-x',(-1,0,.55)),('plus-y',(0,1,.55)),('minus-y',(0,-1,.55))]:
            cam.location = center + Vector(direction) * (extent * 3)
            cam.rotation_euler = (center - cam.location).to_track_quat('-Z','Y').to_euler()
            scene.render.filepath = str(RUN / 'review' / f'{name}-native-{label}.png')
            bpy.ops.render.render(write_still=True)
report['export_seconds'] = time.perf_counter() - started
(RUN / 'geometry/export.json').write_text(json.dumps(report, indent=2) + '\n')
print('GEOMETRY_EXPORTED', report['export_seconds'])
