"""Import one B asset or render one frozen A/B candidate in background Blender."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import time
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def owner(obj):
    while obj is not None:
        if obj.get("instance_id"):
            return obj["instance_id"]
        obj = obj.parent
    return None


def import_asset(args, lock, obj):
    path = ROOT / "scripts/sam3d_objects/import_blender.py"
    spec = importlib.util.spec_from_file_location("office48_importer", path)
    importer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(importer)
    placement = importer.load_placement(args.placement)
    if not all(math.isclose(s, placement["scale"][0], rel_tol=1e-8) for s in placement["scale"]):
        raise ValueError("The A/B protocol permits uniform scale only")
    if placement["semantic_class"] != obj["semantic_class"]:
        raise ValueError("Placement semantic_class differs from the frozen object")
    generation = args.glb.parent
    request, report = read(generation / "request.json"), read(generation / "report.json")
    metadata = read(generation / "inputs.json")["source_metadata"]
    artifacts = read(generation / "artifacts.json")
    if (report["status"] != "completed" or request["object_id"] != obj["instance_id"]
            or request["seed"] not in lock["protocol"]["seeds"]
            or metadata["lock_sha256"] != digest(args.lock)
            or digest(args.glb) != artifacts["object.glb"]["sha256"]):
        raise ValueError("GLB must be a completed B generation for this frozen object and lock")
    importer.run(SimpleNamespace(scene=args.root / lock["resources"]["scene"]["path"],
                 glb=args.glb, placement=args.placement, object_id=obj["instance_id"],
                 replace=True, out=args.out))
    write(args.out / "experiment.json", {"lock_sha256": digest(args.lock), "object": obj["id"],
          "seed": request["seed"], "condition": "B", "placement_sha256": digest(args.placement),
          "note": "Explicit placement; alignment and visual acceptance must be reviewed separately."})


def render(args, lock, obj):
    import bpy
    sys.path.insert(0, str(ROOT / "third_party/aha-3d/src"))
    from aha3d.blender.ensemble import camera_check

    args.out.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "object": obj["id"], "role": args.role, "label": args.label,
              "lock_sha256": digest(args.lock), "scene_sha256": digest(args.scene),
              "script_sha256": digest(__file__), "views": [], "samples": args.samples,
              "blender_version": bpy.app.version_string, "engine": "CYCLES", "device": getattr(args, "device", "CPU"),
              "mask_policy": "Object Index pass, ID 1, no mask antialiasing; full-room occlusion retained."}
    write(args.out / "render.json", report)
    started = time.perf_counter()
    try:
        bpy.ops.wm.open_mainfile(filepath=str(args.scene))
        scene = bpy.context.scene
        if scene.camera is None:
            raise ValueError("Saved candidate has no source camera")
        # Remove reference material from all view layers without changing saved scenes.
        reference = bpy.data.collections.get("REFERENCE_ONLY - hide for authored-room delivery")
        if reference:
            reference.hide_render = True
        targets = [o for o in scene.objects if owner(o) == obj["instance_id"]]
        if not any(o.type == "MESH" and not o.hide_render for o in targets):
            raise ValueError("Target semantic hierarchy has no renderable mesh")
        scene.render.resolution_x, scene.render.resolution_y = lock["protocol"]["image_size"]
        scene.render.resolution_percentage = 100
        scene.render.use_border = False
        scene.render.use_sequencer = False
        scene.render.engine = "CYCLES"
        device = getattr(args, "device", "CPU")
        if device == "CUDA":
            preferences = bpy.context.preferences.addons["cycles"].preferences
            preferences.compute_device_type = "CUDA"
            preferences.get_devices()
            available = [item for item in preferences.devices if item.type == "CUDA"]
            if not available:
                raise ValueError("No CUDA Cycles device is available")
            for item in preferences.devices:
                item.use = item.type == "CUDA"
            report["cuda_devices"] = [item.name for item in available]
            scene.cycles.device = "GPU"
        else:
            scene.cycles.device = "CPU"
        scene.cycles.samples = args.samples
        scene.cycles.use_denoising = False
        scene.cycles.seed = 0
        scene.render.film_transparent = False
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        scene.render.image_settings.color_depth = "8"
        timing = {"frames": 303, "fps": "30", "start": 1, "end": 303}
        report["camera_check"] = camera_check(scene, args.root / lock["resources"]["camera"]["path"],
                                              timing, lock["protocol"]["image_size"], {})
        # One view layer prevents duplicate file outputs and keeps RGB/mask geometry identical.
        layer = bpy.context.view_layer
        for other in scene.view_layers:
            other.use = other == layer
        layer.use_pass_object_index = True
        layer.update_render_passes()
        for item in scene.objects:
            item.pass_index = 1 if owner(item) == obj["instance_id"] else 0
        modern_compositor = hasattr(scene, "compositing_node_group")
        if modern_compositor:
            tree = bpy.data.node_groups.new("Office48 evaluation", "CompositorNodeTree")
            scene.compositing_node_group = tree
            tree.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
            composite = tree.nodes.new("NodeGroupOutput")
        else:
            scene.use_nodes = True
            tree = scene.node_tree
            tree.nodes.clear()
            composite = tree.nodes.new("CompositorNodeComposite")
        layers = tree.nodes.new("CompositorNodeRLayers")
        layers.scene = scene
        layers.layer = layer.name
        tree.links.new(layers.outputs["Image"], composite.inputs["Image"])
        mask = tree.nodes.new("CompositorNodeIDMask")
        if hasattr(mask, "index"):
            mask.index = 1
            mask.use_antialiasing = False
        else:
            mask.inputs["Index"].default_value = 1
            mask.inputs["Anti-Alias"].default_value = False
        index_pass = layers.outputs.get("Object Index") or layers.outputs.get("IndexOB")
        if index_pass is None:
            raise ValueError("Renderer did not expose the Object Index pass")
        tree.links.new(index_pass, mask.inputs[0])
        output = tree.nodes.new("CompositorNodeOutputFile")
        modern_output = hasattr(output, "file_output_items")
        if modern_output:
            output.file_output_items.new("FLOAT", "Mask")
            output.file_name = "mask"
            output.format.media_type = "IMAGE"
        output.format.file_format = "PNG"
        output.format.color_mode = "BW"
        output.format.color_depth = "8"
        # Masks are numeric data; do not apply the RGB scene's view transform.
        if hasattr(output, "save_as_render"):
            output.save_as_render = False
        else:
            output.file_slots[0].save_as_render = False
        tree.links.new(mask.outputs["Alpha"], output.inputs[0])
        scene.render.use_compositing = True
        for view in obj["views"]:
            if view["role"] != args.role:
                continue
            frame = view["frame"]
            scene.frame_set(frame + 1)
            prefix = f"source-{frame:06d}"
            rgb = args.out / (prefix + "-rgb.png")
            temporary = args.out / (prefix + "-mask-output")
            temporary.mkdir()
            if modern_output:
                output.directory = str(temporary)
            else:
                output.base_path = str(temporary)
                output.file_slots[0].path = "mask-"
            scene.render.filepath = str(rgb)
            bpy.ops.render.render(write_still=True)
            generated = list(temporary.rglob("*.png"))
            if len(generated) != 1:
                raise ValueError(f"Expected exactly one mask output, got {generated}")
            mask_path = args.out / (prefix + "-mask.png")
            generated[0].rename(mask_path)
            report["views"].append({"frame": frame, "blender_frame": frame + 1,
                                    "rgb": rgb.name, "rgb_sha256": digest(rgb),
                                    "mask": mask_path.name, "mask_sha256": digest(mask_path)})
            write(args.out / "render.json", report)
        if digest(args.scene) != report["scene_sha256"]:
            raise ValueError("Candidate scene changed during rendering")
        report["status"] = "completed"
    except BaseException:
        report["status"] = "failed_or_interrupted"
        (args.out / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        report["wall_seconds"] = time.perf_counter() - started
        write(args.out / "render.json", report)


def main():
    import bpy
    if not bpy.app.background:
        raise ValueError("Run in background Blender; save interactive alignment as a new candidate first")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--stage", choices=["import", "render"], required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--object", choices=["cabinet", "chair"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--glb", type=Path)
    parser.add_argument("--placement", type=Path)
    parser.add_argument("--scene", type=Path)
    parser.add_argument("--role", choices=["alignment", "evaluation"], default="evaluation")
    parser.add_argument("--label", help="B-seed-42/43/44 or A-run-1/2/3")
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--device", choices=["CPU", "CUDA"], default="CPU")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    for key in ("root", "lock", "out", "scene", "glb", "placement"):
        if getattr(args, key) is not None:
            setattr(args, key, getattr(args, key).resolve())
    lock = read(args.lock)
    if lock["status"] != "frozen":
        raise ValueError("Expected a frozen lock")
    for name, sha in lock["files"].items():
        if digest(args.lock.parent / name) != sha:
            raise ValueError(f"Frozen input changed: {name}")
    for resource in lock["resources"].values():
        if digest(args.root / resource["path"]) != resource["sha256"]:
            raise ValueError("Source scene, camera or video differs from the lock")
    obj = next(o for o in lock["objects"] if o["id"] == args.object)
    if args.stage == "import":
        if args.glb is None or args.placement is None:
            parser.error("import requires --glb and --placement")
        import_asset(args, lock, obj)
    else:
        if args.scene is None or args.label is None or args.samples < 1:
            parser.error("render requires --scene, --label and positive --samples")
        if not re.fullmatch(r"A-run-[123]|B-seed-(42|43|44)", args.label):
            parser.error("Use A-run-1/2/3 or B-seed-42/43/44 as the label")
        if args.role == "evaluation" and args.label.startswith("B-"):
            lineage = read(args.scene.parent / "experiment.json")
            imported = read(args.scene.parent / "import_report.json")
            if (lineage["lock_sha256"] != digest(args.lock) or lineage["object"] != obj["id"]
                    or args.label != f"B-seed-{lineage['seed']}"
                    or imported["output"]["sha256"] != digest(args.scene)):
                raise ValueError("B evaluation requires an unchanged final import for this object, seed and lock")
        render(args, lock, obj)


if __name__ == "__main__":
    main()
