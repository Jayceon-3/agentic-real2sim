"""Best-effort Linux process-group and device telemetry, without ML dependencies."""
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import threading
import time


def gpu_sample():
    fields = ['uuid', 'name', 'utilization.gpu', 'memory.used', 'memory.total',
              'power.draw', 'clocks.sm']
    result = {'devices': [], 'processes': []}
    queries = [('devices', '--query-gpu=' + ','.join(fields)),
               ('processes', '--query-compute-apps=gpu_uuid,pid,used_gpu_memory')]
    for name, query in queries:
        try:
            command = subprocess.run(['nvidia-smi', query, '--format=csv,noheader,nounits'],
                                     capture_output=True, text=True, timeout=2)
            if command.returncode:
                raise RuntimeError(command.stderr.strip() or command.stdout.strip())
            for row in csv.reader(io.StringIO(command.stdout)):
                row = [x.strip() for x in row]
                if not row:
                    continue
                def number(value):
                    try:
                        return float(value)
                    except ValueError:
                        return None
                if name == 'devices':
                    result[name].append(dict(zip(
                        ['uuid', 'name', 'gpu_util_percent', 'memory_used_mib',
                         'memory_total_mib', 'power_w', 'sm_clock_mhz'],
                        row[:2] + [number(x) for x in row[2:]])))
                else:
                    result[name].append({'uuid': row[0], 'pid': int(row[1]),
                                         'memory_used_mib': number(row[2])})
        except (OSError, subprocess.SubprocessError, ValueError, IndexError, RuntimeError) as error:
            result[name + '_error'] = str(error)
    return result


def group_snapshot(group, proc=Path('/proc')):
    """Track (PID, starttime), so PID reuse cannot produce bogus deltas."""
    entries, errors = {}, []
    for path in proc.iterdir():
        if not path.name.isdigit():
            continue
        try:
            raw = (path / 'stat').read_text()
            fields = raw[raw.rfind(')') + 2:].split()  # Starts at stat field 3.
            if int(fields[2]) != group or fields[0] == 'Z':
                continue
            item = {'pid': int(path.name), 'start_ticks': int(fields[19]),
                    'cpu_ticks': int(fields[11]) + int(fields[12]),
                    'minor_faults': int(fields[7]), 'major_faults': int(fields[9]),
                    'rss_bytes': int(fields[21]) * os.sysconf('SC_PAGE_SIZE')}
            try:
                counters = dict(line.split(':', 1) for line in (path / 'io').read_text().splitlines())
                for key in ('read_bytes', 'write_bytes', 'rchar', 'wchar'):
                    item[key] = int(counters[key])
            except (OSError, ValueError, KeyError) as error:
                errors.append(f'{path.name}/io: {error}')
            entries[(item['pid'], item['start_ticks'])] = item
        except (OSError, ValueError, IndexError):
            # Processes can exit during a /proc scan.
            continue
    return entries, errors


def rates(current, previous, seconds):
    result = {'pids': [item['pid'] for item in current.values()],
              'rss_bytes': sum(item['rss_bytes'] for item in current.values()),
              'matched_processes': len(current.keys() & previous.keys())}
    for key in ('cpu_ticks', 'read_bytes', 'write_bytes', 'rchar', 'wchar', 'minor_faults', 'major_faults'):
        pairs = [(item[key], previous[identity][key]) for identity, item in current.items()
                 if identity in previous and key in item and key in previous[identity]]
        value = sum(max(0, a-b) for a, b in pairs) / seconds if pairs and seconds > 0 else None
        if key == 'cpu_ticks':
            result['cpu_percent_one_core'] = value * 100 / os.sysconf('SC_CLK_TCK') if value is not None else None
        else:
            result[key + '_per_second'] = value
    return result


class Monitor:
    def __init__(self, output, interval):
        self.output, self.interval = Path(output), interval
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.phase, self.run_id, self.pid = 'baseline', None, None
        self.error = None
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def set_phase(self, phase, run_id=None, pid=None):
        with self.lock:
            self.phase, self.run_id, self.pid = phase, run_id, pid

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=10)
        if self.thread.is_alive():
            self.error = 'Sampler did not stop within 10 seconds'

    def loop(self):
        previous, previous_group, previous_time = {}, None, None
        try:
            with self.output.open('x') as stream:
                while not self.stop_event.is_set():
                    now = time.monotonic()
                    with self.lock:
                        phase, run_id, pid = self.phase, self.run_id, self.pid
                    current, errors = group_snapshot(pid) if pid is not None else ({}, [])
                    delta = now - previous_time if previous_time is not None else 0
                    record = {'unix_seconds': time.time(), 'monotonic_seconds': now,
                              'phase': phase, 'run_id': run_id, 'root_pid': pid,
                              'process': rates(current, previous if pid == previous_group else {}, delta),
                              'process_counters': list(current.values()), 'proc_errors': errors}
                    record['gpu_sample_start_unix_seconds'] = time.time()
                    record['gpu'] = gpu_sample()
                    record['sample_seconds'] = time.monotonic() - now
                    stream.write(json.dumps(record, allow_nan=False) + '\n')
                    stream.flush()
                    previous, previous_group, previous_time = current, pid, now
                    self.stop_event.wait(max(0, self.interval - record['sample_seconds']))
        except Exception as error:
            self.error = repr(error)
