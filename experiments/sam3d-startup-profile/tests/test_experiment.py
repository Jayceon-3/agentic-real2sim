"""CPU-only orchestration tests; no model, GPU or Slurm allocation required."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

FOLDER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOLDER))
spec = importlib.util.spec_from_file_location('startup_experiment', FOLDER / 'run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
from monitor import group_snapshot, rates, gpu_sample
from summarize import summarize

FAKE = '''import argparse,json,os,time
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--out'); a,_=p.parse_known_args()
out=Path(a.out);out.mkdir()
(out/'pid.txt').write_text(str(os.getpid()))
start=time.monotonic()
(out/'events.jsonl').write_text(json.dumps(dict(stage='inference',event='start',monotonic_seconds=start))+'\\n')
time.sleep(.22)
failed = out.parent.name == 'run-002'
(out/'report.json').write_text(json.dumps(dict(status='failed' if failed else 'completed',
timings_seconds=dict(preparation=.01,runtime_import=.02,model_init=.03,inference=.2,export=.01,end_to_end=.28))))
if not failed: (out/'object.glb').write_bytes(b'fixture')
raise SystemExit(7 if failed else 0)
'''


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fake = self.root / 'fake.py'
        self.fake.write_text(FAKE)
        (self.root / 'notebook').mkdir()
        (self.root / 'notebook/inference.py').write_text('# fake upstream')
        (self.root / 'weights').mkdir()
        (self.root / 'weights/pipeline.yaml').write_text('fixture: true')
        for name in ('image.png', 'mask.png'):
            (self.root / name).write_bytes(b'fixed input')
        self.request = self.root / 'request.json'
        self.request.write_text(json.dumps(dict(image=str(self.root / 'image.png'),
            mask=str(self.root / 'mask.png'), checkpoint=str(self.root / 'weights/pipeline.yaml'),
            upstream=str(self.root), seed=42, save_splat=True, out='ignored')))
        self.args = runner.parser().parse_args(['--request', str(self.request), '--out', str(self.root / 'out'),
            '--runs', '5', '--gap', '0', '--baseline', '0', '--interval', '.1', '--timeout', '10'])
        patcher = patch.object(runner, 'INFER', self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_five_fresh_processes_failure_retained_and_summary_excludes_failure(self):
        no_gpu = {'devices': [], 'processes': [], 'devices_error': 'test: no GPU'}
        with patch('monitor.gpu_sample', return_value=no_gpu), patch.object(runner, 'gpu_sample', return_value=no_gpu):
            self.assertEqual(runner.execute(self.args), 1)
        trials = json.loads((self.args.out / 'experiment.json').read_text())['runs']
        self.assertEqual(len(trials), 5)
        self.assertEqual(trials[1]['status'], 'failed')
        self.assertEqual(trials[1]['exit_code'], 7)
        pids = [(self.args.out / t['run_id'] / 'results/pid.txt').read_text() for t in trials]
        self.assertEqual(len(set(pids)), 5)
        for previous, current in zip(trials, trials[1:]):
            self.assertLessEqual(previous['finished_unix_seconds'], current['started_unix_seconds'])
        report = summarize(self.args.out)
        self.assertEqual(report['subsequent_successful_trials']['inference']['n'], 3)
        self.assertEqual(report['first_trial']['run_id'], 'run-001')
        self.assertEqual(report['trials'][0]['gpu_samples'], 0)
        with self.assertRaises(FileExistsError):
            runner.execute(self.args)

    def test_timeout_terminates_group_and_records_failure(self):
        self.args.runs, self.args.timeout = 1, .05
        with patch('monitor.gpu_sample', return_value={}), patch.object(runner, 'gpu_sample', return_value={}):
            self.assertEqual(runner.execute(self.args), 1)
        trial = json.loads((self.args.out / 'run-001/trial.json').read_text())
        self.assertEqual(trial['status'], 'timeout')
        with self.assertRaises(ProcessLookupError):
            os.killpg(trial['process_group'], 0)

    def test_identity_detects_input_and_code_changes(self):
        req = runner.normalized_request(self.args)
        original = runner.identity(req)
        (self.root / 'mask.png').write_bytes(b'changed')
        self.assertNotEqual(original, runner.identity(req))
        self.fake.write_text('changed code')
        self.assertNotEqual(original['infer_sha256'], runner.identity(req)['infer_sha256'])

    def test_missing_remote_paths_fail_before_output_creation(self):
        data = json.loads(self.request.read_text())
        data['image'] = '/missing/remote/image.png'
        self.request.write_text(json.dumps(data))
        with self.assertRaises(FileNotFoundError):
            runner.execute(self.args)
        self.assertFalse(self.args.out.exists())


class TelemetryTests(unittest.TestCase):
    def test_real_proc_group_contains_current_process(self):
        entries, _ = group_snapshot(os.getpgrp())
        self.assertIn(os.getpid(), [x['pid'] for x in entries.values()])

    def test_rates_do_not_count_pid_reuse_or_first_observation(self):
        old = {(1, 10): dict(pid=1, rss_bytes=100, cpu_ticks=200, read_bytes=2000)}
        new = {(1, 11): dict(pid=1, rss_bytes=200, cpu_ticks=10, read_bytes=100)}
        self.assertIsNone(rates(new, old, 1)['cpu_percent_one_core'])
        self.assertIsNone(rates(new, old, 1)['read_bytes_per_second'])
        new = {(1, 10): dict(pid=1, rss_bytes=100, cpu_ticks=300, read_bytes=3000)}
        self.assertEqual(rates(new, old, 2)['read_bytes_per_second'], 500)

    def test_unavailable_gpu_is_missing_not_zero(self):
        with patch('monitor.subprocess.run', side_effect=FileNotFoundError('no nvidia-smi')):
            result = gpu_sample()
        self.assertEqual(result['devices'], [])
        self.assertIn('devices_error', result)


if __name__ == '__main__':
    unittest.main()
