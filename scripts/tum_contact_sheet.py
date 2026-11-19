"""Tile every Nth TUM RGB frame into one labeled image for picking a clip."""
import sys, cv2, numpy as np
seq, out, step = sys.argv[1], sys.argv[2], int(sys.argv[3])
names = [l.split()[1] for l in open(f"{seq}/rgb.txt") if not l.startswith("#")]
tiles = []
for i in range(0, len(names), step):
    im = cv2.resize(cv2.imread(f"{seq}/{names[i]}"), (320, 240))
    cv2.putText(im, str(i), (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
    tiles.append(im)
while len(tiles) % 6: tiles.append(np.zeros_like(tiles[0]))
rows = [np.hstack(tiles[r:r+6]) for r in range(0, len(tiles), 6)]
cv2.imwrite(out, np.vstack(rows))
