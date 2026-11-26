"""Score completed development/evaluation renders and build source-bound review sheets."""
import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw, ImageOps
from scipy.ndimage import binary_erosion

ROOT = Path(__file__).resolve().parents[4]
RUN = ROOT / 'outputs/office48-sam3d-ab/agent-run-001'
BASE = RUN.parent
spec = importlib.util.spec_from_file_location('experiment_scores', ROOT / 'experiments/office48-sam3d-ab/run.py')
scores = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scores)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--role', choices=['alignment', 'evaluation'], required=True)
    args = p.parse_args()
    lock_path = BASE / 'frozen-v1/lock.json'
    lock = scores.load_lock(lock_path, ROOT)
    results = []
    for obj in lock['objects']:
        for seed in [42, 43, 44]:
            name = f'{obj["id"]}-seed-{seed}'
            folder = RUN / 'renders' / args.role / name
            target = RUN / 'metrics' / args.role / name
            if not (target / 'scores.json').exists():
                scores.score(SimpleNamespace(root=ROOT, lock=lock_path, renders=folder, out=target))
            metric = scores.read(target / 'scores.json')
            if metric['render_sha256'] != scores.digest(folder / 'render.json'):
                raise ValueError('Stale score')
            results.append(metric)
            views = [v for v in obj['views'] if v['role'] == args.role]
            sheet = Image.new('RGB', (1200, 350 * len(views)), (25, 28, 32))
            draw = ImageDraw.Draw(sheet)
            for index, view in enumerate(views):
                frame = view['frame']
                source = Image.open(BASE / 'frozen-v1' / view['image']).convert('RGB')
                render = Image.open(folder / f'source-{frame:06d}-rgb.png').convert('RGB')
                gt = np.array(Image.open(BASE / 'frozen-v1' / view['mask'])) > 0
                prediction = np.array(Image.open(folder / f'source-{frame:06d}-mask.png')) > 0
                ys, xs = np.where(gt)
                border = max(80, int(max(xs.max()-xs.min(), ys.max()-ys.min()) * .25))
                box = (max(0, int(xs.min())-border), max(0, int(ys.min())-border),
                       min(1280, int(xs.max())+border+1), min(720, int(ys.max())+border+1))
                overlay = np.array(source).astype(float)
                for mask, color in [(prediction & gt, [30,220,80]), (prediction & ~gt, [255,65,35]),
                                    (gt & ~prediction, [30,100,255])]:
                    overlay[mask] = overlay[mask] * .45 + np.array(color) * .55
                pictures = [source, render, Image.fromarray(overlay.astype('uint8'))]
                iou = next(v['iou'] for v in metric['views'] if v['frame'] == frame)
                for column, picture in enumerate(pictures):
                    thumbnail = ImageOps.contain(picture.crop(box), (390, 300))
                    sheet.paste(thumbnail, (column*400+5, index*350+35))
                draw.text((8, index*350+8), f'{name} / source {frame}', fill='white')
                draw.text((408, index*350+8), 'B render; same fixed camera', fill='white')
                draw.text((808, index*350+8), f'IoU {iou:.4f}: green TP, red FP, blue FN', fill='white')
            sheet.save(RUN / 'review' / f'{args.role}-{name}.jpg', quality=94)
            print(args.role, name, round(metric['mean_iou'], 4))
    scores.write(RUN / 'metrics' / (args.role + '-all.json'), results)
    if args.role == 'evaluation':
        scores.summarize(SimpleNamespace(scores=[RUN / 'metrics/evaluation' / f'{obj}-seed-{seed}' / 'scores.json'
                         for obj in ['cabinet', 'chair'] for seed in [42,43,44]], out=RUN / 'summary'))


if __name__ == '__main__':
    main()
