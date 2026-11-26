"""Bounded CPU placement search using only two preregistered alignment masks."""
import ctypes
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_erosion, distance_transform_edt
from scipy.optimize import differential_evolution, minimize
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[4]
RUN = ROOT / 'outputs/office48-sam3d-ab/agent-run-001'
BASE = RUN.parent


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def event(action, **values):
    with (RUN / 'operations.jsonl').open('a') as stream:
        stream.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(),
                                 'action': action, **values}) + '\n')


class Raster:
    def __init__(self):
        self.lib = ctypes.CDLL(str(RUN / 'source/raster.so'))
        f32 = np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS')
        i32 = np.ctypeslib.ndpointer(dtype=np.int32, flags='C_CONTIGUOUS')
        f64 = np.ctypeslib.ndpointer(dtype=np.float64, flags='C_CONTIGUOUS')
        self.lib.raster.argtypes = [f32, ctypes.c_int, i32, ctypes.c_int, f64, f64, f64,
                                   ctypes.c_int, ctypes.c_int, f32]
        self.lib.raster.restype = None

    def draw(self, geometry, transform, camera, width):
        height = width * 720 // 1280
        k = camera['K'].copy() * (width / 1280)
        k[2, 2] = 1
        depth = np.empty((height, width), dtype=np.float32)
        self.lib.raster(geometry['vertices'], len(geometry['vertices']), geometry['faces'],
                        len(geometry['faces']), np.ascontiguousarray(transform, dtype=np.float64),
                        np.ascontiguousarray(camera['rt'], dtype=np.float64),
                        np.ascontiguousarray(k, dtype=np.float64), width, height, depth)
        return depth


def load_geometry(name):
    with np.load(RUN / 'geometry' / (name + '.npz')) as data:
        return {k: np.ascontiguousarray(data[k]) for k in ['vertices', 'faces']}


def projection_iou(predicted, truth):
    return float((predicted & truth).sum() / max(1, (predicted | truth).sum()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', required=True)
    args = parser.parse_args()
    raster = Raster()
    lock = json.loads((BASE / 'frozen-v1/lock.json').read_text())
    metadata = json.loads((RUN / 'geometry/export.json').read_text())
    all_results = []
    for obj in lock['objects']:
        identity = obj['id']
        reference = metadata['scene'][identity]
        low, high = np.array(reference['min']), np.array(reference['max'])
        center = (low + high) * .5
        occluders = load_geometry('occluders-' + identity)
        alignment = [v for v in obj['views'] if v['role'] == 'alignment']
        cameras = []
        for view in alignment:
            with np.load(RUN / 'geometry' / f'camera-{view["frame"]}.npz') as data:
                camera = {k: data[k] for k in ['K', 'rt']}
            camera['frame'] = view['frame']
            camera['mask_path'] = BASE / 'frozen-v1' / view['mask']
            camera['image_path'] = BASE / 'frozen-v1' / view['image']
            camera['buffers'] = {}
            for width in [320, 640]:
                shape = (width, width * 720 // 1280)
                truth = np.array(Image.open(camera['mask_path']).resize(shape, Image.Resampling.NEAREST)) > 127
                boundary = truth ^ binary_erosion(truth)
                camera['buffers'][width] = {
                    'truth': truth, 'distance': distance_transform_edt(~boundary),
                    'depth': raster.draw(occluders, np.eye(4), camera, width)}
            cameras.append(camera)
        for seed in [42, 43, 44]:
            name = f'{identity}-seed-{seed}'
            if name != args.candidate:
                continue
            geometry = load_geometry(name)
            points = geometry['vertices'].astype(np.float64)
            native_center = (points.min(0) + points.max(0)) * .5
            prior_scale = float((high[2] - low[2]) / np.ptp(points[:, 2]))
            support_height = float(low[2])
            started = time.perf_counter()
            trace = RUN / 'optimization' / (name + '.jsonl')
            calls = 0
            best = {'loss': 1e10}
            # World floor contact fixes vertical translation; all other transform
            # parameters act on the complete unmodified imported asset.
            def transform(parameters):
                x, y, yaw, logarithm, pitch, roll = parameters
                scale = prior_scale * math.exp(logarithm)
                rotation = Rotation.from_euler('xyz', [roll, pitch, yaw], degrees=True).as_matrix()
                rotated = points @ rotation.T
                translation = np.array([x, y, support_height - scale * rotated[:, 2].min()])
                translation[:2] -= scale * (rotation @ native_center)[:2]
                matrix = np.eye(4)
                matrix[:3, :3] = rotation * scale
                matrix[:3, 3] = translation
                return matrix, rotation, scale, translation

            def evaluate(parameters, width=320, track=True):
                nonlocal calls, best
                matrix, rotation, scale, translation = transform(parameters)
                per_view, contours = [], []
                for camera in cameras:
                    buffer = camera['buffers'][width]
                    depth = raster.draw(geometry, matrix, camera, width)
                    visible = (depth < 1e9) & (depth <= buffer['depth'] + .002)
                    iou = projection_iou(visible, buffer['truth'])
                    boundary = visible ^ binary_erosion(visible)
                    contour = float(buffer['distance'][boundary].mean() / width) if boundary.any() else .25
                    per_view.append(iou)
                    contours.append(contour)
                transformed = points @ matrix[:3, :3].T + translation
                minimum, maximum = transformed.min(0), transformed.max(0)
                wall_violation = max(0., -2.255 - minimum[0]) + max(0., maximum[1] - 4.23)
                prior = .01 * ((parameters[0] - center[0])**2 + (parameters[1] - center[1])**2) + .005 * parameters[3]**2
                loss = 1 - float(np.mean(per_view)) + .1 * float(np.mean(contours)) + 2 * wall_violation + prior
                if track:
                    calls += 1
                    record = {'call': calls, 'width': width, 'parameters': list(parameters),
                              'loss': loss, 'mean_iou': float(np.mean(per_view)), 'per_view_iou': per_view,
                              'wall_violation': wall_violation, 'elapsed_seconds': time.perf_counter() - started}
                    with trace.open('a') as stream:
                        stream.write(json.dumps(record) + '\n')
                    if loss < best['loss']:
                        best = record
                return loss

            yaw_prior = 0 if identity == 'cabinet' else -90
            bounds = [(center[0] - .5, center[0] + .5), (center[1] - .55, center[1] + .55),
                      (yaw_prior - 25, yaw_prior + 25), (math.log(.65), math.log(1.45)), (0, 0), (0, 0)]
            event('alignment_start', candidate=name, views=[v['frame'] for v in alignment],
                  bounds=bounds, support_height=support_height, prior_scale=prior_scale,
                  renderer='CPU triangle silhouette proxy; final scores use Blender')
            for yaw in [yaw_prior - 20, yaw_prior, yaw_prior + 20]:
                evaluate([center[0], center[1], yaw, 0, 0, 0])
            initial = best.copy()
            result = differential_evolution(lambda x: evaluate(x, 320), bounds, seed=442,
                    popsize=7, maxiter=24, polish=False, x0=initial['parameters'],
                    callback=lambda x, convergence: time.perf_counter() - started > 150,
                    updating='immediate', workers=1)
            # Refine at a higher raster without reusing low-resolution loss values.
            best = {'loss': 1e10}
            evaluate(result.x, 640)
            refined = minimize(lambda x: evaluate(x, 640), result.x, method='Powell', bounds=bounds,
                               options={'maxfev': 220, 'xtol': .002, 'ftol': .0002})
            parameters = best['parameters']
            matrix, rotation, scale, translation = transform(parameters)
            placement = {'schema_version': 1, 'coordinate_space': 'blender_imported_to_scene_world',
                         'translation_m': translation.tolist(),
                         'rotation_euler_xyz_deg': Rotation.from_matrix(rotation).as_euler('xyz', degrees=True).tolist(),
                         'scale': [scale]*3, 'semantic_class': obj['semantic_class'],
                         'note': 'Agent placement from two alignment views only; uniform scale; original geometry and materials retained.'}
            write(RUN / 'placements' / (name + '.json'), placement)
            summary = {'candidate': name, 'alignment_frames': [v['frame'] for v in alignment],
                       'initial': initial, 'selected': best, 'calls': calls,
                       'wall_seconds': time.perf_counter() - started, 'placement': placement,
                       'scope': 'Agent-operated bounded search, upright placement, source-verified front +/-25 degrees, floor contact; no evaluation views used.'}
            write(RUN / 'optimization' / (name + '.json'), summary)
            event('alignment_selected', **summary)
            for camera in cameras:
                width = 640
                depth = raster.draw(geometry, matrix, camera, width)
                visible = (depth < 1e9) & (depth <= camera['buffers'][width]['depth'] + .002)
                source = np.array(Image.open(camera['image_path']).resize((640, 360)).convert('RGB'))
                overlay = source.astype(float)
                overlay[visible] = overlay[visible]*.5 + np.array([255, 90, 30])*.5
                truth = camera['buffers'][width]['truth']
                edge = truth ^ binary_erosion(truth)
                overlay[edge] = [20, 255, 100]
                Image.fromarray(overlay.astype('uint8')).save(RUN / 'review' / f'{name}-proxy-{camera["frame"]}.png')
            all_results.append(summary)
            print(name, 'selected alignment proxy IoU', best['mean_iou'], 'seconds', summary['wall_seconds'], flush=True)
    write(RUN / 'optimization' / (args.candidate + '-run.json'), all_results)


if __name__ == '__main__':
    main()
