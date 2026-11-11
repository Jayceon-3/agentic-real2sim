#!/usr/bin/env python3
"""Summarize retained trials; optionally render timing and telemetry figures."""
import argparse
import csv
import json
from pathlib import Path
import statistics

STAGES = ['preparation', 'runtime_import', 'model_init', 'inference', 'export']


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def jsonl(path):
    if not path.exists():
        return []
    result = []
    for line in path.read_text().splitlines():
        try:
            result.append(json.loads(line))
        except ValueError:
            pass  # A killed process may leave a partial final line.
    return result


def summarize(root, plots=False):
    root = Path(root)
    manifest = read(root / 'experiment.json')
    if manifest is None:
        raise ValueError('Missing experiment.json')
    samples = jsonl(root / 'resources.jsonl')
    rows = []
    for trial in manifest['runs']:
        folder = root / trial['run_id']
        report = read(folder / 'results/report.json', {})
        times = report.get('timings_seconds', {})
        row = {'run_id': trial['run_id'], 'status': trial['status'],
               'wrapper_status': report.get('status'), 'exit_code': trial.get('exit_code'),
               'process_wall_seconds': trial.get('wall_seconds')}
        row.update({key: times.get(key) for key in STAGES + ['end_to_end']})
        startup = times.get('runtime_import', 0) + times.get('model_init', 0)
        row['startup_fraction'] = startup / times['end_to_end'] if times.get('end_to_end') and all(k in times for k in ('runtime_import', 'model_init')) else None
        for key in ('allocated', 'reserved'):
            peaks = [value['peak_torch_' + key + '_bytes'] for value in report.get('memory', {}).values()
                     if 'peak_torch_' + key + '_bytes' in value]
            row['peak_torch_' + key + '_gib'] = max(peaks) / 1024**3 if peaks else None
        active = [s for s in samples if s.get('phase') == 'run' and s.get('run_id') == trial['run_id']]
        row['resource_samples'] = len(active)
        row['gpu_samples'] = sum(bool(s.get('gpu', {}).get('devices')) for s in active)
        row['process_samples'] = sum(bool(s.get('process', {}).get('pids')) for s in active)
        row['events_present'] = (folder / 'results/events.jsonl').is_file()
        rows.append(row)
    if rows:
        with (root / 'summary.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    # Run 001 is always isolated, even if it failed. Do not silently substitute 002.
    later = [row for row in rows if row['run_id'] != 'run-001' and row['status'] == 'completed']
    stats = {}
    for key in STAGES + ['end_to_end', 'process_wall_seconds', 'startup_fraction',
                         'peak_torch_allocated_gib', 'peak_torch_reserved_gib']:
        values = [row[key] for row in later if row[key] is not None]
        stats[key] = {'n': len(values), 'median': statistics.median(values) if values else None,
                      'min': min(values) if values else None, 'max': max(values) if values else None}
    summary = {'first_trial': next((row for row in rows if row['run_id'] == 'run-001'), None),
               'subsequent_successful_trials': stats, 'trials': rows,
               'monitor_error': manifest.get('monitor_error'),
               'limits': ['Fresh process does not imply cold filesystem/JIT caches.',
                          'Device GPU metrics may include other processes; identify devices by UUID.',
                          'Missing telemetry is not zero usage. Sampling may miss brief peaks/processes.',
                          'Process rates cover matched PID/starttime pairs in the launch process group.',
                          'Process read_bytes is not a full remote-filesystem throughput measurement.',
                          'Torch reserved memory includes caches; peaks are not additive across stages.']}
    (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    lines = ['# Fresh-process SAM 3D profiling', '',
             f'Experiment status: {manifest["status"]}', '',
             '| Trial | Status | Import (s) | Init (s) | Inference (s) | Total (s) | GPU samples |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    def fmt(value):
        return 'N/A' if value is None else f'{value:.2f}'
    for row in rows:
        lines.append('| ' + ' | '.join([row['run_id'], row['status']] +
                     [fmt(row[key]) for key in ('runtime_import', 'model_init', 'inference', 'end_to_end')] +
                     [str(row['gpu_samples'])]) + ' |')
    lines += ['', 'Subsequent successful trials only (run-001 is separate):', '',
              '| Metric | n | Median | Min | Max |', '| --- | ---: | ---: | ---: | ---: |']
    for key, stat in stats.items():
        lines.append(f'| {key} | {stat["n"]} | {fmt(stat["median"])} | {fmt(stat["min"])} | {fmt(stat["max"])} |')
    lines += ['', '## Interpretation limits', ''] + ['- ' + text for text in summary['limits']]
    (root / 'SUMMARY.md').write_text('\n'.join(lines) + '\n')
    if plots:
        plot(root, rows, samples, manifest)
    return summary


def plot(root, rows, samples, manifest):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    valid = [row for row in rows if row['status'] == 'completed' and all(row[k] is not None for k in STAGES)]
    if valid:
        fig, ax = plt.subplots(figsize=(10, 5))
        bottom = np.zeros(len(valid))
        for key in STAGES:
            values = np.array([row[key] for row in valid])
            ax.bar([row['run_id'] for row in valid], values, bottom=bottom, label=key)
            bottom += values
        ax.set_ylabel('Seconds (named stages; excludes residual wrapper overhead)')
        ax.legend()
        fig.tight_layout()
        fig.savefig(root / 'stage-times.png', dpi=160)
        plt.close(fig)
    for trial in manifest['runs']:
        # Include the trailing idle gap to show memory release after process exit.
        selected = [s for s in samples if s.get('run_id') == trial['run_id']]
        if not selected:
            continue
        start = trial['started_monotonic_seconds']
        x = [s['monotonic_seconds'] - start for s in selected]
        fig, axes = plt.subplots(6, 1, figsize=(12, 14), sharex=True)
        def series(key, divisor=1):
            return [s.get('process', {}).get(key) / divisor
                    if s.get('process', {}).get(key) is not None else float('nan') for s in selected]
        axes[0].plot(x, series('cpu_percent_one_core'), label='Process group CPU (100% = one core)')
        axes[1].plot(x, series('rss_bytes', 1024**3), label='Summed RSS (shared pages may count twice)')
        for key in ('read_bytes', 'write_bytes'):
            axes[2].plot(x, series(key + '_per_second', 1024**2), label=key)
        devices = sorted({d['uuid'] for s in selected for d in s.get('gpu', {}).get('devices', [])})
        for uuid in devices:
            for axis, key in ((axes[3], 'gpu_util_percent'), (axes[4], 'memory_used_mib'), (axes[5], 'power_w')):
                y = []
                for s in selected:
                    d = next((d for d in s.get('gpu', {}).get('devices', []) if d['uuid'] == uuid), {})
                    y.append(d.get(key) if d.get(key) is not None else float('nan'))
                axis.plot(x, y, label=uuid)
        events = jsonl(root / trial['run_id'] / 'results/events.jsonl')
        for event in events:
            if event['event'] == 'start':
                at = event['monotonic_seconds'] - start
                for axis in axes:
                    axis.axvline(at, color='gray', alpha=.3)
                axes[0].text(at, 1.01, event['stage'], rotation=45, fontsize=8,
                             transform=axes[0].get_xaxis_transform())
        for axis, label in zip(axes, ['CPU %', 'RSS GiB', 'I/O MiB/s', 'GPU %', 'Device memory MiB', 'Power W']):
            axis.set_ylabel(label)
            if axis.lines:
                axis.legend(loc='upper right', fontsize=7)
        axes[-1].set_xlabel('Seconds since trial launch (not wrapper entry)')
        fig.suptitle(trial['run_id'] + ' — device metrics are not process-exclusive')
        fig.tight_layout(rect=(0, 0, 1, .96))
        fig.savefig(root / (trial['run_id'] + '-resources.png'), dpi=140)
        plt.close(fig)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--plots', action='store_true', help='Requires local matplotlib and NumPy; not needed for collection')
    args = p.parse_args()
    summarize(args.root, args.plots)
