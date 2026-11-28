"""Compare Pi3X camera centers with TUM ground truth using rigid and similarity fits."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def match_centers(cameras, frame_map, truth):
    by_frame = {entry.get("video_frame", index): entry["tum_timestamp"]
                for index, entry in enumerate(frame_map["frames"])}
    matches = []
    for frame in cameras["frames"]:
        index = frame["source_frame"]
        timestamp = by_frame[index]
        nearest = int(np.argmin(abs(truth[:, 0] - timestamp)))
        if abs(truth[nearest, 0] - timestamp) <= 0.02:
            estimated = np.asarray(frame["c2w"], dtype=float)[:3, 3]
            matches.append((index, nearest, estimated, truth[nearest, 1:4]))
    return matches


def fit_transform(estimated, reference):
    estimated_mean = estimated.mean(axis=0)
    reference_mean = reference.mean(axis=0)
    x = estimated - estimated_mean
    y = reference - reference_mean
    if min(np.linalg.matrix_rank(x), np.linalg.matrix_rank(y)) < 2:
        raise ValueError("Alignment needs at least three non-collinear fit camera centers")
    u, singular, vt = np.linalg.svd(y.T @ x / len(x))
    sign = np.ones(3)
    sign[-1] = np.sign(np.linalg.det(u @ vt))
    rotation = (u * sign) @ vt
    scale = float(singular @ sign / np.mean(np.sum(x**2, axis=1)))
    if scale <= 0:
        raise ValueError("The fitted scale must be positive")
    return rotation, scale, estimated_mean, reference_mean


def errors(estimated, reference, rotation, scale, estimated_mean, reference_mean):
    translation = reference_mean - scale * (rotation @ estimated_mean)
    distances = np.linalg.norm(scale * (estimated @ rotation.T) + translation - reference, axis=1)
    return {
        "translation_m": translation.tolist(),
        "rmse_m": float(np.sqrt(np.mean(distances**2))),
        "median_m": float(np.median(distances)),
        "max_m": float(np.max(distances)),
    }


def evaluate(cameras, frame_map, truth, holdout_every=None):
    matches = match_centers(cameras, frame_map, truth)
    if len(matches) < 3:
        raise ValueError("Fewer than three camera centers matched within 0.02 seconds")
    frames, truth_indices, estimated, reference = zip(*matches)
    estimated, reference = np.asarray(estimated), np.asarray(reference)
    fit = np.ones(len(frames), dtype=bool)
    if holdout_every is not None:
        # Split on truth keys to keep repeated associations on the same side.
        ranks = dict.fromkeys(truth_indices)
        heldout = {key for index, key in enumerate(ranks, start=1) if index % holdout_every == 0}
        fit = np.array([key not in heldout for key in truth_indices])
        if fit.sum() < 3 or fit.all():
            raise ValueError("The split needs at least three fit matches and a held-out match")
    evaluation = ~fit if holdout_every is not None else fit
    rotation, scale, x_mean, y_mean = fit_transform(estimated[fit], reference[fit])
    return {
        "schema_version": 1,
        "max_match_delta_seconds": 0.02,
        "matched_camera_count": len(frames),
        "reference_path_m": float(np.linalg.norm(np.diff(reference, axis=0), axis=1).sum()),
        "fit_source_frames": np.asarray(frames)[fit].tolist(),
        "evaluation_source_frames": np.asarray(frames)[evaluation].tolist(),
        "evaluation_is_holdout": holdout_every is not None,
        "gt_from_estimated_scale": scale,
        "estimated_scale_error_percent": 100 * (1 / scale - 1),
        "gt_from_estimated_rotation": rotation.tolist(),
        "rigid_ate": errors(estimated[evaluation], reference[evaluation], rotation, 1, x_mean, y_mean),
        "similarity_ate": errors(estimated[evaluation], reference[evaluation], rotation, scale, x_mean, y_mean),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cameras", type=Path)
    parser.add_argument("frame_map", type=Path)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument("--holdout-every", type=int, help="Reserve every Nth distinct matched truth timestamp")
    parser.add_argument("--out", type=Path, help="New JSON report path")
    args = parser.parse_args()
    if args.holdout_every is not None and args.holdout_every < 2:
        parser.error("--holdout-every must be at least two")

    truth = np.loadtxt(args.ground_truth, usecols=(0, 1, 2, 3), ndmin=2)
    if not len(truth) or not np.isfinite(truth).all():
        parser.error("Ground truth must contain finite timestamps and 3D centers")
    result = evaluate(json.loads(args.cameras.read_text()), json.loads(args.frame_map.read_text()),
                      truth, args.holdout_every)
    if args.out is not None:
        result["inputs"] = {}
        for key in ("cameras", "frame_map", "ground_truth"):
            path = getattr(args, key)
            with path.open("rb") as stream:
                result["inputs"][key] = {"path": str(path), "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")

    count = result["matched_camera_count"]
    path = result["reference_path_m"]
    scale = result["gt_from_estimated_scale"]
    ate = result["similarity_ate"]
    print(f"matched {count} cameras | GT path {path:.2f} m | Sim3 scale (GT/Pi3X) {scale:.3f}")
    print(f"ATE RMSE {ate['rmse_m']*100:.1f} cm | median {ate['median_m']*100:.1f} cm | max {ate['max_m']*100:.1f} cm")


if __name__ == "__main__":
    main()
