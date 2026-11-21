#!/usr/bin/env python3
"""Compare fresh processes with serial model reuse for one fixed request."""
import argparse
import gc
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'experiments/sam3d-startup-profile'))
baseline_spec = importlib.util.spec_from_file_location(
    'reuse_baseline', ROOT / 'experiments/sam3d-startup-profile/run.py')
baseline = importlib.util.module_from_spec(baseline_spec)
baseline_spec.loader.exec_module(baseline)
from monitor import Monitor


def load_wrapper():
    spec = importlib.util.spec_from_file_location('reuse_infer', baseline.INFER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worker_timeout(seconds, count):
    """Zero disables the controller deadline; Slurm still limits the job."""
    return None if seconds == 0 else seconds * count


def worker(request_path, out, count):
    wrapper = load_wrapper()
    request = json.loads(request_path.read_text())
    session = wrapper.InferenceSession()
    out.mkdir(exist_ok=False)
    rows = []
    try:
        for index in range(1, count + 1):
            destination = out / f'request-{index:03d}'
            argv = baseline.command_for(request, sys.executable, destination)[3:]
            started = time.perf_counter()
            wrapper.run(wrapper.arguments(argv), session=session)
            # run() has returned: its result and other request-local references
            # are no longer retained by the wrapper. Keep only the model alive.
            import torch
            gc.collect()
            torch.cuda.synchronize()
            row = {'request': index, 'pid': os.getpid(),
                   'completed_unix_seconds': time.time(),
                   'wall_with_cleanup_seconds': time.perf_counter() - started,
                   'torch_allocated_after_cleanup_bytes': torch.cuda.memory_allocated(),
                   'torch_reserved_after_cleanup_bytes': torch.cuda.memory_reserved()}
            rows.append(row)
            baseline.write(out / 'worker.json', {'status': 'running', 'requests': rows})
            print(f'Request {index}/{count} completed in PID {os.getpid()}', flush=True)
        baseline.write(out / 'worker.json', {'status': 'completed', 'requests': rows})
    except BaseException:
        baseline.write(out / 'worker.json', {'status': 'failed', 'requests': rows})
        (out / 'error.txt').write_text(traceback.format_exc())
        raise


def summarize(out, manifest):
    summary = {'status': manifest['status'], 'groups': {}, 'artifact_hashes': {}}
    for group in manifest['groups']:
        reports, requests = [], []
        for process in group['processes']:
            folder = out / group['name'] / process['name']
            if not (folder / 'worker.json').exists():
                continue
            requests.extend(json.loads((folder / 'worker.json').read_text())['requests'])
            for path in sorted(folder.glob('request-*/report.json')):
                report = json.loads(path.read_text())
                if report['status'] == 'completed':
                    reports.append(report)
                    artifacts = json.loads((path.parent / 'artifacts.json').read_text())
                    summary['artifact_hashes'][str(path.parent.relative_to(out))] = {
                        key: value['sha256'] for key, value in artifacts.items()}
        summary['groups'][group['name']] = {
            'completed_requests': len(reports),
            'active_process_wall_seconds': sum(p['wall_seconds'] for p in group['processes']),
            'requests': requests,
            'timings_seconds': [r['timings_seconds'] for r in reports],
            'reused': [r.get('session', {}).get('reused') for r in reports]}
        if requests and group['processes'] and 'started_unix_seconds' in group['processes'][0]:
            summary['groups'][group['name']]['first_object_wall_seconds'] = (
                requests[0]['completed_unix_seconds'] - group['processes'][0]['started_unix_seconds'])
    groups = summary['groups']
    if manifest['status'] == 'completed':
        a, b = groups['fresh'], groups['reuse']
        summary['speedup'] = a['active_process_wall_seconds'] / b['active_process_wall_seconds']
        for value in groups.values():
            value['seconds_per_object'] = value['active_process_wall_seconds'] / value['completed_requests']
        summary['reuse_first_request_seconds'] = b['requests'][0]['wall_with_cleanup_seconds']
        summary['reuse_later_request_median_seconds'] = statistics.median(
            row['wall_with_cleanup_seconds'] for row in b['requests'][1:])
        hashes = list(summary['artifact_hashes'].values())
        summary['all_artifact_hashes_equal'] = all(value == hashes[0] for value in hashes)
    baseline.write(out / 'summary.json', summary)


def execute(args):
    request = baseline.normalized_request(args)
    request['seed'] = 42
    initial = baseline.identity(request)
    out = args.out.resolve()
    if out.is_relative_to(Path(__file__).resolve().parent):
        raise ValueError('Keep outputs outside the experiment code directory')
    out.mkdir(parents=True, exist_ok=False)
    baseline.write(out / 'request.json', request)
    shutil.copyfile(baseline.INFER, out / 'infer_snapshot.py')
    shutil.copyfile(__file__, out / 'runner_snapshot.py')
    shutil.copyfile(ROOT / 'experiments/sam3d-startup-profile/monitor.py', out / 'monitor_snapshot.py')
    manifest = {'status': 'running', 'requests_per_group': args.requests, 'order': args.order,
                'timeout_seconds_per_request': args.timeout,
                'internal_timeout_enabled': args.timeout > 0,
                'identity': initial, 'groups': [],
                'host': socket.gethostname(),
                'environment': {key: os.environ.get(key) for key in (
                    'SLURM_JOB_ID', 'SLURM_CPUS_PER_TASK', 'CUDA_VISIBLE_DEVICES', 'CONDA_PREFIX',
                    'CUDA_HOME', 'HF_HOME', 'TORCH_HOME', 'TORCH_EXTENSIONS_DIR', 'WARP_CACHE_PATH')},
                'scope': 'Same fixed request and seed 42; no cache clearing or empty_cache; '
                         'active process wall includes interpreter startup and shutdown; '
                         'excludes controller baseline, identity checks and inter-group gap.'}
    monitor = Monitor(out / 'resources.jsonl', 1.0)
    monitor.start()
    try:
        print('Internal timeout: ' + (f'{args.timeout:g}s per request budget'
                                     if args.timeout else 'disabled; Slurm job time limit still applies'),
              flush=True)
        time.sleep(5)
        for name in (['fresh', 'reuse'] if args.order == 'AB' else ['reuse', 'fresh']):
            group = {'name': name, 'processes': []}
            manifest['groups'].append(group)
            (out / name).mkdir()
            count = args.requests if name == 'reuse' else 1
            for index in range(1, (1 if name == 'reuse' else args.requests) + 1):
                if baseline.identity(request) != initial:
                    raise ValueError('Input/code/checkpoint inventory changed')
                process_name = f'process-{index:03d}'
                folder = out / name / process_name
                command = [sys.executable, '-u', str(Path(__file__).resolve()),
                           '--worker', '--request', str(out / 'request.json'), '--out', str(folder),
                           '--requests', str(count)]
                if Path('/usr/bin/time').is_file():
                    command = ['/usr/bin/time', '-v', '-o', str(out / name / f'{process_name}-time.txt'),
                               '--'] + command
                record = {'name': process_name, 'command': command, 'status': 'running'}
                group['processes'].append(record)
                baseline.write(out / 'experiment.json', manifest)
                print(f'Starting {name}/{process_name}: {count} request(s)', flush=True)
                started = time.perf_counter()
                with (out / name / f'{process_name}.log').open('x') as log:
                    record['started_unix_seconds'] = time.time()
                    child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                             start_new_session=True, cwd=ROOT)
                    monitor.set_phase('run', name + '/' + process_name, child.pid)
                    try:
                        # B gets the same total budget as its count of A requests.
                        record['exit_code'] = child.wait(timeout=worker_timeout(args.timeout, count))
                    except subprocess.TimeoutExpired:
                        record.update(status='timeout', exit_code=None)
                        raise
                    except BaseException:
                        record.update(status='interrupted', exit_code=None)
                        raise
                    finally:
                        baseline.stop_group(child)
                        record['wall_seconds'] = time.perf_counter() - started
                        monitor.set_phase('gap', name)
                        baseline.write(out / 'experiment.json', manifest)
                if record['exit_code'] != 0:
                    raise RuntimeError(f'{name}/{process_name} failed; see its log')
                status = json.loads((folder / 'worker.json').read_text())
                if status['status'] != 'completed' or len(status['requests']) != count:
                    raise RuntimeError('Worker did not complete the expected requests')
                if baseline.identity(request) != initial:
                    raise ValueError('Input/code/checkpoint inventory changed')
                record['status'] = 'completed'
                print(f'Completed {name}/{process_name}: {record["wall_seconds"]:.1f}s', flush=True)
            if len(manifest['groups']) == 1:
                time.sleep(10)
        manifest['status'] = 'completed'
    except BaseException:
        manifest['status'] = 'failed_or_interrupted'
        (out / 'error.txt').write_text(traceback.format_exc())
        raise
    finally:
        monitor.stop()
        manifest['monitor_error'] = monitor.error
        baseline.write(out / 'experiment.json', manifest)
        summarize(out, manifest)
    print(f'Results: {out / "summary.json"}', flush=True)
    return 1 if monitor.error else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--requests', type=int, default=3)
    parser.add_argument('--order', choices=['AB', 'BA'], default='AB')
    parser.add_argument('--timeout', type=float, default=0,
                        help='Internal seconds per request budget; 0 disables it (default). '
                             'Slurm still enforces the job time limit.')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    for key in baseline.PATH_KEYS:
        parser.add_argument('--' + key.replace('_', '-'), type=Path)
    args = parser.parse_args()
    if args.requests < 1 or (not args.worker and args.requests < 2):
        parser.error('The controller needs at least two requests')
    if not math.isfinite(args.timeout) or args.timeout < 0:
        parser.error('Use a nonnegative finite timeout; 0 disables the internal deadline')
    def terminate(*_):
        raise KeyboardInterrupt('SIGTERM')
    signal.signal(signal.SIGTERM, terminate)
    if args.worker:
        worker(args.request, args.out, args.requests)
        return 0
    return execute(args)


if __name__ == '__main__':
    raise SystemExit(main())
