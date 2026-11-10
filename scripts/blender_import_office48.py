"""Run in background Blender: new diagnostic reference scene, source camera, checks.

No supplied authored office is opened. Core-only is the default diagnostic display;
--include-context imports the full eligible hybrid display, preserving all arrays.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "third_party/aha-3d"
sys.path.insert(0, str(UPSTREAM / "src"))
sys.path.insert(0, str(UPSTREAM / "tools/layout_inspection"))

import bpy
import numpy as np
from aha3d.blender.ensemble import bake_camera, camera_check
from render_blender import triangle_mesh, color, save_rgb


def read(path):
    return json.loads(path.read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def collection(name, parent):
    value = bpy.data.collections.new(name)
    parent.children.link(value)
    return value


def main():
    if not bpy.app.background:
        raise RuntimeError("Run with Blender --background; this script creates a new scene")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="New output directory")
    parser.add_argument("--include-context", action="store_true")
    parser.add_argument("--render-checks", action="store_true", help="Three CPU reference renders; not authored-room evidence")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    prepared = (ROOT / args.prepared).resolve()
    out = (ROOT / args.out).resolve()
    out.relative_to(ROOT)
    if out.exists():
        raise ValueError("Output already exists; select a new revision")
    plan = read(prepared / "import_plan.json")
    lock_path = ROOT / plan["input_lock"]
    if digest(lock_path) != plan["input_lock_sha256"]:
        raise ValueError("Input lock changed since camera preparation")
    lock = read(lock_path)
    for entry in lock["files"]:
        if digest(ROOT / entry["path"]) != entry["sha256"]:
            raise ValueError("Locked input changed: " + entry["path"])
    cache = prepared / "camera.npz"
    if digest(cache) != plan["camera_sha256"]:
        raise ValueError("Prepared camera cache changed")
    ref = plan["reference"]
    metadata = read(ROOT / ref["geometry_manifest"])
    cameras = read(ROOT / ref["cameras"])
    with np.load(ROOT / ref["geometry"], allow_pickle=False) as z:
        if not np.allclose(z["world_transform"], cameras["world_transform"], atol=1e-6):
            raise ValueError("Geometry and camera bases differ")
        xyz, rgb = z["display_vertices"], z["display_colors"]
        faces, labels, roles = z["display_faces"], z["display_face_layer"], z["display_face_role"]
    if not np.isfinite(xyz).all() or faces.min() < 0 or faces.max() >= len(xyz):
        raise ValueError("Invalid reference display geometry")
    # These arrays already contain aligned coordinates. Never reapply world_transform.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    t = plan["timing"]
    scene.frame_start, scene.frame_end = t["start"], t["end"]
    scene.render.fps = 30
    scene.render.fps_base = 1
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    scene["units_warning"] = "Uncalibrated predicted metres, not measured metric dimensions"
    scene["experiment_id"] = plan["experiment_id"]
    scene["stage"] = "reference_setup_only_no_authored_room"
    reference = collection("REFERENCE_ONLY - hide for authored-room delivery", scene.collection)
    authored = collection("AUTHORED_ROOM - empty", scene.collection)
    authored["status"] = "No room authored yet"
    material = bpy.data.materials.new("Reference source RGB - diagnostic emission")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    attribute = nodes.new("ShaderNodeAttribute")
    attribute.attribute_name = "Source RGB"
    emission = nodes.new("ShaderNodeEmission")
    output = nodes.new("ShaderNodeOutputMaterial")
    material.node_tree.links.new(attribute.outputs["Color"], emission.inputs["Color"])
    material.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])
    groups = [("TSDF structural core", (labels == 0) & (roles == 0))]
    if args.include_context:
        groups += [("Source context", (labels == 0) & (roles == 1)),
                   ("Uncertain glass", labels == 2), ("Uncertain mirror", labels == 3),
                   ("Uncertain unknown", labels == 5)]
    inventory = []
    for name, selected in groups:
        chosen = faces[selected]
        if not len(chosen):
            continue
        used, remapped = np.unique(chosen, return_inverse=True)
        mesh = triangle_mesh("Reference / " + name, xyz[used], remapped.reshape(-1, 3))
        color(mesh, rgb[used].astype(float) / 255)
        obj = bpy.data.objects.new("REFERENCE / " + name, mesh)
        reference.objects.link(obj)
        obj.data.materials.append(material)
        obj.hide_select = True
        obj["reference_only"] = True
        obj["geometry_sha256"] = metadata["layers_sha256"]
        inventory.append(dict(name=name, vertices=len(used), faces=len(chosen)))
    if not inventory:
        raise ValueError("Reference display is empty")
    bake_camera(scene, cache, t, plan["image_size"])
    scene.camera.name = "SOURCE_CAMERA - interpolated estimates"
    before = camera_check(scene, cache, t, plan["image_size"], {})
    for source_id in plan["comparison_source_frames"]:
        scene.timeline_markers.new(f"source_{source_id:06d}", frame=source_id + 1)
    scene.frame_set(1)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = True
    scene.world = bpy.data.worlds.new("Diagnostic background")
    reference.hide_render = True
    out.mkdir(parents=True, exist_ok=False)
    source_out = out / "source_views"
    source_out.mkdir()
    with np.load(ROOT / ref["inputs"], allow_pickle=False) as z:
        for source_id in plan["comparison_source_frames"]:
            index = int(np.flatnonzero(z["frame_indices"] == source_id)[0])
            save_rgb(source_out / f"source_{source_id:06d}.png", z["rgb"][index])
    blend = out / "reference_setup.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    scene = bpy.context.scene
    after = camera_check(scene, cache, t, plan["image_size"], {})
    reference = bpy.data.collections["REFERENCE_ONLY - hide for authored-room delivery"]
    render_paths = []
    if args.render_checks:
        reference.hide_render = False
        scene.render.resolution_percentage = 50
        try:
            for source_id in (0, 146, 302):
                scene.frame_set(source_id + 1)
                target = out / f"reference_source_{source_id:06d}.png"
                scene.render.filepath = str(target)
                bpy.ops.render.render(write_still=True)
                render_paths.append(target.name)
        finally:
            reference.hide_render = True
            scene.render.resolution_percentage = 100
    report = dict(schema_version=1, experiment_id=plan["experiment_id"],
                  status="reference imported; authored room empty; no acceptance",
                  blender_version=bpy.app.version_string,
                  blender_build_hash=bpy.app.build_hash.decode(),
                  script_sha256=digest(Path(__file__)), blend_sha256=digest(blend),
                  input_lock_sha256=digest(lock_path), camera_cache_sha256=digest(cache),
                  camera_before_save=before, camera_after_reopen=after,
                  inventory=inventory, source_frames=plan["comparison_source_frames"],
                  diagnostic_render_paths=render_paths,
                  display_policy="full eligible hybrid triangles" if args.include_context else "TSDF core-only diagnostic; full context retained in locked input",
                  excluded_layers=["person", "geometry_invalid"],
                  reference_hidden_from_delivery_render=True,
                  transform_policy="display vertices and camera poses already aligned; no extra world transform",
                  limitations=["No scene authored", "No independent source-fidelity acceptance", "Scale uncalibrated", "Sparse-camera interpolation estimated"])
    (out / "import_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("OFFICE48_REFERENCE_IMPORT_OK", blend)


if __name__ == "__main__":
    main()
