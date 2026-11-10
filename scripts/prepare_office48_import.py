"""Validate locked office48 inputs and prepare an upstream-compatible camera cache."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "third_party/aha-3d/src"))
from aha3d.config import timing
from aha3d.workflow.camera import interpolate
from aha3d.workflow.preflight import camera_report


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New directory relative to project root")
    args = parser.parse_args()
    subprocess.run([sys.executable, str(ROOT / "scripts/check_office48_inputs.py")], check=True)
    spec = json.loads((ROOT / "configs/office48_static_baseline_v1.json").read_text())
    lock_path = ROOT / spec["input_lock"]
    source = json.loads((ROOT / spec["reference"]["input_manifest"]).read_text())
    camera_path = ROOT / spec["reference"]["cameras"]
    cameras = json.loads(camera_path.read_text())
    t = timing(dict(fps="30", frames=303, start=1))
    times = np.arange(t["frames"], dtype=float) / 30
    data, held = interpolate(cameras, times, source["processed_size_wh"], [1280, 720], "error")
    report = camera_report(data, t, [1280, 720], tolerance_px=2.0)
    if report["status"] != "passed" or held:
        raise ValueError(f"Camera representation needs investigation: {report}")
    # Check exact native observations independently of Blender and interpolation.
    ids = np.asarray(source["frame_indices"])
    native = np.asarray([f["c2w"] for f in cameras["frames"]])
    # Pi3X rotations have small floating-point orthogonality errors. SLERP
    # normalizes them; compare against independently projected proper rotations.
    u, _, vh = np.linalg.svd(native[:, :3, :3])
    normalized_native = native.copy()
    normalized_native[:, :3, :3] = u @ vh
    native_k = np.asarray([f["intrinsics"] for f in cameras["frames"]])
    expected_k = native_k.copy()
    expected_k[:, :2, 2] += .5
    expected_k[:, 0, :] *= 1280 / source["processed_size_wh"][0]
    expected_k[:, 1, :] *= 720 / source["processed_size_wh"][1]
    if not np.allclose(data["c2w"][ids], normalized_native, atol=1e-7, rtol=0):
        raise ValueError("Interpolation changed native camera poses")
    if not np.allclose(data["K"][ids], expected_k, atol=1e-7, rtol=0):
        raise ValueError("Native intrinsics/pixel-center conversion mismatch")
    out = (ROOT / args.out).resolve()
    out.relative_to(ROOT)
    out.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(out / "camera.npz", **data)
    report.update(native_keyframes_checked=len(ids), native_pose_max_error=float(np.max(np.abs(data["c2w"][ids]-native))),
                  native_rotation_policy="SLERP normalizes near-orthogonal source rotations; independently checked against SVD projection",
                  interpolation="upstream PCHIP translation, SLERP rotation, linear intrinsics",
                  endpoint="error; no extrapolation", source_frame_to_blender="source_frame + 1",
                  source_observations_are_estimates=True, held_samples=held,
                  pixels="boundary centers: add 0.5 to integer-index principal point BEFORE resize",
                  world_transform=cameras["world_transform"], camera_input_sha256=sha256(camera_path))
    (out / "camera_preflight.json").write_text(json.dumps(report, indent=2) + "\n")
    plan = dict(schema_version=1, experiment_id=spec["experiment_id"],
                input_lock=spec["input_lock"], input_lock_sha256=sha256(lock_path),
                reference=spec["reference"], timing=t, image_size=[1280, 720],
                comparison_source_frames=spec["timing"]["comparison_source_frames"],
                camera_sha256=sha256(out / "camera.npz"),
                limitation="Diagnostic reference setup only; no authored room or acceptance",
                preparation_script_sha256=sha256(Path(__file__)))
    (out / "import_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(f"CAMERA_PREPARED: {out.relative_to(ROOT)}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
