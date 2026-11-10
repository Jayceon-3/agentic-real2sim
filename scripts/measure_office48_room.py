"""Source-linked architecture estimates from locked geometry; no authored example."""
import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=False)
    cameras = json.loads((ROOT / "outputs/office48-reference/alignment/cameras.json").read_text())
    by_frame = {f["source_frame"]: f for f in cameras["frames"]}
    landmarks = json.loads((ROOT / "configs/office48_structure_landmarks_v1.json").read_text())
    observations = []
    for item in landmarks["landmarks"]:
        f = by_frame[item["source_frame"]]
        pose, k = np.asarray(f["c2w"]), np.asarray(f["intrinsics"])
        ray = pose[:3, :3] @ np.linalg.solve(k, [*item["pixel_xy"], 1])
        axis = item["plane_axis"]
        distance = (item["plane_coordinate"] - pose[axis, 3]) / ray[axis]
        if distance <= 0:
            raise ValueError("Landmark intersection behind camera")
        point = pose[:3, 3] + distance * ray
        observations.append(dict(item, world_xyz=point.tolist(), method="source ray intersected with fitted constant-axis wall approximation"))
    with np.load(ROOT / "outputs/office48-reference/mesh/layers.npz", allow_pickle=False) as z:
        p, rgb = z["vertices"], z["colors"]
        good = z["measurement_valid"] & (z["layer"] == 0)
        selected = good & (p[:, 1] > 1.9) & (p[:, 1] < 4.05) & (p[:, 2] > 2.6) & (rgb.mean(axis=1) > 110)
        q = p[selected]
        guess = 3.98 - .66 * np.abs(q[:, 0] + .42)
        q = q[np.abs(q[:, 2] - guess) < .12]
        roofs = {}
        for side, mask in [("left", q[:, 0] < -.65), ("right", q[:, 0] > -.2)]:
            values = q[mask][::10]
            a = np.c_[values[:, :2], np.ones(len(values))]
            coeff = np.linalg.lstsq(a, values[:, 2], rcond=None)[0]
            for _ in range(4):
                inliers = np.abs(a @ coeff - values[:, 2]) < .035
                coeff = np.linalg.lstsq(a[inliers], values[inliers, 2], rcond=None)[0]
            roofs[side] = dict(z_equals_ax_by_c=coeff.tolist(), fitted_points=int(inliers.sum()), median_residual_predicted_m=float(np.median(np.abs(a @ coeff - values[:, 2]))))
        measured_bounds = np.quantile(p[good], [.01, .99], axis=0).tolist()
    result = dict(schema_version=1, units="uncalibrated predicted metres", world_basis="locked alignment/cameras.json", observations=observations,
                  roofs=roofs, static_point_quantile_bounds=measured_bounds,
                  wall_approximations=dict(x_left=-2.265, x_right=1.452, y_back=4.24, floor_z=0),
                  assumptions=["Wall planes made orthogonal at representative height; original plane deviations retained in alignment report", "Floor remains source-derived Z=0 hypothesis", "Unseen entry-side room extent is a completion, not measured geometry"],
                  acceptance="measurement estimates only; source-view authored-room review pending")
    (out / "measurements.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
