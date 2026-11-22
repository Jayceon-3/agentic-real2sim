"""CPU-only checks; fake Torch/model behavior is not GPU evidence."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/tests'))
import test_sam3d_objects as fixtures

spec = importlib.util.spec_from_file_location('reuse_experiment', Path(__file__).parents[1] / 'run.py')
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


class ReuseTests(unittest.TestCase):
    def test_worker_deadline_can_be_disabled_or_scaled(self):
        self.assertIsNone(experiment.worker_timeout(0, 1))
        self.assertIsNone(experiment.worker_timeout(0, 3))
        self.assertEqual(experiment.worker_timeout(1800, 1), 1800)
        self.assertEqual(experiment.worker_timeout(1800, 3), 5400)

    def test_controller_launches_three_fresh_workers_and_one_reuse_worker(self):
        self.check_controller_order('AB')

    def test_controller_ba_runs_reuse_first_and_keeps_speedup_definition(self):
        self.check_controller_order('BA')

    def check_controller_order(self, order):
        fixture = fixtures.WrapperTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fake_modules = fixture.root / 'modules'
        fake_modules.mkdir()
        (fake_modules / 'torch.py').write_text('''from types import SimpleNamespace
__version__ = "FAKE"
version = SimpleNamespace(cuda="FAKE")
is_tensor = lambda _: False
cuda = SimpleNamespace(is_available=lambda: True, synchronize=lambda: None,
    reset_peak_memory_stats=lambda: None, get_device_name=lambda _: "FAKE",
    get_device_properties=lambda _: SimpleNamespace(total_memory=100),
    max_memory_allocated=lambda: 40, max_memory_reserved=lambda: 60,
    memory_allocated=lambda: 40, memory_reserved=lambda: 60)
''')
        request = fixtures.wrapper.arguments(fixture.args)
        request_path = fixture.root / 'source-request.json'
        request_path.write_text(json.dumps({k: str(v) if isinstance(v, Path) else v
                                            for k, v in vars(request).items() if v is not None}))
        output = fixture.root / 'pilot'
        command = [sys.executable, str(Path(experiment.__file__)), '--request', str(request_path),
                   '--out', str(output), '--requests', '3', '--order', order]
        env = dict(os.environ, PYTHONPATH=str(fake_modules), EXPECTED_CUDA=str(fixture.cuda))
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = json.loads((output / 'summary.json').read_text())
        self.assertEqual(summary['status'], 'completed')
        self.assertEqual(summary['groups']['fresh']['reused'], [False]*3)
        self.assertEqual(summary['groups']['reuse']['reused'], [False, True, True])
        manifest = json.loads((output / 'experiment.json').read_text())
        expected = ['fresh', 'reuse'] if order == 'AB' else ['reuse', 'fresh']
        self.assertEqual([g['name'] for g in manifest['groups']], expected)
        self.assertEqual([len(g['processes']) for g in manifest['groups']],
                         [3, 1] if order == 'AB' else [1, 3])
        self.assertEqual(manifest['order'], order)
        self.assertAlmostEqual(summary['speedup'],
                               summary['groups']['fresh']['active_process_wall_seconds'] /
                               summary['groups']['reuse']['active_process_wall_seconds'])
        self.assertFalse(manifest['internal_timeout_enabled'])
        self.assertTrue(summary['all_artifact_hashes_equal'])

    def test_worker_three_requests_share_model_and_record_cleanup_memory(self):
        fixture = fixtures.WrapperTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        wrapper = fixtures.wrapper
        request = wrapper.arguments(fixture.args + ['--save-splat'])
        request_path = fixture.root / 'request.json'
        request_path.write_text(json.dumps({k: str(v) if isinstance(v, Path) else v
                                            for k, v in vars(request).items() if v is not None}))
        torch = sys.modules['torch']
        torch.cuda.memory_allocated = lambda: 40
        torch.cuda.memory_reserved = lambda: 60
        out = fixture.root / 'worker'
        with patch.object(experiment, 'load_wrapper', return_value=wrapper), \
                patch.object(wrapper, 'load_runtime', wraps=wrapper.load_runtime) as load:
            experiment.worker(request_path, out, 3)
        self.assertEqual(load.call_count, 1)
        worker = json.loads((out / 'worker.json').read_text())
        self.assertEqual(worker['status'], 'completed')
        self.assertEqual(len({r['pid'] for r in worker['requests']}), 1)
        self.assertEqual([r['torch_allocated_after_cleanup_bytes'] for r in worker['requests']], [40]*3)
        reports = [json.loads(p.read_text()) for p in sorted(out.glob('request-*/report.json'))]
        self.assertEqual([r['session']['reused'] for r in reports], [False, True, True])
        self.assertEqual(len(list(out.glob('request-*/splat.ply'))), 3)

    def test_summary_uses_all_process_wall_and_separates_first_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            groups = []
            for name, counts, walls in [('fresh', [1, 1, 1], [10, 10, 10]),
                                         ('reuse', [3], [14])]:
                processes = []
                groups.append({'name': name, 'processes': processes})
                for index, (count, wall) in enumerate(zip(counts, walls), 1):
                    folder = root / name / f'process-{index:03d}'
                    folder.mkdir(parents=True)
                    processes.append({'name': folder.name, 'wall_seconds': wall})
                    experiment.baseline.write(folder / 'worker.json', {'requests': [
                        {'wall_with_cleanup_seconds': x} for x in ([9] if count == 1 else [9, 2, 2])]})
                    for i in range(count):
                        request = folder / f'request-{i+1:03d}'
                        request.mkdir()
                        experiment.baseline.write(request / 'report.json', {
                            'status': 'completed', 'timings_seconds': {}, 'session': {'reused': i > 0}})
                        experiment.baseline.write(request / 'artifacts.json', {'object.glb': {'sha256': 'same'}})
            experiment.summarize(root, {'status': 'completed', 'groups': groups})
            summary = json.loads((root / 'summary.json').read_text())
            self.assertAlmostEqual(summary['speedup'], 30/14)
            self.assertEqual(summary['reuse_first_request_seconds'], 9)
            self.assertEqual(summary['reuse_later_request_median_seconds'], 2)
            self.assertTrue(summary['all_artifact_hashes_equal'])


if __name__ == '__main__':
    unittest.main()
