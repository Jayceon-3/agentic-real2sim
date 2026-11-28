"""Audit a furniture hierarchy in Blender and optionally run a controlled correction."""

import argparse
import importlib.util
from itertools import product
import json
import math
from pathlib import Path
import sys
import time

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector


def resolve_object(scene, selector):
    matches = [obj for obj in scene.objects if obj.get("instance_id") == selector]
    if len(matches) > 1:
        raise ValueError(f"Ambiguous instance ID: {selector}")
    obj = matches[0] if matches else scene.objects.get(selector)
    if obj is None:
        raise ValueError(f"No object with instance ID or name {selector!r}")
    return obj


def mesh_bounds(root, bounds):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return bounds([obj.evaluated_get(depsgraph) for obj in [root, *root.children_recursive]
                   if obj.type == "MESH"])


def measure(target, support, bounds):
    bpy.context.view_layer.update()
    box = mesh_bounds(target, bounds)
    matrix = target.matrix_world.copy()
    basis = matrix.to_3x3()
    lengths = [column.length for column in basis.col]
    if min(lengths) <= 1e-8:
        raise ValueError("Object world transform has a degenerate axis")
    axes = [column.normalized() for column in basis.col]
    return {
        "world_aabb": box,
        "location_world": list(matrix.translation),
        "rotation_world_xyz_degrees": [math.degrees(x) for x in matrix.to_euler("XYZ")],
        "scale_local": list(target.scale),
        "world_axis_lengths": lengths,
        "matrix_world": [list(row) for row in matrix],
        "world_basis_determinant": basis.determinant(),
        "max_normalized_axis_dot": max(abs(axes[i].dot(axes[j]))
                                       for i, j in ((0, 1), (0, 2), (1, 2))),
        "support_top_z": support,
        "support_clearance_z": box["min"][2] - support if support is not None else None,
    }


def set_clearance(target, measured, clearance):
    matrix = target.matrix_world.copy()
    matrix.translation += Vector((0, 0, clearance - measured["support_clearance_z"]))
    target.matrix_world = matrix


def scale_about_origin(target, factor):
    target.matrix_world = target.matrix_world @ Matrix.Diagonal((factor, factor, factor, 1))


def projected_box(scene, camera, box, raster):
    corners = [world_to_camera_view(scene, camera, Vector(point))
               for point in product(*zip(box["min"], box["max"]))]
    if any(point.z <= 0 for point in corners):
        raise ValueError(f"The target bounds cross the camera plane at frame {scene.frame_current}")
    width, height = raster
    xs = [point.x * width for point in corners]
    ys = [(1 - point.y) * height for point in corners]
    return [min(xs), min(ys), max(xs), max(ys)]


def controlled_demo(scene, target, support_top, bounds, original, scale, lift, frames):
    target_family = [target, *target.children_recursive]
    parent = target.parent
    while parent is not None:
        target_family.append(parent)
        parent = parent.parent
    if any(obj.constraints or obj.animation_data for obj in target_family):
        raise ValueError("The controlled demo needs a static, unconstrained target hierarchy")
    saved_matrix = target.matrix_world.copy()
    saved_frame = scene.frame_current
    reference_height = original["world_aabb"]["dimensions"][2]
    reference_clearance = original["support_clearance_z"]
    if reference_height <= 1e-8:
        raise ValueError("The target must have positive vertical extent")
    started = time.perf_counter()
    try:
        scale_about_origin(target, scale)
        set_clearance(target, measure(target, support_top, bounds), reference_clearance + lift)
        perturbed = measure(target, support_top, bounds)
        fitted_scale = reference_height / perturbed["world_aabb"]["dimensions"][2]
        scale_about_origin(target, fitted_scale)
        scaled = measure(target, support_top, bounds)
        z_correction = reference_clearance - scaled["support_clearance_z"]
        set_clearance(target, scaled, reference_clearance)
        corrected = measure(target, support_top, bounds)
        correction_seconds = time.perf_counter() - started

        settings = scene.render
        raster = [settings.resolution_x * settings.resolution_percentage // 100,
                  settings.resolution_y * settings.resolution_percentage // 100]
        views = []
        for frame in frames:
            scene.frame_set(frame)
            camera = scene.camera.evaluated_get(bpy.context.evaluated_depsgraph_get())
            boxes = [projected_box(scene, camera, sample["world_aabb"], raster)
                     for sample in (original, perturbed, corrected)]
            views.append({
                "blender_frame": frame,
                "reference_xyxy_px": boxes[0],
                "perturbed_xyxy_px": boxes[1],
                "corrected_xyxy_px": boxes[2],
                "perturbed_mean_edge_error_px": sum(abs(a-b) for a, b in zip(boxes[0], boxes[1])) / 4,
                "corrected_mean_edge_error_px": sum(abs(a-b) for a, b in zip(boxes[0], boxes[2])) / 4,
            })
        return {
            "injected_uniform_scale": scale,
            "injected_clearance_delta_z": lift,
            "fitted_uniform_scale": fitted_scale,
            "world_z_correction_after_scaling": z_correction,
            "reference_height": reference_height,
            "reference_clearance_z": reference_clearance,
            "perturbed": perturbed,
            "corrected": corrected,
            "correction_seconds": correction_seconds,
            "evaluation_raster_wh": raster,
            "evaluation_projected_box_views": views,
        }
    finally:
        scene.frame_set(saved_frame)
        target.matrix_world = saved_matrix
        bpy.context.view_layer.update()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--object", required=True, help="Semantic instance ID or exact Blender object name")
    parser.add_argument("--support", help="Instance ID or name of the horizontal support surface")
    parser.add_argument("--out", type=Path, required=True, help="New JSON report path")
    parser.add_argument("--demo", action="store_true", help="Inject and correct a known scale and height error in memory")
    parser.add_argument("--scale-factor", type=float, default=1.08)
    parser.add_argument("--lift-z", type=float, default=0.10)
    parser.add_argument("--eval-blender-frames", type=int, nargs="+", default=[])
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(arguments)
    if args.out.exists():
        parser.error("--out must be a new report path")
    if args.demo and (not args.support or not math.isfinite(args.scale_factor)
                      or args.scale_factor <= 0 or not math.isfinite(args.lift_z)):
        parser.error("--demo requires --support, a finite positive scale factor and a finite lift")
    if args.eval_blender_frames and not args.demo:
        parser.error("--eval-blender-frames requires --demo")

    importer_path = Path(__file__).resolve().parent / "sam3d_objects" / "import_blender.py"
    spec = importlib.util.spec_from_file_location("sam3d_importer", importer_path)
    importer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(importer)

    start = time.perf_counter()
    source_hash = importer.digest(args.scene)
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()), load_ui=False, use_scripts=False)
    scene = bpy.context.scene
    target = resolve_object(scene, args.object)
    support = resolve_object(scene, args.support) if args.support else None
    if support is not None and support in [target, *target.children_recursive]:
        raise ValueError("Support must belong to a separate object hierarchy")
    if args.eval_blender_frames and (scene.camera is None or len(set(args.eval_blender_frames)) != len(args.eval_blender_frames)
                                   or any(not scene.frame_start <= frame <= scene.frame_end
                                          for frame in args.eval_blender_frames)):
        raise ValueError("Evaluation requires a camera and unique frames in the scene timeline")
    support_top = mesh_bounds(support, importer.bounds)["max"][2] if support is not None else None
    original = measure(target, support_top, importer.bounds)
    report = {
        "schema_version": 1,
        "scene": {"path": str(args.scene), "sha256": source_hash},
        "blender_version": bpy.app.version_string,
        "scene_units": {"system": scene.unit_settings.system, "scale_length": scene.unit_settings.scale_length},
        "bounds_units": "Blender scene units",
        "object": {"name": target.name, "instance_id": target.get("instance_id")},
        "support": support.name if support is not None else None,
        "measurement_blender_frame": scene.frame_current,
        "original": original,
    }
    if args.demo:
        report["demo"] = controlled_demo(scene, target, support_top, importer.bounds, original,
                                         args.scale_factor, args.lift_z, args.eval_blender_frames)
    if importer.digest(args.scene) != source_hash:
        raise ValueError("Source scene changed while it was being audited")
    report["wall_seconds"] = time.perf_counter() - start
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
