"""Encode, fully decode and package an explicitly preliminary office48 review copy."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def run(args):
    return subprocess.run([str(v) for v in args], check=True, capture_output=True, text=True, timeout=180)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--ffmpeg", type=Path, required=True)
    p.add_argument("--ffprobe", type=Path, required=True)
    a = p.parse_args()
    out = (ROOT / a.run).resolve()
    package = out / "package"
    if (package / "manifest.json").exists():
        raise ValueError("Package already finalized; preserve it and use a new version")
    setup = json.loads((out / "scene_setup.json").read_text())
    rendered = json.loads((out / "frame_render.json").read_text())
    scene = package / "office48_preview.blend"
    if sha(scene) != setup["preview_scene_sha256"] or rendered["scene_sha256"] != setup["preview_scene_sha256"]:
        raise ValueError("Scene/render binding differs")
    frames = out / "work/frames"
    expected = [f"{i:04d}.png" for i in range(1,304)]
    if sorted(p.name for p in frames.glob("*.png")) != expected:
        raise ValueError("Expected all 303 rendered frames, without extras")
    for name in expected:
        with Image.open(frames / name) as im:
            im.load()
            if im.size != (1280,720):
                raise ValueError("Frame raster differs: " + name)
    video = package / "office48_preview.mp4"
    run([a.ffmpeg,"-hide_banner","-loglevel","error","-y","-framerate","30",
         "-start_number","1","-i",frames/"%04d.png","-frames:v","303",
         "-vf","setsar=1","-c:v","libx264","-crf","18","-preset","medium",
         "-pix_fmt","yuv420p","-movflags","+faststart","-an",video])
    run([a.ffmpeg,"-hide_banner","-loglevel","error","-xerror","-i",video,"-f","null","-"])
    probe=json.loads(run([a.ffprobe,"-v","error","-count_frames","-show_streams","-show_format","-of","json",video]).stdout)
    stream=next(s for s in probe['streams'] if s['codec_type']=='video')
    count=int(stream['nb_read_frames']);fps=Fraction(stream['avg_frame_rate']);duration=float(probe['format']['duration'])
    if count!=303 or fps!=30 or (stream['width'],stream['height'])!=(1280,720) or abs(duration-10.1)>.01:
        raise ValueError('Encoded video timing/raster failed validation')
    if any(s['codec_type']=='audio' for s in probe['streams']):
        raise ValueError('Unexpected audio stream')
    validation=dict(status='technical checks passed; fidelity acceptance deferred',
                    full_decode_pass=True,decoded_frames=count,fps=str(fps),duration_seconds=duration,
                    width=1280,height=720,codec=stream['codec_name'],pixel_format=stream['pix_fmt'],
                    video_sha256=sha(video),scene_sha256=sha(scene),all_render_pngs_decoded=True,
                    camera_check=setup['camera_after_reopen'],scene_external_dependencies=0,
                    baseline_accepted=False,source_fidelity_repairs='deferred by explicit user request',
                    render_settings=setup['settings'],render_seconds=rendered['render_seconds'],
                    ffmpeg_version=run([a.ffmpeg,'-version']).stdout.splitlines()[0],
                    visual_coverage='Representative source times; full decode is technical, not a full visual acceptance')
    (package/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    comparisons=package/'comparisons';comparisons.mkdir()
    sheet=Image.new('RGB',(1280,388*5),(25,28,32));draw=ImageDraw.Draw(sheet)
    for row,source_id in enumerate([0,78,146,224,302]):
        source=Image.open(ROOT/f'outputs/office48-review/source_views/source_{source_id:06d}_source.png').convert('RGB').resize((640,360),Image.Resampling.LANCZOS)
        model=Image.open(frames/f'{source_id+1:04d}.png').convert('RGB').resize((640,360),Image.Resampling.LANCZOS)
        y=row*388;draw.text((8,y+8),f'Source {source_id} / {source_id/30:.3f}s (resized display)',fill='white')
        draw.text((648,y+8),'Preliminary review render - source-fidelity repairs deferred',fill='white')
        sheet.paste(source,(0,y+28));sheet.paste(model,(640,y+28))
    sheet.save(comparisons/'source_vs_preview.jpg',quality=92)
    shutil.copy2(ROOT/'outputs/office48-baseline-001/evidence/comparisons-v006/cutaways.jpg',comparisons/'plan_front_side.jpg')
    # Decode separate samples from the encoded video, not only the input PNGs.
    decoded=out/'decoded-review';decoded.mkdir(exist_ok=False)
    run([a.ffmpeg,'-hide_banner','-loglevel','error','-i',video,'-vf','fps=1','-vsync','0',decoded/'sample_%02d.png'])
    samples=sorted(decoded.glob('sample_*.png'))
    contact=Image.new('RGB',(1280,382*((len(samples)+1)//2)),(25,28,32));draw=ImageDraw.Draw(contact)
    for i,path in enumerate(samples):
        with Image.open(path) as im:im.load();image=im.convert('RGB').resize((640,360),Image.Resampling.LANCZOS)
        x=(i%2)*640;y=(i//2)*382
        draw.text((x+8,y+6),f'Encoded MP4 decoded sample {i+1}',fill='white');contact.paste(image,(x,y+22))
    contact.save(out/'encoded_video_contact_sheet.jpg',quality=90)
    (package/'README.md').write_text('''# Office48 preliminary review copy

This package is for viewing the current reconstruction before source-fidelity
repairs. It is not the accepted baseline result.

- Play `office48_preview.mp4`: full source timeline, 303 frames, 30 fps, 1280 x 720,
  10.1 seconds, no audio. Rendered with EEVEE for quick material review.
- Open `office48_preview.blend` with Blender 5.2.1 or a compatible release. All
  authored geometry/materials and the baked camera are included. No model weights,
  cached NPZ files or source video are needed to open it. Timeline: frames 1-303.
- `comparisons/source_vs_preview.jpg` compares five source times with this video.
- `comparisons/plan_front_side.jpg` shows diagnostic cutaways, not final camera views.
- `keyframes/` contains three full-resolution representative renders.
- `validation.json` records actual full video decoding, timing and camera checks.

Known issues: exterior is unmodeled; materials and small props are simplified;
collar ties and some furniture silhouettes need source-based refinement. These
issues were intentionally deferred for this review copy and remain open in the
original experiment. Technical checks do not establish source fidelity.

Static architecture/furniture only; source people are excluded. Cameras are
interpolated estimates from 32 observations. Scale is uncalibrated predicted metres.
Physics diagnostics do not certify robot simulation or dynamic stability.

Source attribution: https://github.com/KevinXu02/aha-3d
Experiment: office48-baseline-001, authored candidate furnished-v006.
''')
    (package/'known_issues.json').write_text(json.dumps(json.loads((ROOT/'experiments/office48-baseline-001/findings-v006.json').read_text())['findings'],indent=2)+'\n')
    provenance=dict(experiment_id='office48-baseline-001',status='preliminary_review_copy',accepted=False,
                    source_scene='furnished-v006',source_scene_sha256=setup['source_scene_sha256'],
                    renderer_script_sha256=setup['script_sha256'],packaging_script_sha256=sha(Path(__file__)),
                    input_lock_sha256=sha(ROOT/'experiments/office48-baseline-001/inputs.lock.json'),
                    blender_version=setup['blender_version'],render_settings=setup['settings'],
                    source_video_sha256=json.loads((ROOT/'experiments/office48-baseline-001/inputs.lock.json').read_text())['source']['sha256'],
                    user_scope='View current deliverable version first; defer source-fidelity fixes without closing findings')
    (package/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    artifacts=[dict(path=str(p.relative_to(package)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(package.rglob('*')) if p.is_file()]
    manifest=dict(status='PRELIMINARY_NOT_ACCEPTED',artifacts=artifacts,validation='validation.json',known_issues='known_issues.json')
    (package/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    archive=out/'office48_preliminary_review.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for path in sorted(package.rglob('*')):
            if path.is_file():z.write(path,Path('office48_preliminary_review')/path.relative_to(package))
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC check failed')
    receipt=dict(archive=str(archive.relative_to(ROOT)),archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,
                 video=str(video.relative_to(ROOT)),scene=str(scene.relative_to(ROOT)),validation=validation,accepted=False)
    (out/'package_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
