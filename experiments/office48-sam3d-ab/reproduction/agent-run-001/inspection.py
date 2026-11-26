"""Save isolated plan/front/side geometry views for each final B object."""
import importlib.util
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[4]
RUN = ROOT / 'outputs/office48-sam3d-ab/agent-run-001'
spec = importlib.util.spec_from_file_location('inspection_scene', ROOT / 'experiments/office48-sam3d-ab/scene.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

records = []
for identity in ['cabinet', 'chair']:
    target = 'furniture/cabinet' if identity == 'cabinet' else 'furniture/chair-guest-1'
    for seed in [42, 43, 44]:
        name = f'{identity}-seed-{seed}'
        folder = RUN / 'scenes' / (name + '-final')
        bpy.ops.wm.open_mainfile(filepath=str(folder / 'scene.blend'))
        scene = bpy.context.scene
        scene.frame_set(1)
        report = tool.read(folder / 'import_report.json')
        bounds = report['world_bounds_m']
        center = (Vector(bounds['min']) + Vector(bounds['max'])) * .5
        extent = max(b-a for a,b in zip(bounds['min'], bounds['max']))
        for obj in scene.objects:
            if obj.type in {'MESH', 'CURVE', 'FONT'}:
                obj.hide_render = tool.owner(obj) != target
        bpy.ops.object.camera_add()
        cam = bpy.context.object
        scene.camera = cam
        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = extent * 1.4
        scene.render.engine = 'BLENDER_WORKBENCH'
        scene.render.use_compositing = False
        scene.render.use_sequencer = False
        scene.render.resolution_x = scene.render.resolution_y = 360
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = 'PNG'
        scene.display.shading.color_type = 'MATERIAL'
        scene.display.shading.light = 'STUDIO'
        scene.display.shading.show_shadows = True
        scene.display.shading.show_cavity = True
        directions = {'plan': (0,0,1), 'front': (0,-1,.1) if identity == 'cabinet' else (-1,0,.1),
                      'side': (1,0,.1) if identity == 'cabinet' else (0,-1,.1)}
        for label, direction in directions.items():
            cam.location = center + Vector(direction) * (extent * 3)
            cam.rotation_euler = (center - cam.location).to_track_quat('-Z','Y').to_euler()
            path = RUN / 'review' / f'{name}-isolated-{label}.png'
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            records.append({'candidate': name, 'view': label, 'image': str(path.relative_to(RUN)),
                            'meaning': 'Isolated geometry including occluded surfaces; not a visible-mask score or source-camera view.'})
tool.write(RUN / 'review/isolated-views.json', records)
print('ISOLATED_INSPECTION_COMPLETED', len(records))
