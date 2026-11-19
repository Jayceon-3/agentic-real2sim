"""Compare Pi3X camera centers with TUM ground truth: Sim(3) Umeyama alignment, ATE RMSE and scale."""
import sys, json, numpy as np
cams, frames_map, gt_path = sys.argv[1:4]
cams = json.load(open(cams)); fmap = json.load(open(frames_map))["frames"]
gt = np.array([[float(x) for x in l.split()] for l in open(gt_path) if not l.startswith("#")])
est, ref = [], []
for f in cams["frames"]:
    t = fmap[f["source_frame"]]["tum_timestamp"]
    j = np.argmin(abs(gt[:, 0] - t))
    if abs(gt[j, 0] - t) > 0.02: continue
    est.append(np.array(f["c2w"])[:3, 3]); ref.append(gt[j, 1:4])
X, Y = np.array(est).T, np.array(ref).T          # 3xN
mx, my = X.mean(1, keepdims=True), Y.mean(1, keepdims=True)
U, D, Vt = np.linalg.svd((Y - my) @ (X - mx).T / X.shape[1])
S = np.eye(3); S[2, 2] = np.sign(np.linalg.det(U @ Vt))
R = U @ S @ Vt; s = np.trace(np.diag(D) @ S) / ((X - mx) ** 2).sum(0).mean()
err = np.linalg.norm(s * R @ X + (my - s * R @ mx) - Y, axis=0)
path = np.linalg.norm(np.diff(Y, axis=1), axis=0).sum()
print(f"matched {X.shape[1]} cameras | GT path {path:.2f} m | Sim3 scale (GT/Pi3X) {s:.3f}")
print(f"ATE RMSE {np.sqrt((err**2).mean())*100:.1f} cm | median {np.median(err)*100:.1f} cm | max {err.max()*100:.1f} cm")
