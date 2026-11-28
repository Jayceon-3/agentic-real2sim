"""Build a controlled, 8%-oversized camera-center trace from public TUM ground truth."""

import argparse
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="New fixture directory")
    args = parser.parse_args()

    truth = np.loadtxt(args.ground_truth, usecols=(0, 1, 2, 3), ndmin=2)
    if len(truth) < 24 or not np.isfinite(truth).all():
        raise ValueError("Expected at least 24 finite ground-truth camera centers")
    row_indices = np.linspace(0, len(truth) - 1, 24, dtype=int)
    angle = np.deg2rad(23)
    c, s = np.cos(angle), np.sin(angle)
    rotation = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    scale = 1.08
    translation = np.array([0.2, -0.45, 0.3])
    cameras, mapping = [], []
    for frame, row in enumerate(truth[row_indices]):
        c2w = np.eye(4)
        c2w[:3, 3] = scale * (rotation @ row[1:]) + translation
        cameras.append({"source_frame": frame, "c2w": c2w.tolist()})
        mapping.append({"video_frame": frame, "tum_timestamp": float(row[0])})

    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "cameras.json").write_text(json.dumps({
        "kind": "controlled_tum_camera_centers_not_pi3x_predictions",
        "injected_scale": scale,
        "injected_world_rotation_degrees_z": 23,
        "injected_world_translation_m": translation.tolist(),
        "source_ground_truth_rows": row_indices.tolist(),
        "frames": cameras,
    }, indent=2) + "\n", encoding="utf-8")
    (args.out / "frames.json").write_text(json.dumps({"frames": mapping}, indent=2) + "\n",
                                         encoding="utf-8")


if __name__ == "__main__":
    main()
