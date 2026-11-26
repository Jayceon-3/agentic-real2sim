"""Isolate vertex-color lookup from room lighting without modifying input assets."""
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[4]
RUN = ROOT / 'outputs/office48-sam3d-ab/agent-run-001'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(RUN.parent / 'generation-001/cabinet/seed-42/object.glb'))
mesh = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
material = mesh.material_slots[0].material
node = next(n for n in material.node_tree.nodes if n.type == 'VERTEX_COLOR')
output = next(n for n in material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL')
emission = material.node_tree.nodes.new('ShaderNodeEmission')
material.node_tree.links.new(node.outputs['Color'], emission.inputs['Color'])
material.node_tree.links.new(emission.outputs[0], output.inputs['Surface'])
bpy.ops.object.camera_add(location=(.8,-1.3,.6))
scene = bpy.context.scene
scene.camera = bpy.context.object
scene.camera.rotation_euler = (Vector((0,0,0))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
scene.camera.data.type = 'ORTHO'
scene.camera.data.ortho_scale = .8
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 1
scene.render.resolution_x = scene.render.resolution_y = 128
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
scene.view_settings.exposure = 0
for label, layer in [('implicit',''),('explicit','Color')]:
    node.layer_name = layer
    scene.render.filepath = str(RUN / 'review' / f'vertex-color-binding-{label}.png')
    bpy.ops.render.render(write_still=True)
print('VERTEX_BINDING_CHECK_RENDERED')
