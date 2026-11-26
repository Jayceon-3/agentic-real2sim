"""CPU checks of frozen input binding, mixed-request reuse and score accounting."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


runner = module("office48_ab_test", HERE / "run.py")
fixtures = module("office48_wrapper_fixtures", ROOT / "scripts/tests/test_sam3d_objects.py")


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def lock(self):
        config = runner.read(HERE / "manifest.example.json")
        config["image_size"] = [6, 4]
        folder = self.root / "frozen"
        folder.mkdir()
        Image.new("RGB", (6, 4), (100, 120, 140)).save(folder / "image.png")
        data = np.zeros((4, 6), dtype="uint8")
        data[1:3, 1:4] = 255
        Image.fromarray(data).save(folder / "mask.png")
        Image.new("RGB", (6, 4), (200, 80, 60)).save(folder / "chair.png")
        video = self.root / "video.mp4"
        video.write_bytes(b"synthetic-video-identity")
        lock = {"status": "frozen", "protocol": config,
                "resources": {"video": {"path": "video.mp4", "sha256": runner.digest(video)}},
                "files": {p.name: runner.digest(p) for p in folder.glob("*.png")}, "objects": []}
        for obj in config["objects"]:
            entry = copy.deepcopy(obj)
            for frame, view in enumerate(entry["views"]):
                view.update(frame=frame, image="chair.png" if obj["id"] == "chair" else "image.png",
                            mask="mask.png", reviewed=True)
            lock["objects"].append(entry)
        path = folder / "lock.json"
        runner.write(path, lock)
        return path, lock

    def test_manifest_rejects_unreviewed_and_overlapping_views(self):
        config = runner.read(HERE / "manifest.example.json")
        with self.assertRaises(ValueError):
            runner.validate_manifest(config)
        for obj in config["objects"]:
            obj["identity_review"] = "Matched source object to its scene semantic root."
            for frame, view in enumerate(obj["views"]):
                view.update(frame=frame, reviewed=True)
        runner.validate_manifest(config)
        config["objects"][0]["views"][-1]["frame"] = 0
        with self.assertRaisesRegex(ValueError, "disjoint"):
            runner.validate_manifest(config)

    def test_input_tamper_rejected_before_generation(self):
        path, lock = self.lock()
        (path.parent / "mask.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Frozen input changed"):
            runner.load_lock(path, self.root)

    def test_freeze_binds_extracted_frames_masks_and_source_resources(self):
        config = runner.read(HERE / "manifest.example.json")
        for key in ("video", "scene", "camera"):
            resource = self.root / key
            resource.write_bytes(key.encode())
            config[key] = key
        config["video_sha256"] = runner.digest(self.root / "video")
        config["frames_dir"] = "frames"
        frames = self.root / "frames"
        frames.mkdir()
        receipt = {"status": "completed", "video_sha256": config["video_sha256"], "frames": {}}
        for frame in range(6):
            rgb = frames / runner.frame_name(frame)
            Image.new("RGB", (1280, 720)).save(rgb)
            receipt["frames"][str(frame)] = {"sha256": runner.digest(rgb)}
        runner.write(frames / "frames.json", receipt)
        mask = self.root / "target.png"
        Image.new("L", (1280, 720), 255).save(mask)
        for obj in config["objects"]:
            obj["identity_review"] = "Source identity reviewed."
            for frame, view in enumerate(obj["views"]):
                view.update(frame=frame, mask="target.png", reviewed=True)
        manifest = self.root / "manifest.json"
        runner.write(manifest, config)
        args = SimpleNamespace(root=self.root, manifest=manifest, out=self.root / "frozen")
        runner.freeze(args)
        lock = runner.load_lock(args.out / "lock.json", self.root)
        self.assertEqual(len(lock["files"]), 24)
        self.assertEqual(len(lock["objects"]), 2)
        # Original annotations can move after freezing; snapshot bytes remain bound.
        mask.write_bytes(b"original changed after snapshot")
        runner.load_lock(args.out / "lock.json", self.root)
        (self.root / "scene").write_bytes(b"scene changed")
        with self.assertRaisesRegex(ValueError, "Source resource changed"):
            runner.load_lock(args.out / "lock.json", self.root)

    def test_real_wrapper_handles_two_inputs_three_seeds_with_one_model(self):
        fixture = fixtures.WrapperTests("test_full_control_flow_and_run_local_cuda_patch")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        wrapper = fixtures.wrapper
        path, lock = self.lock()
        calls = []
        class Mesh:
            def export(self, path):
                Path(path).write_bytes(b"fake-glb")
        class Model:
            def __init__(self, *args, **kwargs):
                calls.append("initialized")
            def __call__(self, image, mask, seed):
                calls.append((int(image[0, 0, 0]), seed))
                return {"glb": Mesh(), "rotation": [1, 0, 0, 0],
                        "translation": [0, 0, 0], "scale": [1, 1, 1]}
        fake_cuda = sys.modules["torch"].cuda
        fake_cuda.memory_allocated = lambda: 100
        fake_cuda.memory_reserved = lambda: 200
        args = SimpleNamespace(lock=path, root=self.root, out=self.root / "generated",
                               upstream=fixture.upstream, checkpoint=fixture.config,
                               cuda_home=fixture.cuda, validate_only=False)
        import os
        with patch.dict(os.environ, {"CUDA_HOME": str(fixture.cuda)}), \
                patch.object(runner, "wrapper_module", return_value=wrapper), \
                patch.object(wrapper, "load_runtime", return_value=SimpleNamespace(Inference=Model)) as load:
            runner.generate(args)
        self.assertEqual(calls, ["initialized", (100, 42), (200, 42),
                                (100, 43), (200, 43), (100, 44), (200, 44)])
        self.assertEqual(load.call_count, 1)
        report = runner.read(args.out / "batch.json")
        self.assertEqual(report["status"], "completed")
        self.assertEqual([r["reused"] for r in report["requests"]], [False] + [True] * 5)
        with self.assertRaises(FileExistsError):
            runner.generate(args)

    def test_failure_keeps_partial_batch_and_stops_remaining_requests(self):
        path, lock = self.lock()
        args = SimpleNamespace(lock=path, root=self.root, out=self.root / "failed",
                               upstream=self.root, checkpoint=self.root, cuda_home=None, validate_only=True)
        fake = SimpleNamespace(InferenceSession=lambda: object(), arguments=lambda argv: argv,
                               run=lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("failed request")))
        with patch.object(runner, "wrapper_module", return_value=fake):
            with self.assertRaisesRegex(RuntimeError, "failed request"):
                runner.generate(args)
        report = runner.read(args.out / "batch.json")
        self.assertEqual(report["status"], "failed_or_interrupted")
        self.assertEqual(len(report["requests"]), 1)
        self.assertEqual(report["requests"][0]["status"], "failed_or_interrupted")
        self.assertTrue((args.out / "error.txt").exists())

    def test_score_uses_full_raster_ignore_regions_and_macro_view_mean(self):
        path, lock = self.lock()
        ignored = np.zeros((4, 6), dtype="uint8")
        ignored[0, 0] = 255
        Image.fromarray(ignored).save(path.parent / "ignore.png")
        lock["files"]["ignore.png"] = runner.digest(path.parent / "ignore.png")
        for view in lock["objects"][0]["views"]:
            view["ignore"] = "ignore.png"
        runner.write(path, lock)
        renders = self.root / "renders"
        renders.mkdir()
        record = {"status": "completed", "lock_sha256": runner.digest(path), "object": "cabinet",
                  "role": "evaluation", "label": "B-seed-42", "scene_sha256": "test-scene", "views": []}
        for frame in (3, 4, 5):
            data = np.array(Image.open(path.parent / "mask.png"))
            data[0, 0] = 255  # Ignored false positive must not affect IoU.
            if frame == 5:
                data[1, 1:4] = 0  # Three of six GT pixels remain.
            mask = renders / f"{frame}.png"
            Image.fromarray(data).save(mask)
            record["views"].append({"frame": frame, "mask": mask.name, "mask_sha256": runner.digest(mask)})
        runner.write(renders / "render.json", record)
        args = SimpleNamespace(lock=path, root=self.root, renders=renders, out=self.root / "scores")
        runner.score(args)
        scores = runner.read(args.out / "scores.json")
        self.assertAlmostEqual(scores["mean_iou"], (1 + 1 + .5) / 3)
        record["views"].pop()
        runner.write(renders / "render.json", record)
        args.out = self.root / "incomplete"
        with self.assertRaisesRegex(ValueError, "every preregistered"):
            runner.score(args)

    def test_summary_separates_methods_and_rejects_duplicate_runs(self):
        paths = []
        for index, (label, value) in enumerate([("A-run-1", .4), ("B-seed-42", .8), ("B-seed-43", .6)]):
            path = self.root / f"score-{index}.json"
            runner.write(path, {"object": "chair", "role": "evaluation", "lock_sha256": "same",
                                "label": label, "mean_iou": value})
            paths.append(path)
        args = SimpleNamespace(scores=paths, out=self.root / "summary")
        runner.summarize(args)
        groups = runner.read(args.out / "summary.json")["groups"]
        self.assertEqual([g["scored_runs"] for g in groups], [1, 2])
        self.assertAlmostEqual(groups[1]["mean_iou"], .7)
        args.scores.append(paths[-1])
        args.out = self.root / "duplicate"
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            runner.summarize(args)


if __name__ == "__main__":
    unittest.main()
