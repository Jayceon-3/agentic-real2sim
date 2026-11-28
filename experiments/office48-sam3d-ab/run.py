#!/usr/bin/env python3
"""Prepare, freeze, generate and score the Office48 object replacement experiment."""
import argparse
from collections import Counter
import csv
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
import traceback

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source(root, value):
    path = (root / value).resolve()
    path.relative_to(root.resolve())
    return path


def binary(path, size):
    with Image.open(path) as image:
        if image.mode != "L" or list(image.size) != size:
            raise ValueError(f"Expected an L-mode mask at {size}: {path}")
        data = np.array(image)
    if not np.isin(data, [0, 255]).all():
        raise ValueError(f"Expected only 0 and 255 mask values: {path}")
    return data > 0


def frame_name(frame):
    return f"frame_{frame:06d}.png"


def validate_manifest(config):
    if config["schema_version"] != 1 or config["seeds"] != [42, 43, 44]:
        raise ValueError("Expected schema 1 and preregistered seeds [42, 43, 44]")
    if (config["image_size"] != [1280, 720] or config["frame_count"] != 303
            or config["fps"] != 30):
        raise ValueError("This protocol expects the locked 303-frame, 30-fps Office48 clip")
    expected = {"cabinet": "furniture/cabinet", "chair": "furniture/chair-guest-1"}
    if Counter(o["id"] for o in config["objects"]) != Counter(expected.keys()):
        raise ValueError("Expected exactly one cabinet and one chair")
    for obj in config["objects"]:
        if obj["instance_id"] != expected[obj["id"]] or not obj["identity_review"].strip():
            raise ValueError("Confirm the exact source-to-scene object identity in identity_review")
        if Counter(v["role"] for v in obj["views"]) != {"generation": 1, "alignment": 2, "evaluation": 3}:
            raise ValueError("Each object needs one generation, two alignment and three evaluation views")
        frames = [v["frame"] for v in obj["views"]]
        if any(type(f) is not int or not 0 <= f < config["frame_count"] for f in frames):
            raise ValueError("Select zero-based source frame indices in [0, 302]")
        if len(set(frames)) != len(frames):
            raise ValueError("An object's generation, alignment and evaluation frames must be disjoint")
        if any(v["reviewed"] is not True for v in obj["views"]):
            raise ValueError("Review every mask before freezing")


def extract(args):
    """Decode by frame index, preserving the original raster and temporal indexing."""
    if args.manifest:
        config = read(args.manifest)
        args.frames = [v["frame"] for o in config["objects"] for v in o["views"]]
        args.video = config["video"]
    if not args.frames or any(type(f) is not int for f in args.frames):
        raise ValueError("Fill in selected integer frame indices before extraction")
    video = source(args.root, args.video)
    if not video.is_file() or any(not 0 <= f <= 302 for f in args.frames):
        raise ValueError("Use the Office48 video and frame indices in [0, 302]")
    args.out.mkdir(parents=True, exist_ok=False)
    receipt = {"status": "running", "video_sha256": digest(video), "frames": {}}
    write(args.out / "frames.json", receipt)
    try:
        for frame in sorted(set(args.frames)):
            path = args.out / frame_name(frame)
            # Start each single-image output at timestamp zero after selecting the source frame.
            select_frame = f"select=eq(n\\,{frame}),setpts=PTS-STARTPTS"
            command = [args.ffmpeg, "-nostdin", "-v", "error", "-i", str(video),
                       "-vf", select_frame, "-frames:v", "1", str(path)]
            subprocess.run(command, check=True)
            with Image.open(path) as image:
                if image.size != (1280, 720):
                    raise ValueError("Unexpected source raster; do not resize or crop extraction")
            receipt["frames"][str(frame)] = {"sha256": digest(path), "command": command}
            write(args.out / "frames.json", receipt)
        if digest(video) != receipt["video_sha256"]:
            raise ValueError("Video changed during extraction")
        receipt["status"] = "completed"
    except BaseException:
        receipt["status"] = "failed_or_interrupted"
        raise
    finally:
        write(args.out / "frames.json", receipt)


def freeze(args):
    config = read(args.manifest)
    validate_manifest(config)
    root = args.root.resolve()
    resources = {key: {"path": source(root, config[key]).relative_to(root).as_posix(),
                       "sha256": digest(source(root, config[key]))}
                 for key in ("video", "scene", "camera")}
    if resources["video"]["sha256"] != config["video_sha256"]:
        raise ValueError("Video differs from the preregistered Office48 input")
    frames_dir = source(args.root, config["frames_dir"])
    extracted = read(frames_dir / "frames.json")
    if extracted["status"] != "completed" or extracted["video_sha256"] != resources["video"]["sha256"]:
        raise ValueError("Extract frames from this video with the extract command first")
    # Validate the entire batch before creating a frozen directory.
    identities = {}
    for obj in config["objects"]:
        for view in obj["views"]:
            rgb = frames_dir / frame_name(view["frame"])
            if digest(rgb) != extracted["frames"][str(view["frame"])]["sha256"]:
                raise ValueError("Extracted RGB changed")
            mask = binary(source(args.root, view["mask"]), config["image_size"])
            ignored = (binary(source(args.root, view["ignore"]), config["image_size"])
                       if view.get("ignore") else np.zeros_like(mask))
            if not (mask & ~ignored).any():
                raise ValueError("Target mask must contain foreground outside the ignore region")
            for original in [rgb, source(args.root, view["mask"])]:
                identities[original] = digest(original)
            if view.get("ignore"):
                original = source(args.root, view["ignore"])
                identities[original] = digest(original)
    args.out.mkdir(parents=True, exist_ok=False)
    lock = {"schema_version": 1, "status": "freezing", "protocol": config,
            "resources": resources, "files": {}, "objects": [],
            "manifest_sha256": digest(args.manifest), "runner_sha256": digest(__file__)}
    write(args.out / "lock.json", lock)
    for obj in config["objects"]:
        entry = {k: v for k, v in obj.items() if k != "views"}
        entry["views"] = []
        for index, view in enumerate(obj["views"]):
            item = {"role": view["role"], "frame": view["frame"]}
            paths = {"image": frames_dir / frame_name(view["frame"]),
                     "mask": source(args.root, view["mask"])}
            if view.get("ignore"):
                paths["ignore"] = source(args.root, view["ignore"])
            for key, original in paths.items():
                relative = f"inputs/{obj['id']}/{index:02d}-{key}.png"
                destination = args.out / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, destination)
                lock["files"][relative] = digest(destination)
                if lock["files"][relative] != identities[original]:
                    raise ValueError("Input changed while freezing; keep this incomplete snapshot and use a new directory")
                item[key] = relative
            entry["views"].append(item)
        lock["objects"].append(entry)
    shutil.copyfile(args.manifest, args.out / "manifest.json")
    shutil.copyfile(frames_dir / "frames.json", args.out / "extraction.json")
    if digest(args.manifest) != lock["manifest_sha256"]:
        raise ValueError("Manifest changed while freezing")
    lock["status"] = "frozen"
    write(args.out / "lock.json", lock)
    print(f"FROZEN {args.out / 'lock.json'}")


def load_lock(path, root, verify_resources=True):
    lock = read(path)
    if lock["status"] != "frozen":
        raise ValueError("Expected a completed frozen lock")
    for name, sha in lock["files"].items():
        if digest(path.parent / name) != sha:
            raise ValueError(f"Frozen input changed: {name}")
    if verify_resources:
        for resource in lock["resources"].values():
            if digest(source(root, resource["path"])) != resource["sha256"]:
                raise ValueError(f"Source resource changed: {resource['path']}")
    return lock


def wrapper_module():
    path = ROOT / "scripts/sam3d_objects/infer.py"
    spec = importlib.util.spec_from_file_location("office48_sam3d_infer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def requests(lock):
    for seed in lock["protocol"]["seeds"]:
        for obj in lock["objects"]:
            yield obj, seed, next(v for v in obj["views"] if v["role"] == "generation")


def generate(args):
    lock = load_lock(args.lock, args.root)
    wrapper = wrapper_module()
    args.out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(args.lock, args.out / "lock.snapshot.json")
    shutil.copyfile(__file__, args.out / "runner_snapshot.py")
    session = wrapper.InferenceSession()
    started = time.perf_counter()
    report = {"status": "running", "mode": "validate_only" if args.validate_only else "resident_reuse",
              "lock_sha256": digest(args.lock), "pid": os.getpid(), "requests": [],
              "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
              "quality_acceptance": "not_assessed"}
    write(args.out / "batch.json", report)
    try:
        for obj, seed, view in requests(lock):
            if digest(args.lock) != report["lock_sha256"]:
                raise ValueError("Lock changed during generation")
            load_lock(args.lock, args.root, verify_resources=False)
            name = f"{obj['id']}/seed-{seed}"
            row = {"name": name, "object": obj["id"], "seed": seed, "status": "running"}
            report["requests"].append(row)
            write(args.out / "batch.json", report)
            argv = ["--image", str(args.lock.parent / view["image"]),
                    "--mask", str(args.lock.parent / view["mask"]),
                    "--upstream", str(args.upstream), "--checkpoint", str(args.checkpoint),
                    "--object-id", obj["instance_id"], "--seed", str(seed),
                    "--out", str(args.out / name), "--events"]
            if args.cuda_home:
                argv += ["--cuda-home", str(args.cuda_home)]
            metadata = args.out / f"{obj['id']}-seed-{seed}-source.json"
            write(metadata, {"source_video_sha256": lock["resources"]["video"]["sha256"],
                             "source_frame": view["frame"], "source_frame_indexing": "zero_based",
                             "object_id": obj["instance_id"], "lock_sha256": report["lock_sha256"],
                             "mask_review": "approved_in_frozen_manifest"})
            argv += ["--input-metadata", str(metadata)]
            if args.validate_only:
                argv += ["--validate-only"]
            before = time.perf_counter()
            result = wrapper.run(wrapper.arguments(argv), session=session)
            if result != 0:
                raise RuntimeError(f"Wrapper failed: {name}")
            if not args.validate_only:
                import torch
                gc.collect()
                torch.cuda.synchronize()
                request_report = read(args.out / name / "report.json")
                expected_reuse = len(report["requests"]) > 1
                if request_report["session"]["reused"] != expected_reuse:
                    raise RuntimeError("Unexpected model reuse state")
                row.update(reused=expected_reuse,
                           torch_allocated_after_cleanup_bytes=torch.cuda.memory_allocated(),
                           torch_reserved_after_cleanup_bytes=torch.cuda.memory_reserved())
            row.update(status="validated_only" if args.validate_only else "completed",
                       wall_with_cleanup_seconds=time.perf_counter() - before)
            write(args.out / "batch.json", report)
        report["status"] = "validated_only" if args.validate_only else "completed"
    except BaseException:
        report["status"] = "failed_or_interrupted"
        if report["requests"] and report["requests"][-1]["status"] == "running":
            report["requests"][-1]["status"] = "failed_or_interrupted"
        (args.out / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        report["total_wall_seconds"] = time.perf_counter() - started
        report["timing_scope"] = "Batch entry after preflight through request cleanup; includes model initialization; excludes queue and process startup."
        write(args.out / "batch.json", report)


def score(args):
    lock = load_lock(args.lock, args.root)
    render = read(args.renders / "render.json")
    if render["status"] != "completed" or render["lock_sha256"] != digest(args.lock):
        raise ValueError("Render is incomplete or belongs to a different lock")
    obj = next(o for o in lock["objects"] if o["id"] == render["object"])
    expected = {v["frame"]: v for v in obj["views"] if v["role"] == render["role"]}
    if (len(render["views"]) != len(expected)
            or {v["frame"] for v in render["views"]} != set(expected)):
        raise ValueError("Render must contain every preregistered view exactly once")
    rows = []
    for view in render["views"]:
        mask_path = args.renders / view["mask"]
        if digest(mask_path) != view["mask_sha256"]:
            raise ValueError("Rendered mask changed after rendering")
        reference = expected[view["frame"]]
        size = lock["protocol"]["image_size"]
        gt = binary(args.lock.parent / reference["mask"], size)
        predicted = binary(mask_path, size)
        valid = (~binary(args.lock.parent / reference["ignore"], size)
                 if reference.get("ignore") else np.ones_like(gt))
        intersection = int((gt & predicted & valid).sum())
        union = int(((gt | predicted) & valid).sum())
        if not (gt & valid).any():
            raise ValueError("No visible target in the scored region")
        rows.append({"frame": view["frame"], "intersection": intersection,
                     "union": union, "iou": intersection / union})
    args.out.mkdir(parents=True, exist_ok=False)
    write(args.out / "scores.json", {"object": obj["id"], "role": render["role"],
          "label": render["label"], "scene_sha256": render["scene_sha256"],
          "render_sha256": digest(args.renders / "render.json"), "lock_sha256": digest(args.lock),
          "mean_iou": statistics.mean(row["iou"] for row in rows), "views": rows})
    with (args.out / "per_view.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["frame", "intersection", "union", "iou"])
        writer.writeheader()
        writer.writerows(rows)


def summarize(args):
    scores = [read(path) for path in args.scores]
    if any(s["role"] != "evaluation" for s in scores) or len({s["lock_sha256"] for s in scores}) != 1:
        raise ValueError("Summarize evaluation scores from one frozen lock only")
    groups = {}
    seen = set()
    for item in scores:
        # Labels must distinguish independent A runs and preregistered B seeds.
        if not re.fullmatch(r"A-run-[123]|B-seed-(42|43|44)", item["label"]):
            raise ValueError("Use A-run-1/2/3 or B-seed-42/43/44 as render labels")
        identity = (item["object"], item["label"])
        if identity in seen:
            raise ValueError("Duplicate object/label; do not count repeated renders as new runs")
        seen.add(identity)
        groups.setdefault((item["object"], item["label"][0]), []).append(item["mean_iou"])
    args.out.mkdir(parents=True, exist_ok=False)
    rows = [{"object": obj, "method": method, "scored_runs": len(values), "planned_runs": 3,
             "mean_iou": statistics.mean(values),
             "sample_std_iou": statistics.stdev(values) if len(values) > 1 else None}
            for (obj, method), values in sorted(groups.items())]
    write(args.out / "summary.json", {"groups": rows, "inputs": [
          {"path": str(path), "sha256": digest(path)} for path in args.scores],
          "limitation": "Missing or failed runs are not scored; report their status and costs separately. B-only scores do not establish improvement over A."})
    with (args.out / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root for resource paths")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("extract", help="Extract selected source frames using ffmpeg")
    p.add_argument("--video", default="data/local/office48/source.mp4")
    selection = p.add_mutually_exclusive_group(required=True)
    selection.add_argument("--frames", nargs="+", type=int)
    selection.add_argument("--manifest", type=Path, help="Extract the frame indices selected in a draft manifest")
    p.add_argument("--ffmpeg", default="ffmpeg")
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(action=extract)
    p = sub.add_parser("freeze", help="Validate reviewed inputs and create a hash-bound snapshot")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(action=freeze)
    p = sub.add_parser("generate", help="Run all six requests in one model session")
    p.add_argument("--lock", type=Path, required=True)
    p.add_argument("--upstream", type=Path, required=True)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--cuda-home", type=Path)
    p.add_argument("--validate-only", action="store_true")
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(action=generate)
    p = sub.add_parser("score", help="Score a completed visible-mask render")
    p.add_argument("--lock", type=Path, required=True)
    p.add_argument("--renders", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(action=score)
    p = sub.add_parser("summarize", help="Aggregate per-run view means, keeping A and B separate")
    p.add_argument("--scores", nargs="+", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(action=summarize)
    args = parser.parse_args()
    args.root = args.root.resolve()
    for name in ("lock", "out", "manifest", "renders", "upstream", "checkpoint", "cuda_home"):
        if getattr(args, name, None) is not None:
            setattr(args, name, getattr(args, name).resolve())
    args.action(args)


if __name__ == "__main__":
    def terminate(signum, frame):
        raise KeyboardInterrupt(f"Received signal {signum}")
    signal.signal(signal.SIGTERM, terminate)
    main()
