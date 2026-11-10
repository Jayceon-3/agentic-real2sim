#!/usr/bin/env python3
"""Auditable, human-reviewed single-object workflow using existing model runtimes."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def envpath(name, default):
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


def runtimes():
    aha = envpath("AHA_ROOT", ROOT / "third_party/aha-3d")
    work = envpath("SAM3D_WORK", Path.home() / "eecs442_scratch/real2sim/sam3d-objects")
    sam = envpath("SAM3_RUNTIME", aha / ".runtime/sam3-segmentation")
    pi_default = aha / ".runtime/pi3x-inference/venv/bin/python"
    if not pi_default.exists() and (aha / ".runtime/pi3x/venv/bin/python").exists():
        pi_default = aha / ".runtime/pi3x/venv/bin/python"
    return {
        "aha": aha, "work": work, "sam3_runtime": sam,
        "sam3_python": envpath("SAM3_PY", sam / "venv/bin/python"),
        "pi3x_python": envpath("PI3X_PY", pi_default),
        "mesh_python": envpath("PI3X_MESH_PY", aha / ".runtime/pi3x-mesh/venv/bin/python"),
        "pi3x_upstream": envpath("PI3X_UPSTREAM", aha / "external/Pi3"),
        "pi3x_checkpoint": envpath("PI3X_CHECKPOINT", aha / ".runtime/pi3x/checkpoint/model.safetensors"),
        "object_python": envpath("SAM3D_ENV", work / "envs/sam3d-objects") / "bin/python",
        "object_upstream": envpath("SAM3D_SRC", work / "src/sam-3d-objects"),
        "object_config": envpath("MODEL_CONFIG", work / "checkpoints/hf-download/checkpoints/pipeline.yaml"),
        "cuda_home": envpath("SAM3D_CUDA_HOME", "/sw/pkgs/arc/cuda/12.1.1"),
    }


def require_file(path, executable=False):
    if not path.is_file() or (executable and not os.access(path, os.X_OK)):
        raise FileNotFoundError(f"{'Executable' if executable else 'File'} missing: {path}")


def inside(path, parent):
    path = Path(path).resolve()
    path.relative_to(Path(parent).resolve())
    return path


def process(command, cwd, stage):
    command = [str(x) for x in command]
    shutil.copyfile(__file__, stage / "workflow_snapshot.py")
    if len(command) > 1 and Path(command[1]).is_file() and command[1].endswith(".py"):
        shutil.copyfile(command[1], stage / "runner_snapshot.py")
    write(stage / "command.json", {"argv": command, "cwd": str(cwd),
                                   "workflow_sha256": sha(__file__)})
    print("Executing:", shlex.join(command), flush=True)
    with (stage / "console.log").open("x") as log:
        with subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors="replace") as child:
            try:
                for line in child.stdout:
                    log.write(line)
                    log.flush()
                    print(line, end="", flush=True)
                code = child.wait()
            except BaseException:
                child.terminate()
                child.wait()
                raise
        if code:
            raise subprocess.CalledProcessError(code, command)


class Case:
    def __init__(self, root, create=False):
        self.root = Path(root).expanduser().resolve()
        if create:
            self.root.mkdir(parents=True, exist_ok=False)
        self.state = (read(self.root / "case.json") if not create else
                      {"schema_version": 1, "status": "initializing", "history": []})

    def save(self):
        write(self.root / "case.json", self.state)

    @contextmanager
    def locked(self):
        with (self.root / ".workflow.lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another stage is writing this case; wait for it to finish")
            try:
                # Refresh after acquiring the lock, so stale state cannot replace newer work.
                if (self.root / "case.json").exists():
                    self.state = read(self.root / "case.json")
                yield self
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    @contextmanager
    def stage(self, name):
        identity = name + "-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        path = self.root / "stages" / identity
        path.mkdir(parents=True)
        record = {"stage": name, "path": str(path.relative_to(self.root)), "status": "running",
                  "started_at": datetime.now(timezone.utc).isoformat()}
        self.state["history"].append(record)
        self.state["status"] = name + "_running"
        self.save()
        started = time.perf_counter()
        try:
            yield path
            record["status"] = "completed"
            self.state["status"] = name + "_completed"
        except BaseException as error:
            record.update(status="failed", error=str(error))
            self.state["status"] = name + "_failed"
            (path / "error.txt").write_text(traceback.format_exc())
            raise
        finally:
            record["wall_seconds"] = time.perf_counter() - started
            record["finished_at"] = datetime.now(timezone.utc).isoformat()
            write(path / "stage.json", record)
            self.save()
            print("Stage artifacts:", path, flush=True)

    def pointer(self, name):
        value = self.state.get(name)
        if not value:
            raise ValueError(f"Case has no {name}; complete the preceding stage first")
        return inside(self.root / value, self.root)

    def verify_image(self):
        image = self.root / "source" / self.state["object_id"] / "image.png"
        if sha(image) != self.state["image_sha256"]:
            raise ValueError("Source image changed; create a new case instead")
        if sha(self.root / "source/manifest.json") != self.state["source_manifest_sha256"]:
            raise ValueError("Source frame manifest changed; create a new case")
        if sha(self.root / "sam3-request.json") != self.state["request_sha256"]:
            raise ValueError("Segmentation request changed; prepare a new case")
        return image


def prepare(args, rt):
    video = args.video.expanduser().resolve()
    require_file(video)
    require_file(rt["pi3x_python"], True)
    if (args.frame < 0 or not args.label.strip()
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.object_id)):
        raise ValueError("Use a nonnegative frame and a simple object ID without slashes")
    if args.bbox_relative:
        l, t, r, b = args.bbox_relative
        if not (0 <= l < r <= 1 and 0 <= t < b <= 1):
            raise ValueError("Relative bbox must be normalized left,top,right,bottom within [0,1]")
    case = Case(args.case, create=True)
    with case.locked(), case.stage("prepare") as stage:
        spec = {"id": args.object_id, "label": args.label,
                "source_video": str(video), "source_frame": args.frame}
        write(stage / "frame-request.json", {"objects": [spec]})
        script = rt["aha"] / "tools/object_pilot/prepare_inputs.py"
        require_file(script)
        process([rt["pi3x_python"], script, "--root", ROOT, "--frames-only",
                 "--config", stage / "frame-request.json", "--out", case.root / "source"],
                rt["aha"], stage)
        obj = read(case.root / "source/manifest.json")["objects"][0]
        w, h = obj["image_size"]
        bbox = args.bbox
        if args.bbox_relative:
            bbox = [round(x * scale) for x, scale in zip(args.bbox_relative, [w, h, w, h])]
        if bbox:
            l, t, r, b = bbox
            if not (0 <= l < r <= w and 0 <= t < b <= h):
                raise ValueError("Selection bbox must fit the decoded native image")
            obj["selection_bbox_xyxy"] = bbox
        write(case.root / "sam3-request.json", {"schema_version": 1, "objects": [obj]})
        case.state.update(object_id=args.object_id, label=args.label, video=str(video),
                          frame=args.frame, image_sha256=obj["image_sha256"],
                          video_sha256=obj["source_sha256"],
                          source_manifest_sha256=sha(case.root / "source/manifest.json"),
                          request_sha256=sha(case.root / "sam3-request.json"))
        if args.reference_build:
            reference = args.reference_build.expanduser().resolve()
            require_file(reference)
            case.state["existing_reference"] = {"path": str(reference), "sha256": sha(reference),
                                                "status": "linked_not_visually_validated"}
        print("Prepared native frame; next run segment, then inspect candidates before review-mask.")


def segment(case, args, rt):
    case.verify_image()
    for path in (rt["sam3_python"], rt["sam3_runtime"] / "checkpoints/sam3.pt",
                 rt["sam3_runtime"] / "runtime.json"):
        require_file(path, path == rt["sam3_python"])
    with case.stage("segment") as stage:
        script = rt["aha"] / "tools/object_pilot/segmentation/run.py"
        process([rt["sam3_python"], script, "--runtime", rt["sam3_runtime"],
                 "--manifest", case.root / "sam3-request.json", "--out", stage / "results"],
                rt["aha"], stage)
        manifest = stage / "results/manifest.json"
        report = read(manifest)
        obj = next(x for x in report["objects"] if x["id"] == case.state["object_id"])
        if obj["image_sha256"] != case.state["image_sha256"] or not obj["variants"]:
            raise ValueError("Segmentation input differs or has no candidates")
        files = {}
        for candidate in obj["variants"]:
            mask = inside(candidate["mask"], stage / "results")
            for path in (mask, mask.with_name(candidate["variant"] + "_overlay.jpg"),
                         mask.with_name(candidate["variant"] + "_cutout.png")):
                files[str(path.relative_to(stage))] = sha(path)
        write(stage / "segmentation_receipt.json", {"manifest_sha256": sha(manifest),
              "image_sha256": case.state["image_sha256"], "files": files,
              "review_status": "pending_human_review", "runner_sha256": sha(script)})
        case.state["latest_segmentation"] = str(stage.relative_to(case.root))
        print("STOP FOR HUMAN REVIEW: inspect results/*/*_overlay.jpg and *_cutout.png.")


def review_mask(case, args, rt):
    image = case.verify_image()
    segmentation = (inside(args.segmentation, case.root) if args.segmentation else
                    case.pointer("latest_segmentation"))
    receipt = read(segmentation / "segmentation_receipt.json")
    manifest = segmentation / "results/manifest.json"
    if sha(manifest) != receipt["manifest_sha256"] or receipt["image_sha256"] != sha(image):
        raise ValueError("Segmentation receipt does not match current inputs")
    obj = next(x for x in read(manifest)["objects"] if x["id"] == case.state["object_id"])
    candidate = next((x for x in obj["variants"] if x["variant"] == args.variant), None)
    if candidate is None:
        raise ValueError(f"Unknown candidate {args.variant}; inspect manifest.json")
    for relative, expected in receipt["files"].items():
        if sha(inside(segmentation / relative, segmentation)) != expected:
            raise ValueError("Segmentation artifact changed since generation: " + relative)
    with case.stage("review-mask") as stage:
        mask = inside(candidate["mask"], segmentation / "results")
        shutil.copyfile(mask, stage / "mask.png")
        metadata = dict(read(case.root / "source/manifest.json")["objects"][0])
        metadata.update(mask_method=obj["mask_method"], mask_review="human_visual_review",
                        selected_variant=args.variant, reviewer=args.reviewer, review_note=args.note,
                        segmentation_manifest=str(manifest), segmentation_manifest_sha256=sha(manifest),
                        mask_sha256=sha(stage / "mask.png"))
        write(stage / "source.json", metadata)
        write(stage / "review.json", {"reviewer": args.reviewer, "note": args.note,
              "variant": args.variant, "image_sha256": sha(image),
              "mask_sha256": sha(stage / "mask.png"),
              "source_metadata_sha256": sha(stage / "source.json"),
              "segmentation_receipt_sha256": sha(segmentation / "segmentation_receipt.json"),
              "reviewed_at": datetime.now(timezone.utc).isoformat()})
        case.state["selected_review"] = str(stage.relative_to(case.root))
        case.state["selected_review_sha256"] = sha(stage / "review.json")
        print("Selected", args.variant, "with an explicit human review record.")


def reviewed_inputs(case):
    image = case.verify_image()
    review = case.pointer("selected_review")
    if sha(review / "review.json") != case.state["selected_review_sha256"]:
        raise ValueError("Review record changed")
    receipt = read(review / "review.json")
    for path, key in ((image, "image_sha256"), (review / "mask.png", "mask_sha256"),
                      (review / "source.json", "source_metadata_sha256")):
        if sha(path) != receipt[key]:
            raise ValueError("Reviewed input changed: " + str(path))
    return image, review


def generate(case, args, rt):
    image, review = reviewed_inputs(case)
    require_file(rt["object_python"], True)
    require_file(rt["object_config"])
    with case.stage("validate" if args.validate_only else "generate") as stage:
        command = [rt["object_python"], ROOT / "scripts/sam3d_objects/infer.py",
                   "--image", image, "--mask", review / "mask.png",
                   "--input-metadata", review / "source.json", "--object-id", case.state["object_id"],
                   "--upstream", rt["object_upstream"], "--checkpoint", rt["object_config"],
                   "--cuda-home", rt["cuda_home"], "--seed", str(args.seed), "--out", stage / "results"]
        if args.save_splat:
            command.append("--save-splat")
        if args.validate_only:
            command.append("--validate-only")
        revision_file = rt["work"] / "logs/checkpoint_revision.txt"
        if revision_file.is_file():
            revision = revision_file.read_text().strip()
            if revision:
                command += ["--checkpoint-revision", revision]
        process(command, ROOT, stage)
        report = read(stage / "results/report.json")
        expected = "validated_only" if args.validate_only else "completed"
        if report.get("status") != expected:
            raise ValueError("Inference did not produce the expected completion report")
        key = "latest_validation" if args.validate_only else "latest_generation"
        case.state[key] = str(stage.relative_to(case.root))
        if not args.validate_only:
            case.state["generation_review_sha256"] = sha(review / "review.json")
            case.state.pop("latest_result_review", None)
            case.state.pop("latest_scene_import", None)
            case.state.pop("scene_import_receipt_sha256", None)
        print("Input validation complete." if args.validate_only else
              "GLB exported. Inspect it in Blender; generation is not visual acceptance.")


def import_scene(case, args, rt):
    if args.glb:
        if case.state.get("mode") != "import_only":
            raise ValueError("--glb requires a separate import-only case; omit it for generated cases")
        glb = args.glb.expanduser().resolve()
        generation = None
    else:
        generation = case.pointer("latest_generation")
        if read(generation / "results/report.json").get("status") != "completed":
            raise ValueError("Latest generation is not completed")
        glb = generation / "results/object.glb"
        if sha(glb) != read(generation / "results/artifacts.json")["object.glb"]["sha256"]:
            raise ValueError("Generated GLB changed after export")
    scene, placement = args.scene.expanduser().resolve(), args.placement.expanduser().resolve()
    for path in (glb, scene, placement):
        require_file(path)
    executable = args.blender or os.environ.get("BLENDER_BIN") or "blender"
    resolved = shutil.which(str(executable))
    if not resolved:
        raise FileNotFoundError("Blender executable missing; pass --blender or export BLENDER_BIN")
    blender = Path(resolved).resolve()
    # The controller runs on Linux/WSL; Windows Blender needs Windows file paths.
    windows = blender.suffix.lower() == ".exe"
    def blender_path(path):
        if windows:
            return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()
        return str(path)
    with case.stage("import-scene") as stage:
        inputs = stage / "inputs"
        inputs.mkdir()
        shutil.copyfile(glb, inputs / "object.glb")
        shutil.copyfile(placement, inputs / "placement.json")
        identities = {"scene": sha(scene), "glb": sha(inputs / "object.glb"),
                      "placement": sha(inputs / "placement.json")}
        if sha(glb) != identities["glb"] or sha(placement) != identities["placement"]:
            raise ValueError("Import inputs changed while copying")
        script = ROOT / "scripts/sam3d_objects/import_blender.py"
        shutil.copyfile(script, stage / "runner_snapshot.py")
        command = [blender, "--background", "--python-exit-code", "1",
                   "--python", blender_path(script), "--",
                   "--scene", blender_path(scene), "--glb", blender_path(inputs / "object.glb"),
                   "--placement", blender_path(inputs / "placement.json"),
                   "--object-id", args.object_id, "--out", blender_path(stage / "results")]
        if args.replace:
            command.append("--replace")
        process(command, ROOT, stage)
        report = read(stage / "results/import_report.json")
        if report.get("status") != "completed" or report.get("reopen_verified") is not True:
            raise ValueError("Blender import did not complete its reopen checks")
        if report.get("object_id") != args.object_id:
            raise ValueError("Blender report has a different object ID")
        for key, expected in identities.items():
            if report["inputs"][key]["sha256"] != expected:
                raise ValueError("Blender report input differs: " + key)
        if sha(scene) != identities["scene"]:
            raise ValueError("Source scene changed during import")
        if sha(stage / "results/scene.blend") != report["output"]["sha256"]:
            raise ValueError("Saved Blender scene differs from its report")
        files = {str(path.relative_to(stage)): sha(path) for path in
                 (inputs / "object.glb", inputs / "placement.json", stage / "results/scene.blend",
                  stage / "results/semantics.json", stage / "results/import_report.json")}
        write(stage / "import_receipt.json", {
            "generation": str(generation.relative_to(case.root)) if generation else None,
            "source_glb": str(glb), "source_scene": str(scene), "inputs_sha256": identities,
            "object_id": args.object_id, "files": files,
            "visual_review": "not_recorded", "scope": "static asset import; alignment not accepted"})
        case.state["latest_scene_import"] = str(stage.relative_to(case.root))
        case.state["scene_import_receipt_sha256"] = sha(stage / "import_receipt.json")
        print("Scene imported. Inspect placement and materials:", stage / "results/scene.blend")


def checked_scene_import(case):
    stage = case.pointer("latest_scene_import")
    if sha(stage / "import_receipt.json") != case.state["scene_import_receipt_sha256"]:
        raise ValueError("Scene import receipt changed")
    receipt = read(stage / "import_receipt.json")
    if receipt["generation"] != case.state.get("latest_generation"):
        raise ValueError("Scene import belongs to a different generation")
    for relative, expected in receipt["files"].items():
        if sha(inside(stage / relative, stage)) != expected:
            raise ValueError("Scene import artifact changed: " + relative)
    return stage


def reference(case, args, rt):
    # Optional room-reference preparation, independent of object generation.
    video = Path(case.state["video"])
    require_file(video)
    if sha(video) != case.state["video_sha256"]:
        raise ValueError("Source video changed since frame preparation")
    for key in ("pi3x_python", "mesh_python", "sam3_python"):
        require_file(rt[key], True)
    require_file(rt["pi3x_checkpoint"])
    with case.stage("reference") as stage:
        process([rt["pi3x_python"], "-m", "tools.layout_inspection.build_reference",
                 "--video", video, "--upstream", rt["pi3x_upstream"],
                 "--checkpoint", rt["pi3x_checkpoint"], "--pi3x-python", rt["pi3x_python"],
                 "--mesh-python", rt["mesh_python"], "--semantic-python", rt["sam3_python"],
                 "--semantic-runtime", rt["sam3_runtime"], "--num-frames", str(args.num_frames),
                 "--reference-views", "5", "--out", stage / "results"], rt["aha"], stage)
        require_file(stage / "results/reference_build.json")
        case.state["latest_reference"] = str(stage.relative_to(case.root))
        print("Reference generated; inspect overlays/floor separately. No authored room was built.")


def review_result(case, args, rt):
    generation = case.pointer("latest_generation")
    if read(generation / "results/report.json").get("status") != "completed":
        raise ValueError("Latest generation is not completed")
    artifact = read(generation / "results/artifacts.json")["object.glb"]
    if sha(generation / "results/object.glb") != artifact["sha256"]:
        raise ValueError("Generated GLB changed after export")
    with case.stage("review-result") as stage:
        write(stage / "review.json", {"reviewer": args.reviewer, "note": args.note,
              "verdict": args.verdict, "generation": str(generation.relative_to(case.root)),
              "glb_sha256": artifact["sha256"],
              "scope": "single generated asset; not room alignment or scene acceptance"})
        case.state["latest_result_review"] = str(stage.relative_to(case.root))


def bundle(case, args, rt):
    if case.state.get("mode") == "import_only":
        if args.kind != "result":
            raise ValueError("Import-only cases only support result bundles")
        selected = [case.root / "case.json", checked_scene_import(case)]
        return write_bundle(case, args, selected)
    case.verify_image()
    selected = [case.root / "case.json", case.root / "source", case.root / "sam3-request.json"]
    selected += [case.root / record["path"] for record in case.state["history"]
                 if record["stage"] == "prepare"]
    if args.kind == "review":
        selected.append(case.pointer("latest_segmentation"))
    else:
        reviewed_inputs(case)
        generation = case.pointer("latest_generation")
        selected += [generation, case.pointer("selected_review")]
        if case.state["generation_review_sha256"] != case.state["selected_review_sha256"]:
            raise ValueError("Latest mesh uses an older mask review; select matching results")
        artifacts = read(generation / "results/artifacts.json")
        for relative, identity in artifacts.items():
            if sha(inside(generation / "results" / relative, generation / "results")) != identity["sha256"]:
                raise ValueError("Generated artifact changed: " + relative)
        if case.state.get("latest_result_review"):
            selected.append(case.pointer("latest_result_review"))
        if case.state.get("latest_scene_import"):
            selected.append(checked_scene_import(case))
    write_bundle(case, args, selected)


def write_bundle(case, args, selected):
    output = args.out.expanduser().resolve()
    if output.is_relative_to(case.root):
        raise ValueError("Bundle path must be outside the case to avoid recursive archives")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation refuses overwrite, including partial archives from failures.
    with tarfile.open(output, "x:gz") as archive:
        for path in selected:
            archive.add(path, arcname=str(Path(case.root.name) / path.relative_to(case.root)))
    print("Download this archive with scp:", output)
    print("Bundle SHA256:", sha(output))


def doctor(args, rt):
    paths = {"SAM3D Python": rt["object_python"],
             "SAM3D inference entry": rt["object_upstream"] / "notebook/inference.py",
             "SAM3D pipeline": rt["object_config"], "CUDA nvcc": rt["cuda_home"] / "bin/nvcc",
             "SAM3 Python": rt["sam3_python"], "SAM3 checkpoint": rt["sam3_runtime"] / "checkpoints/sam3.pt",
             "SAM3 metadata": rt["sam3_runtime"] / "runtime.json", "Pi3X Python": rt["pi3x_python"]}
    if args.reference:
        paths.update({"Mesh Python": rt["mesh_python"], "Pi3X checkpoint": rt["pi3x_checkpoint"],
                      "Pi3X source": rt["pi3x_upstream"] / "pi3/models/pi3x.py"})
    missing = False
    for name, path in paths.items():
        ok = path.is_file() and (not name.endswith("Python") or os.access(path, os.X_OK))
        print(f"{'OK     ' if ok else 'MISSING'} {name}: {path}")
        missing |= not ok
    print("Path checks only; existing environments are not installed or modified.")
    return int(missing)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    d = commands.add_parser("doctor", help="Check configured existing runtime paths without models")
    d.add_argument("--reference", action="store_true", help="Also check full Pi3X/mesh dependencies")
    for name in ("prepare", "segment", "review-mask", "generate", "reference", "review-result", "import-scene", "bundle", "status"):
        sub = commands.add_parser(name)
        sub.add_argument("--case", type=Path, required=True)
        if name == "prepare":
            sub.add_argument("--video", type=Path, required=True)
            sub.add_argument("--frame", type=int, required=True, help="Zero-based native source frame")
            sub.add_argument("--object-id", required=True)
            sub.add_argument("--label", required=True, help="Text prompt sent to SAM3")
            boxes = sub.add_mutually_exclusive_group()
            boxes.add_argument("--bbox", type=float, nargs=4, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
            boxes.add_argument("--bbox-relative", type=float, nargs=4,
                               metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
            sub.add_argument("--reference-build", type=Path, help="Link an existing reference_build.json")
        elif name in ("review-mask", "review-result"):
            sub.add_argument("--reviewed", action="store_true", required=True,
                             help="Explicitly confirm that you inspected the actual images/asset")
            sub.add_argument("--reviewer", default=getpass.getuser())
            sub.add_argument("--note", required=True)
            if name == "review-mask":
                sub.add_argument("--variant", required=True)
                sub.add_argument("--segmentation", type=Path, help="Specific stage directory; defaults to latest")
            else:
                sub.add_argument("--verdict", choices=("usable", "reject"), required=True)
        elif name == "generate":
            sub.add_argument("--seed", type=int, default=42)
            sub.add_argument("--save-splat", action="store_true")
            sub.add_argument("--validate-only", action="store_true")
        elif name == "import-scene":
            sub.add_argument("--scene", type=Path, required=True)
            sub.add_argument("--placement", type=Path, required=True)
            sub.add_argument("--object-id", required=True, help="Scene instance_id, not segmentation ID")
            sub.add_argument("--blender", help="Executable path; defaults to BLENDER_BIN or PATH")
            sub.add_argument("--replace", action="store_true")
            sub.add_argument("--glb", type=Path, help="External GLB; creates/reuses a separate import-only case")
        elif name == "reference":
            sub.add_argument("--num-frames", type=int, choices=(32, 64), default=32)
        elif name == "bundle":
            sub.add_argument("--kind", choices=("review", "result"), required=True)
            sub.add_argument("--out", type=Path, required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    rt = runtimes()
    if args.command == "doctor":
        return doctor(args, rt)
    if args.command == "prepare":
        prepare(args, rt)
        return 0
    if args.command == "import-scene" and args.glb and not args.case.expanduser().exists():
        case = Case(args.case, create=True)
        case.state.update(mode="import_only", status="initialized")
        case.save()
    else:
        case = Case(args.case)
    if case.state.get("mode") == "import_only" and args.command not in ("import-scene", "bundle", "status"):
        raise ValueError("Import-only cases support import-scene, bundle and status; prepare a separate full case")
    if args.command == "status":
        print(json.dumps(case.state, indent=2))
        return 0
    if args.command in ("review-mask", "review-result") and not args.note.strip():
        raise ValueError("Record a nonempty observation, not only an acceptance flag")
    with case.locked():
        {"segment": segment, "review-mask": review_mask, "generate": generate,
         "reference": reference, "bundle": bundle, "review-result": review_result,
         "import-scene": import_scene}[args.command](case, args, rt)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"WORKFLOW_FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
