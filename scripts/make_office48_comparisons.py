"""Assemble source/model and isolated-object review sheets; no image synthesis."""
import argparse
import json
from pathlib import Path
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--review',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();candidate=ROOT/a.candidate;review=ROOT/a.review;out=ROOT/a.out
    out.mkdir(parents=True,exist_ok=False)
    views=[0,78,146,224,302];sheet=Image.new('RGB',(1280,388*len(views)),(25,28,32));draw=ImageDraw.Draw(sheet)
    for row,source_id in enumerate(views):
        src=Image.open(ROOT/f'outputs/office48-review/source_views/source_{source_id:06d}_source.png').convert('RGB').resize((640,360),Image.Resampling.LANCZOS)
        model=Image.open(candidate/f'source_{source_id:06d}_model.png').convert('RGB')
        if model.size!=(640,360):raise ValueError('Unexpected render raster')
        y=row*388;draw.text((8,y+8),f'Source frame {source_id} / {source_id/30:.3f}s (RGB resized for display)',fill='white')
        draw.text((648,y+8),'New authored room - initial candidate; no people',fill='white')
        sheet.paste(src,(0,y+28));sheet.paste(model,(640,y+28))
    sheet.save(out/'source_vs_model.jpg',quality=92)
    packet=json.loads((review/'focus_manifest.json').read_text())
    focus=Image.new('RGB',(1344,408*len(packet['objects'])),(25,28,32));draw=ImageDraw.Draw(focus)
    for row,entry in enumerate(packet['objects']):
        source_id=entry['source_frame'];src=Image.open(ROOT/f'outputs/office48-review/source_views/source_{source_id:06d}_source.png').convert('RGBA')
        isolated=Image.open(review/entry['isolated_image']).convert('RGBA')
        if isolated.size!=src.size:raise ValueError('Focus/source raster mismatch')
        alpha=isolated.getchannel('A').point(lambda x:round(x*.40));isolated.putalpha(alpha)
        overlay=Image.alpha_composite(src,isolated).convert('RGB')
        y=row*408;draw.text((8,y+8),f"{entry['instance_id']} / source {source_id}",fill='white')
        draw.text((680,y+8),'Orange X-ray silhouette: occluded geometry shown',fill='white')
        focus.paste(src.convert('RGB'),(0,y+30));focus.paste(overlay,(672,y+30))
    focus.save(out/'object_focus.jpg',quality=92)
    ortho=Image.new('RGB',(1920,670),(25,28,32));draw=ImageDraw.Draw(ortho)
    for i,name in enumerate(['plan','front','side']):
        draw.text((i*640+8,8),name+' - diagnostic cutaway; see hidden geometry in manifest',fill='white')
        ortho.paste(Image.open(review/(name+'_cutaway.png')).convert('RGB'),(i*640,30))
    ortho.save(out/'cutaways.jpg',quality=92)
    print(out)


if __name__=='__main__':main()
