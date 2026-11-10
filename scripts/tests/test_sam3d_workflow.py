"""CPU orchestration tests with stand-in decoders/models, not real GPU inference."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "sam3d_objects/workflow.py"
spec = importlib.util.spec_from_file_location("sam3d_workflow_test", SCRIPT)
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)

PREPARE = '''import argparse, json, hashlib
from pathlib import Path
from PIL import Image
p=argparse.ArgumentParser()
p.add_argument('--root'); p.add_argument('--frames-only', action='store_true')
p.add_argument('--config'); p.add_argument('--out')
a=p.parse_args(); out=Path(a.out); out.mkdir()
obj=json.loads(Path(a.config).read_text())['objects'][0]
target=out/obj['id']; target.mkdir()
image=target/'image.png'; Image.new('RGB',(10,6),(120,90,50)).save(image)
obj.update(image=str(image), image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
           image_size=[10,6], source_fps=30, source_timestamp_seconds=obj['source_frame']/30,
           source_sha256=hashlib.sha256(Path(obj['source_video']).read_bytes()).hexdigest())
(out/'manifest.json').write_text(json.dumps({'objects':[obj]}))
'''

SEGMENT = '''import argparse,json,hashlib
from pathlib import Path
from PIL import Image
p=argparse.ArgumentParser(); p.add_argument('--runtime');p.add_argument('--manifest');p.add_argument('--out')
a=p.parse_args(); out=Path(a.out);out.mkdir()
obj=json.loads(Path(a.manifest).read_text())['objects'][0]
target=out/obj['id'];target.mkdir()
mask=target/'text_0_mask.png';Image.new('L',(10,6),255).save(mask)
Image.new('RGB',(10,6)).save(target/'text_0_overlay.jpg')
Image.new('RGB',(10,6)).save(target/'text_0_cutout.png')
obj.update(mask_method='fake SAM3', variants=[{'variant':'text_0','mask':str(mask)}])
(out/'manifest.json').write_text(json.dumps({'objects':[obj]}))
'''


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.case = self.root / "case"
        self.video = self.root / "source.mp4"
        self.video.write_bytes(b"stand-in video; decoder replaced in this test")
        aha = self.root / "aha"
        (aha / "tools/object_pilot/segmentation").mkdir(parents=True)
        (aha / "tools/object_pilot/prepare_inputs.py").write_text(PREPARE)
        (aha / "tools/object_pilot/segmentation/run.py").write_text(SEGMENT)
        sam = self.root / "sam"
        (sam / "checkpoints").mkdir(parents=True)
        (sam / "checkpoints/sam3.pt").write_bytes(b"fixture")
        (sam / "runtime.json").write_text('{}')
        config = self.root / "pipeline.yaml"
        config.write_text("fixture: true")
        self.rt = {"aha": aha, "work": self.root, "pi3x_python": Path(sys.executable),
                   "sam3_python": Path(sys.executable), "sam3_runtime": sam,
                   "object_python": Path(sys.executable), "object_upstream": self.root,
                   "object_config": config, "cuda_home": self.root}
        runtime_patch = patch.object(workflow, "runtimes", return_value=self.rt)
        runtime_patch.start()
        self.addCleanup(runtime_patch.stop)

    def call(self, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return workflow.main([str(x) for x in args])

    def prepare(self):
        self.call("prepare", "--case", self.case, "--video", self.video, "--frame", "0",
                  "--object-id", "cabinet", "--label", "wooden cabinet",
                  "--bbox-relative", ".8", ".1", ".99", ".64")

    def segment(self):
        self.prepare()
        self.call("segment", "--case", self.case)

    def review(self):
        self.segment()
        self.call("review-mask", "--case", self.case, "--variant", "text_0", "--reviewed",
                  "--reviewer", "test-human", "--note", "Inspected the actual overlay")

    def state(self):
        return workflow.read(self.case / "case.json")

    def fake_generation(self, command, cwd, stage):
        destination = Path(command[command.index("--out") + 1])
        destination.mkdir()
        validated = "--validate-only" in command
        workflow.write(destination / "report.json", {"status": "validated_only" if validated else "completed"})
        if not validated:
            (destination / "object.glb").write_bytes(b"GLB fixture")
            workflow.write(destination / "artifacts.json", {
                "object.glb": {"sha256": workflow.sha(destination / "object.glb")}})

    def test_prepare_extracts_native_frame_and_scales_selection_box(self):
        self.prepare()
        obj = workflow.read(self.case / "sam3-request.json")["objects"][0]
        self.assertEqual(obj["selection_bbox_xyxy"], [8, 1, 10, 4])
        self.assertEqual(self.state()["status"], "prepare_completed")
        with self.assertRaises(FileExistsError):
            self.prepare()

    def import_args(self):
        scene, placement = self.root / 'room.blend', self.root / 'placement.json'
        scene.write_bytes(b'scene fixture')
        placement.write_text('{}')
        return ['import-scene', '--case', self.case, '--scene', scene,
                '--placement', placement, '--object-id', 'furniture/cabinet',
                '--blender', sys.executable]

    def fake_import(self, command, cwd, stage):
        destination = Path(command[command.index('--out') + 1])
        destination.mkdir()
        (destination / 'scene.blend').write_bytes(b'imported scene fixture')
        workflow.write(destination / 'semantics.json', {})
        workflow.write(destination / 'import_report.json', {
            'status': 'completed', 'reopen_verified': True, 'object_id': 'furniture/cabinet',
            'inputs': {key: {'sha256': workflow.sha(command[command.index('--' + key) + 1])}
                       for key in ('scene', 'glb', 'placement')},
            'output': {'sha256': workflow.sha(destination / 'scene.blend')}})

    def test_import_generation_bundle_and_invalidate_on_regeneration(self):
        self.review()
        with patch.object(workflow, 'process', side_effect=self.fake_generation):
            self.call('generate', '--case', self.case)
        with patch.object(workflow, 'process', side_effect=self.fake_import):
            self.call(*self.import_args())
        stage = self.case / self.state()['latest_scene_import']
        receipt = workflow.read(stage / 'import_receipt.json')
        self.assertEqual(receipt['generation'], self.state()['latest_generation'])
        archive = self.root / 'scene.tar.gz'
        self.call('bundle', '--case', self.case, '--kind', 'result', '--out', archive)
        with tarfile.open(archive) as tar:
            self.assertTrue(any(name.endswith('/results/scene.blend') for name in tar.getnames()))
        with patch.object(workflow, 'process', side_effect=self.fake_generation):
            self.call('generate', '--case', self.case)
        self.assertNotIn('latest_scene_import', self.state())
        self.assertTrue(stage.is_dir())

    def test_external_glb_import_case_and_tampered_scene(self):
        glb = self.root / 'external.glb'
        glb.write_bytes(b'external GLB')
        with patch.object(workflow, 'process', side_effect=self.fake_import):
            self.call(*self.import_args(), '--glb', glb)
        self.assertEqual(self.state()['mode'], 'import_only')
        self.call('bundle', '--case', self.case, '--kind', 'result', '--out', self.root / 'external.tar.gz')
        stage = self.case / self.state()['latest_scene_import']
        (stage / 'results/scene.blend').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            self.call('bundle', '--case', self.case, '--kind', 'result', '--out', self.root / 'bad.tar.gz')
        with self.assertRaisesRegex(ValueError, 'Import-only'):
            self.call('generate', '--case', self.case)

    def test_import_failure_not_selected_and_retry_preserved(self):
        glb = self.root / 'external.glb'
        glb.write_bytes(b'external GLB')
        args = self.import_args() + ['--glb', glb]
        with patch.object(workflow, 'process', side_effect=subprocess.CalledProcessError(1, ['blender'])):
            with self.assertRaises(subprocess.CalledProcessError):
                self.call(*args)
        failed = self.state()['history'][-1]['path']
        self.assertNotIn('latest_scene_import', self.state())
        with patch.object(workflow, 'process', side_effect=self.fake_import):
            self.call(*args)
        self.assertNotEqual(failed, self.state()['latest_scene_import'])
        self.assertTrue((self.case / failed / 'error.txt').is_file())

    def test_changed_generation_rejected_before_blender(self):
        self.review()
        with patch.object(workflow, 'process', side_effect=self.fake_generation):
            self.call('generate', '--case', self.case)
        (self.case / self.state()['latest_generation'] / 'results/object.glb').write_bytes(b'changed')
        with patch.object(workflow, 'process') as process:
            with self.assertRaisesRegex(ValueError, 'GLB changed'):
                self.call(*self.import_args())
            process.assert_not_called()

    def test_no_generation_before_explicit_review(self):
        self.segment()
        with self.assertRaisesRegex(ValueError, "selected_review"):
            self.call("generate", "--case", self.case)
        with self.assertRaisesRegex(ValueError, "nonempty"):
            self.call("review-mask", "--case", self.case, "--variant", "text_0", "--reviewed", "--note", " ")
        self.assertNotIn("selected_review", self.state())

    def test_review_hashes_block_changed_mask(self):
        self.review()
        selected = self.case / self.state()["selected_review"]
        (selected / "mask.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Reviewed input changed"):
            self.call("generate", "--case", self.case)

    def test_changed_segmentation_image_or_request_is_rejected(self):
        self.segment()
        segmentation = self.case / self.state()["latest_segmentation"]
        mask = segmentation / "results/cabinet/text_0_mask.png"
        mask.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "artifact changed"):
            self.call("review-mask", "--case", self.case, "--variant", "text_0", "--reviewed", "--note", "review")
        (self.case / "sam3-request.json").write_text('{}')
        with self.assertRaisesRegex(ValueError, "request changed"):
            self.call("segment", "--case", self.case)

    def test_validation_does_not_select_a_generation(self):
        self.review()
        with patch.object(workflow, "process", side_effect=self.fake_generation):
            self.call("generate", "--case", self.case, "--validate-only")
        self.assertIn("latest_validation", self.state())
        self.assertNotIn("latest_generation", self.state())

    def test_result_review_and_bundle_preserve_artifacts(self):
        self.review()
        with patch.object(workflow, "process", side_effect=self.fake_generation):
            self.call("generate", "--case", self.case, "--save-splat")
        self.call("review-result", "--case", self.case, "--reviewed", "--verdict", "usable",
                  "--note", "Inspected mesh from front and side")
        output = self.root / "bundle.tar.gz"
        self.call("bundle", "--case", self.case, "--kind", "result", "--out", output)
        with tarfile.open(output) as archive:
            names = archive.getnames()
            self.assertTrue(any(x.endswith("object.glb") for x in names))
            self.assertIn("case/source/cabinet/image.png", names)
        with self.assertRaises(FileExistsError):
            self.call("bundle", "--case", self.case, "--kind", "result", "--out", output)

    def test_new_generation_does_not_inherit_old_visual_review(self):
        self.review()
        with patch.object(workflow, "process", side_effect=self.fake_generation):
            self.call("generate", "--case", self.case)
            self.call("review-result", "--case", self.case, "--reviewed", "--verdict", "usable",
                      "--note", "Inspected first output")
            self.assertIn("latest_result_review", self.state())
            self.call("generate", "--case", self.case)
        self.assertNotIn("latest_result_review", self.state())

    def test_changed_source_manifest_cannot_change_frame_provenance(self):
        self.review()
        source = self.case / "source/manifest.json"
        data = workflow.read(source)
        data["objects"][0]["source_frame"] = 99
        workflow.write(source, data)
        with self.assertRaisesRegex(ValueError, "Source frame manifest changed"):
            self.call("generate", "--case", self.case)

    def test_failed_process_is_recorded_and_retry_gets_new_directory(self):
        self.prepare()
        original = workflow.process
        with patch.object(workflow, "process", side_effect=subprocess.CalledProcessError(7, ["fixture"])):
            with self.assertRaises(subprocess.CalledProcessError):
                self.call("segment", "--case", self.case)
        self.assertEqual(self.state()["history"][-1]["status"], "failed")
        failed = self.case / self.state()["history"][-1]["path"]
        self.assertTrue((failed / "error.txt").exists())
        with patch.object(workflow, "process", side_effect=original):
            self.call("segment", "--case", self.case)
        self.assertNotEqual(self.state()["latest_segmentation"], str(failed.relative_to(self.case)))

    def test_case_lock_blocks_parallel_writer(self):
        self.prepare()
        first, second = workflow.Case(self.case), workflow.Case(self.case)
        with first.locked():
            with self.assertRaisesRegex(RuntimeError, "Another stage"):
                with second.locked():
                    self.fail("Second writer acquired lock")

    def test_review_bundle_available_before_mask_selection(self):
        self.segment()
        output = self.root / "review.tar.gz"
        self.call("bundle", "--case", self.case, "--kind", "review", "--out", output)
        with tarfile.open(output) as archive:
            self.assertTrue(any(x.endswith("text_0_overlay.jpg") for x in archive.getnames()))
        self.assertNotIn("selected_review", self.state())


class ShellToolsTests(unittest.TestCase):
    def test_paths_default_and_machine_override(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "machine.sh"
            config.write_text('export SAM3D_WORK="/tmp/custom-runtime"\nexport SAM3_PY="/tmp/custom-sam/bin/python"\n')
            env = dict(os.environ)
            for name in ("SAM3D_WORK", "SAM3D_ENV", "SAM3D_SRC", "MODEL_CONFIG"):
                env.pop(name, None)
            env["SAM3D_MACHINE_CONFIG"] = str(config)
            paths = SCRIPT.with_name("paths.sh")
            result = subprocess.run(["bash", "-c", 'source "$1"; printf "%s\\n%s\\n" "$SAM3D_WORK" "$SAM3_PY"',
                                     "test", str(paths)], env=env, text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.splitlines(), ["/tmp/custom-runtime", "/tmp/custom-sam/bin/python"])

    def test_gpu_script_refuses_nested_allocation(self):
        env = dict(os.environ, SLURM_JOB_ID="123")
        result = subprocess.run(["bash", str(SCRIPT.with_name("gpu.sh"))],
                                env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Already inside", result.stderr)

    def test_batch_launcher_preserves_arguments_and_failure_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fake = root / "srun"
            fake.write_text(f'#!{sys.executable}\nimport sys,json\nfrom pathlib import Path\n'
                            f'Path({str(root / "argv.json")!r}).write_text(json.dumps(sys.argv[1:]))\n'
                            'raise SystemExit(37)\n')
            fake.chmod(0o755)
            project = SCRIPT.parents[2]
            script = SCRIPT.parents[1] / "slurm/sam3d_workflow.sbatch"
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                       SAM3D_PROJECT_ROOT=str(project), SLURM_JOB_ID="fixture-job")
            result = subprocess.run(["bash", str(script), "generate", "--case", "/tmp/case with space"],
                                    cwd=folder, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 37)
            args = json.loads((root / "argv.json").read_text())
            self.assertEqual(args, ["bash", "scripts/sam3d_objects/run.sh", "generate",
                                    "--case", "/tmp/case with space"])

    def test_interactive_launcher_requests_and_enters_one_allocation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fake = root / "salloc"
            fake.write_text(f'#!{sys.executable}\nimport sys,json\nfrom pathlib import Path\n'
                            f'Path({str(root / "argv.json")!r}).write_text(json.dumps(sys.argv[1:]))\n')
            fake.chmod(0o755)
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"])
            env.pop("SLURM_JOB_ID", None)
            subprocess.run(["bash", str(SCRIPT.with_name("gpu.sh")), "--time=01:00:00"],
                           env=env, capture_output=True, text=True, check=True)
            args = json.loads((root / "argv.json").read_text())
            self.assertIn("--gres=gpu:a40:1", args)
            self.assertIn("--time=01:00:00", args)
            self.assertEqual(args[-4:], ["srun", "--pty", "bash", "-l"])


if __name__ == "__main__":
    unittest.main()
