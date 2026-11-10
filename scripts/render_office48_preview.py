"""Prepare and render a portable, explicitly unaccepted office48 review copy."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "third_party/aha-3d/src"))
from aha3d.blender.rendering import configure_render
from aha3d.blender.ensemble import camera_check


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def main():
    if not bpy.app.background:
        raise RuntimeError("Run in background Blender with a saved scene")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=["prepare", "render"], required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--engine", choices=["eevee", "cycles"], default="eevee")
    p.add_argument("--samples", type=int, default=32)
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = (ROOT / a.out).resolve()
    out.relative_to(ROOT)
    scene = bpy.context.scene
    source = Path(bpy.data.filepath)
    if not source.is_file():
        raise ValueError("Open the saved authored scene")
    cache = ROOT / "outputs/office48-baseline-001/inputs/camera-v001/camera.npz"
    timing = dict(frames=303, fps="30", start=1, end=303)
    camera = camera_check(scene, cache, timing, [1280, 720], {})
    if a.stage == "prepare":
        out.mkdir(parents=True, exist_ok=False)
        package = out / "package"
        package.mkdir()
        source_hash = digest(source)
        reference = bpy.data.collections.get("REFERENCE_ONLY - hide for authored-room delivery")
        if reference:
            for obj in list(reference.all_objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(reference)
        bpy.data.orphans_purge(do_recursive=True)
        exposure = scene.view_settings.exposure
        settings = configure_render(scene, "material", a.samples, a.engine, cycles_device="CPU")
        scene.view_settings.exposure = exposure
        scene.render.resolution_x, scene.render.resolution_y = 1280, 720
        scene.render.resolution_percentage = 100
        scene.frame_start, scene.frame_end = 1, 303
        scene.render.fps, scene.render.fps_base = 30, 1
        scene.render.filepath = "//renders/frame_"
        scene.frame_set(147)
        scene["delivery_status"] = "PRELIMINARY REVIEW COPY - NOT ACCEPTED"
        scene["review_note"] = "Source-fidelity repairs deferred by user; original findings remain open"
        scene["open_findings_json"] = json.dumps(["source-appearance-v006", "source-shape-review-v006"])
        bpy.ops.file.pack_all()
        target = package / "office48_preview.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(target))
        bpy.ops.wm.open_mainfile(filepath=str(target))
        scene = bpy.context.scene
        reopened = camera_check(scene, cache, timing, [1280, 720], {})
        external_images = [im.filepath for im in bpy.data.images if im.source == "FILE" and im.filepath and not im.packed_file]
        if bpy.data.libraries or external_images:
            raise ValueError("Preview scene still has external asset dependencies")
        keyframes = package / "keyframes"
        keyframes.mkdir()
        times = []
        for frame in [1, 147, 303]:
            scene.frame_set(frame)
            scene.render.filepath = str(keyframes / f"frame_{frame:04d}.png")
            started = time.monotonic()
            bpy.ops.render.render(write_still=True)
            times.append(dict(frame=frame, seconds=time.monotonic()-started))
        report = dict(status="preliminary; render-keyframe review required", source_scene_sha256=source_hash,
                      preview_scene_sha256=digest(target), scene="package/office48_preview.blend",
                      settings=settings, exposure=exposure, timing=timing, image_size=[1280, 720],
                      camera_before=camera, camera_after_reopen=reopened,
                      external_images=external_images, linked_libraries=0,
                      reference_geometry_removed=True, keyframe_times=times,
                      script_sha256=digest(Path(__file__)), blender_version=bpy.app.version_string,
                      final_baseline_accepted=False)
        (out / "scene_setup.json").write_text(json.dumps(report, indent=2)+"\n")
        print("PREVIEW_SCENE_PREPARED", target, flush=True)
        return
    setup = json.loads((out / "scene_setup.json").read_text())
    if digest(source) != setup["preview_scene_sha256"]:
        raise ValueError("Saved preview scene differs from prepared input")
    review_path = out / "keyframe_review.json"
    if not review_path.is_file() or json.loads(review_path.read_text()).get("technical_preview_usable") is not True:
        raise ValueError("Inspect representative preview frames before rendering the full clip")
    work = out / "work"
    work.mkdir(exist_ok=True)
    frames = work / "frames"
    frames.mkdir(exist_ok=False)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.compression = 15
    started = time.monotonic()
    durations = []
    for frame in range(1, 304):
        scene.frame_set(frame)
        scene.render.filepath = str(frames / f"{frame:04d}.png")
        t = time.monotonic()
        bpy.ops.render.render(write_still=True)
        durations.append(time.monotonic()-t)
        if frame == 1 or frame % 30 == 0 or frame == 303:
            print(f"PREVIEW_RENDER_PROGRESS {frame}/303 elapsed={time.monotonic()-started:.1f}s", flush=True)
    report = dict(status="frames rendered; encoding and full decode still required", frames=303,
                  fps=30, width=1280, height=720, scene_sha256=setup["preview_scene_sha256"],
                  settings=setup["settings"], render_seconds=time.monotonic()-started,
                  frame_render_seconds=durations, camera_check=camera, accepted=False)
    (out / "frame_render.json").write_text(json.dumps(report, indent=2)+"\n")
    print("PREVIEW_FRAMES_COMPLETE", out, flush=True)


if __name__ == "__main__":
    main()
