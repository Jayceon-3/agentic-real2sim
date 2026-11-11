"""CPU tests of request handling; the fake backend is not GPU/model validation."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / "sam3d_objects/infer.py"
spec = importlib.util.spec_from_file_location("sam3d_wrapper_test", SCRIPT)
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)

FAKE_RUNTIME = '''import os
os.environ["CUDA_HOME"] = os.environ["CONDA_PREFIX"]
from pathlib import Path
class Mesh:
    def export(self, path):
        Path(path).write_bytes(b"glTF-test-fixture")
class Splat:
    def save_ply(self, path):
        Path(path).write_bytes(b"ply-test-fixture")
class Inference:
    def __init__(self, config, compile=False):
        assert os.environ["CUDA_HOME"] == os.environ["EXPECTED_CUDA"]
        assert compile is False
    def __call__(self, image, mask, seed):
        assert image.shape == (4, 6, 3)
        assert mask.dtype.name == "bool"
        assert mask.sum() == 6
        assert seed == 42
        if os.environ.get("FAKE_FAIL"):
            raise RuntimeError("synthetic inference failure")
        return {"glb": None if os.environ.get("FAKE_NO_MESH") else Mesh(),
                "gs": Splat(), "rotation": [[1, 0, 0, 0]],
                "translation": [[0, 0, 0]], "scale": [[1, 1, 1]]}
'''


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upstream = self.root / "upstream"
        (self.upstream / "notebook").mkdir(parents=True)
        (self.upstream / "notebook/inference.py").write_text(FAKE_RUNTIME)
        self.config = self.root / "weights/pipeline.yaml"
        self.config.parent.mkdir()
        self.config.write_text("test: true\n")
        self.cuda = self.root / "cuda"
        (self.cuda / "bin").mkdir(parents=True)
        (self.cuda / "bin/nvcc").write_text("test fixture")
        self.image = self.root / "image.png"
        self.mask = self.root / "mask.png"
        Image.new("RGBA", (6, 4), (100, 120, 140, 255)).save(self.image)
        mask = np.zeros((4, 6), dtype="uint8")
        mask[1:3, 1:4] = 255
        Image.fromarray(mask).save(self.mask)
        self.out = self.root / "out"
        self.args = ["--image", str(self.image), "--mask", str(self.mask),
                     "--checkpoint", str(self.config.parent), "--upstream", str(self.upstream),
                     "--out", str(self.out), "--cuda-home", str(self.cuda)]
        self.env = patch.dict(os.environ, {"EXPECTED_CUDA": str(self.cuda),
                                           "NVCC_PREPEND_FLAGS": "", "NVCC_APPEND_FLAGS": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        old_path = sys.path[:]
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), old_path))
        self.addCleanup(lambda: sys.modules.pop("sam3d_inference_runtime", None))
        cuda = SimpleNamespace(is_available=lambda: True, synchronize=lambda: None,
                               reset_peak_memory_stats=lambda: None,
                               get_device_name=lambda _: "FAKE_GPU",
                               get_device_properties=lambda _: SimpleNamespace(total_memory=123),
                               max_memory_allocated=lambda: 40, max_memory_reserved=lambda: 60)
        fake_torch = SimpleNamespace(cuda=cuda, __version__="FAKE", version=SimpleNamespace(cuda="12.1"),
                                     is_tensor=lambda _: False)
        torch_patch = patch.dict(sys.modules, {"torch": fake_torch})
        torch_patch.start()
        self.addCleanup(torch_patch.stop)
        dist_patch = patch.object(wrapper.metadata, "distributions", return_value=[])
        dist_patch.start()
        self.addCleanup(dist_patch.stop)

    def report(self):
        return json.loads((self.out / "report.json").read_text())

    def test_validate_only_copies_originals_and_normalizes_without_runtime(self):
        with patch.object(wrapper, "load_runtime", side_effect=AssertionError("must not import GPU")):
            self.assertEqual(wrapper.run(wrapper.arguments(self.args + ["--validate-only"])), 0)
        self.assertEqual(self.report()["status"], "validated_only")
        self.assertEqual((self.out / "inputs/image.png").read_bytes(), self.image.read_bytes())
        with Image.open(self.out / "inputs/image_rgb.png") as image:
            self.assertEqual(image.mode, "RGB")
        receipt = json.loads((self.out / "inputs.json").read_text())
        self.assertEqual(receipt["mask_pixels"], 6)
        self.assertFalse((self.out / "runtime").exists())

    def test_empty_mask_and_mismatch_are_failed_preparation(self):
        for size in ((6, 4), (3, 3)):
            with self.subTest(size=size):
                Image.new("L", size).save(self.mask)
                args = self.args[:]
                output = self.root / f"bad-{size[0]}"
                args[args.index("--out") + 1] = str(output)
                with self.assertRaises(ValueError):
                    wrapper.run(wrapper.arguments(args + ["--validate-only"]))
                report = json.loads((output / "report.json").read_text())
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["stage"], "prepare_inputs")
                self.assertTrue((output / "error.txt").is_file())

    def test_reject_colored_overlay_in_auto_mode(self):
        Image.new("RGB", (6, 4), (40, 220, 120)).save(self.mask)
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            wrapper.run(wrapper.arguments(self.args + ["--validate-only"]))

    def test_repeated_rgb_mask_keeps_foreground(self):
        with Image.open(self.mask) as im:
            im.convert("RGB").save(self.root / "rgb.png")
        args = self.args[:]
        args[args.index("--mask") + 1] = str(self.root / "rgb.png")
        self.assertEqual(wrapper.run(wrapper.arguments(args)), 0)
        receipt = json.loads((self.out / "inputs.json").read_text())
        self.assertEqual(receipt["mask_pixels"], 6)
        self.assertEqual(receipt["mask_selected_channel"], "repeated RGB grayscale")

    def test_explicit_alpha_and_upstream_last_channel(self):
        with Image.open(self.mask) as im:
            alpha = np.array(im)
        rgba = np.zeros((4, 6, 4), dtype="uint8")
        rgba[..., :3] = [40, 220, 120]
        rgba[..., 3] = alpha
        Image.fromarray(rgba).save(self.mask)
        for channel in ("alpha", "last"):
            with self.subTest(channel=channel):
                args = self.args[:]
                args[args.index("--out") + 1] = str(self.root / channel)
                self.assertEqual(wrapper.run(wrapper.arguments(args + ["--mask-channel", channel])), 0)
                receipt = json.loads((self.root / channel / "inputs.json").read_text())
                self.assertEqual(receipt["mask_pixels"], 6)

    def test_refuse_existing_output_without_touching_it(self):
        self.out.mkdir()
        sentinel = self.out / "keep.txt"
        sentinel.write_text("keep")
        with self.assertRaises(FileExistsError):
            wrapper.run(wrapper.arguments(self.args))
        self.assertEqual(sentinel.read_text(), "keep")
        self.assertEqual(list(self.out.iterdir()), [sentinel])

    def test_full_control_flow_and_run_local_cuda_patch(self):
        original = (self.upstream / "notebook/inference.py").read_bytes()
        self.assertEqual(wrapper.run(wrapper.arguments(self.args)), 0)
        self.assertEqual(self.report()["status"], "completed")
        self.assertEqual((self.upstream / "notebook/inference.py").read_bytes(), original)
        self.assertEqual(self.report()["cuda_home"], str(self.cuda))
        for phase in ("preparation", "runtime_import", "model_init", "inference", "export", "end_to_end"):
            self.assertGreaterEqual(self.report()["timings_seconds"][phase], 0)
        pose = json.loads((self.out / "pose.json").read_text())
        self.assertFalse(pose["applied_to_glb_by_wrapper"])
        artifacts = json.loads((self.out / "artifacts.json").read_text())
        self.assertEqual(artifacts["object.glb"]["sha256"], wrapper.digest(self.out / "object.glb"))

    def test_stage_events_have_ordered_boundaries_and_clocks(self):
        wrapper.run(wrapper.arguments(self.args + ["--events"]))
        events = [json.loads(line) for line in (self.out / 'events.jsonl').read_text().splitlines()]
        phases = ['preparation', 'runtime_import', 'model_init', 'inference', 'export', 'artifact_receipt']
        self.assertEqual([(e['stage'], e['event']) for e in events],
                         [(phase, action) for phase in phases for action in ('start', 'end')])
        self.assertTrue(all(e['pid'] == os.getpid() for e in events))
        self.assertTrue(all(e['unix_seconds'] > 0 for e in events))
        self.assertEqual(sorted(e['monotonic_seconds'] for e in events), [e['monotonic_seconds'] for e in events])

    def test_stage_events_mark_preparation_failure(self):
        self.image.unlink()
        with self.assertRaises(FileNotFoundError):
            wrapper.run(wrapper.arguments(self.args + ['--events']))
        events = [json.loads(line) for line in (self.out / 'events.jsonl').read_text().splitlines()]
        self.assertEqual(events[-1]['stage'], 'preparation')
        self.assertEqual(events[-1]['status'], 'failed')

    def test_model_failure_retains_stage_and_traceback(self):
        with patch.dict(os.environ, {"FAKE_FAIL": "1"}):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                wrapper.run(wrapper.arguments(self.args + ['--events']))
        self.assertEqual(self.report()["status"], "failed")
        self.assertEqual(self.report()["stage"], "inference")
        events = [json.loads(line) for line in (self.out / 'events.jsonl').read_text().splitlines()]
        self.assertEqual(events[-1]['status'], 'failed')
        self.assertEqual(events[-1]['stage'], 'inference')
        self.assertIn("inference", self.report()["timings_seconds"])
        self.assertIn("synthetic", (self.out / "error.txt").read_text())
        self.assertFalse((self.out / "artifacts.json").exists())

    def test_optional_splat_and_source_metadata(self):
        source = self.root / "source.json"
        source.write_text('{"source_frame": 146}')
        args = self.args + ["--save-splat", "--input-metadata", str(source),
                            "--checkpoint-revision", "test-revision"]
        self.assertEqual(wrapper.run(wrapper.arguments(args)), 0)
        self.assertTrue((self.out / "splat.ply").is_file())
        receipt = json.loads((self.out / "inputs.json").read_text())
        self.assertEqual(receipt["source_metadata"]["source_frame"], 146)
        model = json.loads((self.out / "checkpoint.json").read_text())
        self.assertEqual(model["revision"], "test-revision")
        self.assertFalse(model["weight_contents_hashed"])

    def test_missing_mesh_is_export_failure_not_success(self):
        with patch.dict(os.environ, {"FAKE_NO_MESH": "1"}):
            with self.assertRaisesRegex(ValueError, "No exportable"):
                wrapper.run(wrapper.arguments(self.args))
        self.assertEqual(self.report()["status"], "failed")
        self.assertEqual(self.report()["stage"], "export")

    def test_unknown_upstream_initialization_fails_closed(self):
        (self.upstream / "notebook/inference.py").write_text("# changed upstream\n")
        with self.assertRaisesRegex(ValueError, "Unknown upstream"):
            wrapper.run(wrapper.arguments(self.args))
        self.assertEqual(self.report()["stage"], "runtime_import")


class LauncherTests(unittest.TestCase):
    def test_shell_syntax_and_missing_configuration(self):
        script = SCRIPT.parents[1] / "slurm/sam3d_objects.sbatch"
        subprocess.run(["bash", "-n", str(script)], check=True)
        env = dict(os.environ)
        env.pop("SAM3D_PROJECT_ROOT", None)
        result = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SAM3D_PROJECT_ROOT", result.stderr)


if __name__ == "__main__":
    unittest.main()
