#!/usr/bin/env python3
"""Repeat a fixed SAM 3D request in fresh processes and collect resource curves."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import traceback

from monitor import Monitor, gpu_sample

ROOT = Path(__file__).resolve().parents[2]
INFER = ROOT / 'scripts/sam3d_objects/infer.py'
PATH_KEYS = ('image', 'mask', 'checkpoint', 'upstream', 'input_metadata', 'cuda_home')
VALUE_KEYS = ('seed', 'mask_threshold', 'mask_channel', 'checkpoint_revision', 'object_id')


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_request(args):
    raw = json.loads(args.request.read_text())
    if not isinstance(raw, dict):
        raise ValueError('Request must be a JSON object from infer.py')
    if raw.get('validate_only'):
        raise ValueError('Use a real inference request, not --validate-only')
    request = {key: raw[key] for key in PATH_KEYS + VALUE_KEYS if raw.get(key) is not None}
    for key in PATH_KEYS:
        override = getattr(args, key, None)
        if override is not None:
            request[key] = str(override)
        if key in request:
            request[key] = str(Path(request[key]).expanduser().resolve())
    for key in ('image', 'mask', 'checkpoint', 'upstream'):
        if key not in request:
            raise ValueError('Missing request field: ' + key)
    checkpoint = Path(request['checkpoint'])
    if checkpoint.is_dir():
        request['checkpoint'] = str(checkpoint / 'pipeline.yaml')
    request.setdefault('seed', 42)
    request.setdefault('mask_threshold', 0)
    request.setdefault('mask_channel', 'auto')
    request.setdefault('object_id', 'object')
    if type(raw.get('save_splat', False)) is not bool:
        raise ValueError('save_splat must be a JSON boolean')
    request['save_splat'] = raw.get('save_splat', False)
    for key in ('image', 'mask', 'checkpoint', 'input_metadata'):
        if key in request and not Path(request[key]).is_file():
            raise FileNotFoundError(f'{key}: {request[key]} (override remote paths on this machine)')
    if not (Path(request['upstream']) / 'notebook/inference.py').is_file():
        raise FileNotFoundError('Missing upstream notebook/inference.py')
    return request


def identity(request):
    files = {key: sha(request[key]) for key in ('image', 'mask', 'checkpoint', 'input_metadata')
             if key in request}
    upstream = Path(request['upstream'])
    code = {str(path.relative_to(upstream)): sha(path)
            for directory in ('notebook', 'sam3d_objects')
            for path in sorted((upstream / directory).rglob('*.py'))}
    weights = [{'path': str(path.relative_to(Path(request['checkpoint']).parent)),
                'bytes': path.stat().st_size, 'mtime_ns': path.stat().st_mtime_ns}
               for path in sorted(Path(request['checkpoint']).parent.rglob('*')) if path.is_file()]
    return {'input_sha256': files, 'infer_sha256': sha(INFER), 'upstream_python_sha256': code,
            'checkpoint_inventory': weights, 'weight_contents_hashed': False}


def command_for(request, python, out):
    command = [python, '-u', str(INFER)]
    for key in PATH_KEYS + VALUE_KEYS:
        if key in request:
            command += ['--' + key.replace('_', '-'), str(request[key])]
    if request['save_splat']:
        command.append('--save-splat')
    return command + ['--events', '--out', str(out)]


def stop_group(child):
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    # Also stop any lingering descendants; the next trial must not overlap.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait()


def execute(args):
    if not sys.platform.startswith('linux'):
        raise ValueError('Run this controller on Linux/WSL; /proc telemetry is required')
    request = normalized_request(args)
    python = shutil.which(str(args.python))
    if python is None:
        raise FileNotFoundError('Inference Python executable not found')
    initial = identity(request)
    output = args.out.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(Path(__file__).parent, output / 'experiment_code',
                    ignore=shutil.ignore_patterns('__pycache__', 'tests'))
    shutil.copyfile(INFER, output / 'infer_snapshot.py')
    write(output / 'request.json', request)
    manifest = {'schema_version': 1, 'status': 'running', 'hostname': socket.gethostname(),
                'platform': platform.platform(), 'python': python, 'controller_python': sys.executable,
                'started_unix_seconds': time.time(), 'runs_requested': args.runs,
                'interval_seconds': args.interval, 'gap_seconds': args.gap,
                'baseline_seconds': args.baseline, 'run_timeout_seconds': args.timeout,
                'identity': initial, 'runs': [], 'gpu_before': gpu_sample(),
                'environment': {key: os.environ.get(key) for key in (
                    'SLURM_JOB_ID', 'SLURM_JOB_NODELIST', 'SLURM_CPUS_PER_TASK', 'CUDA_VISIBLE_DEVICES',
                    'CUDA_HOME', 'CONDA_PREFIX', 'OMP_NUM_THREADS', 'MAX_JOBS',
                    'HF_HOME', 'TORCH_EXTENSIONS_DIR', 'WARP_CACHE_PATH')},
                'scope': 'Fresh Python process per trial; OS/disk caches are not cleared; no model reuse.'}
    write(output / 'experiment.json', manifest)
    monitor = Monitor(output / 'resources.jsonl', args.interval)
    monitor.start()
    try:
        time.sleep(args.baseline)
        for index in range(1, args.runs + 1):
            if identity(request) != initial:
                raise ValueError('Fixed input, code or checkpoint inventory changed; stopping experiment')
            name = f'run-{index:03d}'
            folder = output / name
            folder.mkdir()
            command = command_for(request, python, folder / 'results')
            # GNU time wraps the inference process, without changing its arguments.
            time_bin = Path('/usr/bin/time')
            launch = ([str(time_bin), '-v', '-o', str(folder / 'time.txt'), '--'] + command
                      if time_bin.is_file() else command)
            write(folder / 'command.json', {'argv': launch, 'cwd': str(ROOT)})
            record = {'run_id': name, 'status': 'running', 'started_unix_seconds': time.time(),
                      'started_monotonic_seconds': time.monotonic(), 'gnu_time_enabled': time_bin.is_file()}
            manifest['runs'].append(record)
            write(output / 'experiment.json', manifest)
            print(f'[{index}/{args.runs}] Starting fresh process: {folder}', flush=True)
            with (folder / 'console.log').open('x') as log:
                child = subprocess.Popen(launch, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                         start_new_session=True, env=dict(os.environ, LC_ALL='C'))
                record['process_group'] = child.pid
                monitor.set_phase('run', name, child.pid)
                write(folder / 'trial.json', record)
                try:
                    code = child.wait(timeout=args.timeout)
                    record.update(exit_code=code, status='completed' if code == 0 else 'failed')
                except subprocess.TimeoutExpired:
                    record.update(status='timeout', exit_code=None)
                except BaseException:
                    record.update(status='interrupted', exit_code=None)
                    raise
                finally:
                    stop_group(child)
                    record['finished_unix_seconds'] = time.time()
                    record['wall_seconds'] = time.monotonic() - record['started_monotonic_seconds']
                    write(folder / 'trial.json', record)
                    monitor.set_phase('gap', name)
            report_path = folder / 'results/report.json'
            try:
                report = json.loads(report_path.read_text())
                record['wrapper_status'] = report.get('status')
                if report.get('status') != 'completed' or not (folder / 'results/object.glb').is_file():
                    record['status'] = 'failed' if record['status'] == 'completed' else record['status']
            except (OSError, ValueError):
                record['wrapper_status'] = 'missing_or_invalid_report'
                if record['status'] == 'completed':
                    record['status'] = 'failed'
            if identity(request) != initial:
                record['status'] = 'invalid_inputs_changed'
                write(folder / 'trial.json', record)
                raise ValueError('Inputs changed during a trial; results are not comparable')
            write(folder / 'trial.json', record)
            write(output / 'experiment.json', manifest)
            print(f'{name}: {record["status"]}, {record["wall_seconds"]:.1f}s', flush=True)
            if index < args.runs:
                time.sleep(args.gap)
        manifest['status'] = 'completed' if all(r['status'] == 'completed' for r in manifest['runs']) else 'completed_with_failures'
    except BaseException:
        manifest['status'] = 'interrupted_or_failed'
        (output / 'error.txt').write_text(traceback.format_exc())
        raise
    finally:
        monitor.stop()
        manifest['monitor_error'] = monitor.error
        manifest['finished_unix_seconds'] = time.time()
        write(output / 'experiment.json', manifest)
        from summarize import summarize
        try:
            summarize(output, plots=False)
        except Exception:
            (output / 'summary_error.txt').write_text(traceback.format_exc())
    print('Results:', output, flush=True)
    return 0 if manifest['status'] == 'completed' and not monitor.error else 1


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', type=Path, required=True, help='Existing infer.py request.json; its out is ignored')
    p.add_argument('--out', type=Path, required=True, help='New experiment output directory outside this code directory')
    p.add_argument('--python', default=sys.executable, help='Dedicated SAM 3D environment Python')
    p.add_argument('--runs', type=int, default=5)
    p.add_argument('--interval', type=float, default=1.0)
    p.add_argument('--gap', type=float, default=10.0)
    p.add_argument('--baseline', type=float, default=5.0)
    p.add_argument('--timeout', type=float, default=1800.0, help='Per-trial timeout in seconds')
    for key in PATH_KEYS:
        p.add_argument('--' + key.replace('_', '-'), type=Path, help='Override the request path on this machine')
    return p


def main():
    args = parser().parse_args()
    if args.runs < 1 or any(not math.isfinite(x) for x in (args.interval, args.gap, args.baseline, args.timeout)):
        raise ValueError('Use a positive run count and finite timing values')
    if args.interval < .1 or args.gap < 0 or args.baseline < 0 or args.timeout <= 0:
        raise ValueError('Interval must be >=0.1; gap/baseline >=0; timeout >0')
    if args.out.resolve().is_relative_to(Path(__file__).resolve().parent):
        raise ValueError('Keep generated results outside the experiment code directory, e.g. outputs/')
    def terminate(signum, frame):
        raise KeyboardInterrupt(f'Received signal {signum}')
    signal.signal(signal.SIGTERM, terminate)
    return execute(args)


if __name__ == '__main__':
    raise SystemExit(main())
