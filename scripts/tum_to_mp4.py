"""Write a TUM RGB frame range as a 30 fps mp4 plus a frame -> source timestamp map."""
import sys, json, cv2
seq, out, start, end = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
rows = [l.split() for l in open(f"{seq}/rgb.txt") if not l.startswith("#")][start:end]
h, w = cv2.imread(f"{seq}/{rows[0][1]}").shape[:2]
vw = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), 30, (w, h))
for _, name in rows:
    vw.write(cv2.imread(f"{seq}/{name}"))
vw.release()
json.dump({"source": seq, "license": "CC BY 4.0 (TUM RGB-D benchmark, Sturm et al. IROS 2012)",
           "tum_index_range": [start, end],
           "frames": [{"video_frame": i, "tum_timestamp": float(t), "file": n} for i, (t, n) in enumerate(rows)]},
          open(out.rsplit(".", 1)[0] + "_frames.json", "w"), indent=1)
