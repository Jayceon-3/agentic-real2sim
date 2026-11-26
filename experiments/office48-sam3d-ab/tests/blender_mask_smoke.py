"""Synthetic Blender check: visible-mask export must retain foreground occlusion."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("office48_scene_smoke", HERE / "scene.py")
scene_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scene_tool)
sys.path.insert(0, str(HERE.parents[1] / "third_party/aha-3d/src"))
from aha3d.blender.body import camera_matrices


def main():
    out = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
    out.mkdir(parents=True, exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.resolution_x = scene.render.resolution_y = 64
    scene.render.resolution_percentage = 100
    scene.render.fps = 30
    scene.frame_end = 303
    bpy.ops.object.camera_add(location=(0, -8, 0))
    scene.camera = bpy.context.object
    scene.camera.rotation_euler = (Vector((0, 0, 0)) - scene.camera.location).to_track_quat('-Z', 'Y').to_euler()
    bpy.ops.mesh.primitive_cube_add(size=2)
    bpy.context.object["instance_id"] = "furniture/cabinet"
    bpy.ops.mesh.primitive_cube_add(size=1.5, location=(.9, -2, 0))
    blocker_name = bpy.context.object.name
    k, rt, *_ = camera_matrices(scene, bpy.context.evaluated_depsgraph_get())
    np.savez(out / "camera.npz", c2w=np.repeat(np.linalg.inv(rt)[None], 303, axis=0),
             K=np.repeat(k[None], 303, axis=0))
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "source.blend"))
    obj = {"id": "cabinet", "instance_id": "furniture/cabinet",
           "views": [{"frame": 0, "role": "evaluation"}]}
    lock = {"protocol": {"image_size": [64, 64]}, "resources": {"camera": {"path": "camera.npz"}}}
    scene_tool.write(out / "lock.json", lock)
    args = SimpleNamespace(root=out, lock=out / "lock.json", scene=out / "source.blend",
                           out=out / "visible", role="evaluation", label="B-seed-42", samples=1)
    scene_tool.render(args, lock, obj)
    bpy.ops.wm.open_mainfile(filepath=str(out / "source.blend"))
    bpy.data.objects[blocker_name].hide_render = True
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "isolated.blend"))
    args.scene, args.out = out / "isolated.blend", out / "isolated"
    scene_tool.render(args, lock, obj)
    counts = []
    for folder in ("visible", "isolated"):
        image = bpy.data.images.load(str(out / folder / "source-000000-mask.png"), check_existing=False)
        values = np.array(image.pixels[:]).reshape(64, 64, 4)[..., 0]
        assert np.isin(values, [0, 1]).all(), np.unique(values)
        counts.append(int((values > .5).sum()))
    assert 0 < counts[0] < counts[1], counts
    print("VISIBLE_MASK_SMOKE_PASSED", counts)


if __name__ == "__main__":
    main()
