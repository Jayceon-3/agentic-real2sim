#!/usr/bin/env python3
"""Run one SAM 3D Objects image/mask request with durable artifacts and timings."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback


PROJECT = Path(__file__).resolve().parents[2]
PINNED_UPSTREAM = "f91db411c50efee93d8db7aeb323885650f6f722"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def git_identity(root):
    def git(*args):
        result = subprocess.run(["git", "-C", str(root), *args],
                                capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    return {"commit": git("rev-parse", "HEAD"),
            "tracked_status": git("status", "--porcelain", "--untracked-files=no")}


def arguments(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image", type=Path, required=True)
    p.add_argument("--mask", type=Path, required=True,
                   help="Single-channel foreground mask; values > threshold are foreground")
    p.add_argument("--checkpoint", type=Path, required=True,
                   help="pipeline.yaml or its containing directory, not a single weight file")
    p.add_argument("--upstream", type=Path, required=True, help="SAM 3D Objects source checkout")
    p.add_argument("--out", type=Path, required=True, help="New output directory; never overwritten")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--mask-threshold", type=int, default=0)
    p.add_argument("--cuda-home", type=Path,
                   help="Validated toolkit root; otherwise use existing CUDA_HOME")
    p.add_argument("--checkpoint-revision", help="User-supplied HF revision, recorded as a claim")
    p.add_argument("--object-id", default="object")
    p.add_argument("--input-metadata", type=Path,
                   help="Optional JSON with source video/frame/mask provenance")
    p.add_argument("--save-splat", action="store_true", help="Also export Gaussian PLY")
    p.add_argument("--validate-only", action="store_true",
                   help="Prepare inputs and provenance without importing Torch or loading weights")
    return p.parse_args(argv)


def prepare_inputs(args, out):
    import numpy as np
    from PIL import Image

    target = out / "inputs"
    target.mkdir()
    identities = {}
    for name, source in (("image", args.image), ("mask", args.mask)):
        destination = target / (name + source.suffix.lower())
        before = digest(source)
        shutil.copyfile(source, destination)
        if digest(destination) != before or digest(source) != before:
            raise ValueError(f"Input changed while copying: {source}")
        identities[name] = {"source": str(source), "copy": str(destination.relative_to(out)),
                            "sha256": before, "bytes": destination.stat().st_size}
    with Image.open(out / identities["image"]["copy"]) as im:
        image = np.array(im.convert("RGB"))
    with Image.open(out / identities["mask"]["copy"]) as im:
        mask_array = np.array(im)
    if mask_array.ndim != 2:
        raise ValueError("Mask must be single-channel (L/1); do not pass an RGB overlay")
    if mask_array.shape != image.shape[:2]:
        raise ValueError(f"Image/mask dimensions differ: {image.shape[:2]} vs {mask_array.shape}")
    if not np.isfinite(mask_array).all() or mask_array.min() < 0 or mask_array.max() > 255:
        raise ValueError("Mask values must be finite and in [0, 255]")
    mask = mask_array > args.mask_threshold
    if not mask.any():
        raise ValueError("Foreground mask is empty")
    Image.fromarray(mask.astype("uint8") * 255).save(target / "mask_binary.png")
    Image.fromarray(image).save(target / "image_rgb.png")
    overlay = image.astype("float32")
    overlay[mask] = overlay[mask] * 0.55 + np.array([40, 220, 120]) * 0.45
    Image.fromarray(overlay.astype("uint8")).save(target / "overlay.png")
    receipt = {"object_id": args.object_id, "files": identities,
               "width": image.shape[1], "height": image.shape[0],
               "mask_threshold": args.mask_threshold, "mask_pixels": int(mask.sum()),
               "mask_fraction": float(mask.mean()), "visual_mask_review": "not_recorded",
               "normalized_files": {name: digest(target / name) for name in
                                    ("image_rgb.png", "mask_binary.png", "overlay.png")}}
    if args.input_metadata:
        receipt["source_metadata"] = json.loads(args.input_metadata.read_text())
        receipt["source_metadata_sha256"] = digest(args.input_metadata)
    write_json(out / "inputs.json", receipt)
    return image, mask


def load_runtime(args, out):
    """Patch only a run-local copy, before any upstream imports can capture CUDA_HOME."""
    cuda_home = args.cuda_home or (Path(os.environ["CUDA_HOME"]) if os.environ.get("CUDA_HOME") else None)
    if cuda_home is None or not (cuda_home / "bin/nvcc").is_file():
        raise ValueError("Set --cuda-home to a toolkit containing bin/nvcc")
    cuda_home = cuda_home.resolve()
    os.environ["CUDA_HOME"] = str(cuda_home)
    os.environ["PATH"] = str(cuda_home / "bin") + os.pathsep + os.environ.get("PATH", "")
    os.environ["LIDRA_SKIP_INIT"] = "true"
    for variable in ("NVCC_PREPEND_FLAGS", "NVCC_APPEND_FLAGS"):
        if os.environ.get(variable):
            raise ValueError(f"Unset {variable} before running; use the validated Slurm setup")
    runtime = out / "runtime"
    runtime.mkdir()
    original = args.upstream / "notebook/inference.py"
    source = original.read_text()
    old = 'os.environ["CUDA_HOME"] = os.environ["CONDA_PREFIX"]'
    if source.count(old) != 1:
        raise ValueError("Unknown upstream CUDA initialization; inspect inference.py before adapting")
    patched = runtime / "inference_runtime.py"
    replacement = 'os.environ["CUDA_HOME"] = ' + repr(str(cuda_home))
    patched.write_text(source.replace(old, replacement, 1))
    write_json(runtime / "patch.json", {"original_sha256": digest(original),
               "patched_sha256": digest(patched), "old": old, "new": replacement,
               "cuda_home": str(cuda_home)})
    sys.path[:0] = [str(args.upstream / "notebook"), str(args.upstream)]
    spec = importlib.util.spec_from_file_location("sam3d_inference_runtime", patched)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def checkpoint_identity(config, revision):
    # Avoid hashing all multi-GB weights on every profiling request. This inventory
    # is not a cryptographic proof of model bytes; revision is explicitly a claim.
    files = [{"path": str(p.relative_to(config.parent)), "bytes": p.stat().st_size,
              "mtime_ns": p.stat().st_mtime_ns}
             for p in sorted(config.parent.rglob("*")) if p.is_file()]
    return {"config": str(config), "config_sha256": digest(config), "files": files,
            "revision": revision, "revision_binding": "user_asserted_not_verified",
            "weight_contents_hashed": False}


def run(args):
    started = time.perf_counter()
    for key in ("image", "mask", "checkpoint", "upstream", "out", "input_metadata", "cuda_home"):
        value = getattr(args, key)
        if value is not None:
            setattr(args, key, value.expanduser().resolve())
    if args.checkpoint.is_dir():
        args.checkpoint /= "pipeline.yaml"
    # Exclusive creation also prevents concurrent writers to a previous run.
    args.out.mkdir(parents=True, exist_ok=False)
    out = args.out
    report = {"schema_version": 1, "status": "running", "stage": "preflight",
              "started_at": datetime.now(timezone.utc).isoformat(), "timings_seconds": {},
              "timing_scope": "wrapper entry through final artifacts; excludes scheduler queue, "
                              "shell startup and final report serialization",
              "quality_acceptance": "not_assessed"}
    write_json(out / "report.json", report)
    try:
        if not 0 <= args.seed < 2**32:
            raise ValueError("Seed must be in [0, 2**32)")
        if not 0 <= args.mask_threshold <= 254:
            raise ValueError("Mask threshold must be in [0, 254]")
        for path in (args.image, args.mask, args.checkpoint, args.upstream / "notebook/inference.py"):
            if not path.is_file():
                raise FileNotFoundError(path)
        write_json(out / "request.json", {k: str(v) if isinstance(v, Path) else v
                                         for k, v in vars(args).items()})
        provenance = {"wrapper_sha256": digest(Path(__file__)),
                      "project": git_identity(PROJECT), "upstream": git_identity(args.upstream),
                      "validated_upstream_commit": PINNED_UPSTREAM,
                      "python": sys.version, "executable": sys.executable,
                      "packages": sorted({(d.metadata.get("Name") or "unknown", d.version)
                                          for d in metadata.distributions()}),
                      "slurm": {k: os.environ.get(k) for k in
                                ("SLURM_JOB_ID", "SLURM_JOB_PARTITION", "SLURM_JOB_NODELIST",
                                 "SLURM_CPUS_PER_TASK", "CUDA_VISIBLE_DEVICES")}}
        provenance["upstream_python_sha256"] = {
            str(p.relative_to(args.upstream)): digest(p)
            for directory in ("sam3d_objects", "notebook")
            for p in sorted((args.upstream / directory).rglob("*.py"))
        }
        write_json(out / "provenance.json", provenance)
        shutil.copyfile(__file__, out / "wrapper_snapshot.py")
        shutil.copytree(args.upstream / "notebook", out / "upstream_code",
                        ignore=shutil.ignore_patterns("images", "*.ipynb", "__pycache__"))
        write_json(out / "checkpoint.json", checkpoint_identity(args.checkpoint, args.checkpoint_revision))
        report["stage"] = "prepare_inputs"
        image, mask = prepare_inputs(args, out)
        report["timings_seconds"]["preparation"] = time.perf_counter() - started
        if args.validate_only:
            report.update(status="validated_only", stage="done")
            return 0

        report["stage"] = "runtime_import"
        write_json(out / "report.json", report)
        stage_start = time.perf_counter()
        runtime = load_runtime(args, out)
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable; execute inside a GPU allocation")
        torch.cuda.synchronize()
        report["timings_seconds"]["runtime_import"] = time.perf_counter() - stage_start
        report["gpu"] = {"name": torch.cuda.get_device_name(0),
                         "torch": torch.__version__, "torch_cuda": torch.version.cuda,
                         "total_memory_bytes": torch.cuda.get_device_properties(0).total_memory}
        report["cuda_home"] = os.environ["CUDA_HOME"]
        report["memory"] = {}

        def measure(name, action):
            report["stage"] = name
            write_json(out / "report.json", report)
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
            t = time.perf_counter()
            try:
                value = action()
                torch.cuda.synchronize()
            finally:
                report["timings_seconds"][name] = time.perf_counter() - t
                report["memory"][name] = {
                    "peak_torch_allocated_bytes": torch.cuda.max_memory_allocated(),
                    "peak_torch_reserved_bytes": torch.cuda.max_memory_reserved()}
                write_json(out / "report.json", report)
            return value

        model = measure("model_init", lambda: runtime.Inference(str(args.checkpoint), compile=False))
        result = measure("inference", lambda: model(image, mask, seed=args.seed))
        report["output_keys"] = sorted(result)

        def export():
            mesh = result.get("glb")
            if mesh is None or not callable(getattr(mesh, "export", None)):
                raise ValueError("No exportable glb mesh in model output")
            mesh.export(str(out / "object.glb"))
            if args.save_splat:
                result["gs"].save_ply(str(out / "splat.ply"))
            pose = {}
            for key in ("rotation", "translation", "scale"):
                if key not in result:
                    raise ValueError(f"Missing model placement field: {key}")
                value = result[key]
                pose[key] = value.detach().cpu().tolist() if torch.is_tensor(value) else value
            write_json(out / "pose.json", {
                "object_id": args.object_id, "model_output": pose,
                "applied_to_glb_by_wrapper": False,
                "coordinate_status": "native model/export conventions; not aligned to AHa-3D",
                "warning": "Do not apply these transforms blindly; audit exporter conventions first."})
            for name in ("object.glb", "pose.json") + (("splat.ply",) if args.save_splat else ()):
                if not (out / name).is_file() or (out / name).stat().st_size == 0:
                    raise ValueError(f"Missing or empty artifact: {name}")
        measure("export", export)
        report["stage"] = "artifact_receipt"
        names = ["object.glb", "pose.json"] + (["splat.ply"] if args.save_splat else [])
        write_json(out / "artifacts.json", {name: {"bytes": (out / name).stat().st_size,
                                                  "sha256": digest(out / name)} for name in names})
        report.update(status="completed", stage="done")
        print(f"SAM3D_COMPLETED {out}", flush=True)
        return 0
    except BaseException as error:
        report.update(status="failed", error_type=type(error).__name__, error=str(error))
        (out / "error.txt").write_text(traceback.format_exc())
        raise
    finally:
        report["timings_seconds"]["end_to_end"] = time.perf_counter() - started
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["memory_scope"] = ("PyTorch allocator only; excludes external CUDA allocations. "
                                  "Per-stage peaks include already resident model memory.")
        write_json(out / "report.json", report)


if __name__ == "__main__":
    try:
        raise SystemExit(run(arguments()))
    except Exception as error:
        print(f"SAM3D_FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
