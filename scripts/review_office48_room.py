"""Saved-room placement diagnostics and native Blender object-focus passes.

This early-review packet does not replace the upstream layout acceptance gate.
"""
import argparse
import json
import sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'third_party/aha-3d/src'))
from aha3d.blender.body import camera_matrices
from aha3d.blender.placement_check import check
from aha3d.placement.report import write_report


def owner(obj):
    while obj:
        if obj.get('instance_id'):return obj['instance_id']
        obj=obj.parent
    return None


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);out=(ROOT/args.out).resolve();out.mkdir(parents=True,exist_ok=False)
    scene=bpy.context.scene;scene.frame_set(1);dg=bpy.context.evaluated_depsgraph_get()
    k,rt,w,h,*_=camera_matrices(scene,dg);pose=np.linalg.inv(rt)
    rays=[]
    for u,v in [(500,200),(480,200),(510,100)]:
        direction=pose[:3,:3]@np.linalg.solve(k,[u*2+.5,v*2+.5,1]);direction/=np.linalg.norm(direction)
        hit,loc,n,face,obj,matrix=scene.ray_cast(dg,Vector(pose[:3,3]),Vector(direction))
        rays.append(dict(test_pixel_640x360=[u,v],hit=hit,object=obj.name if hit else None,point=list(loc) if hit else None))
    (out/'entry_ray_debug.json').write_text(json.dumps(rays,indent=2)+'\n')
    report=check(json.loads((ROOT/'configs/office48_placement_v1.json').read_text()))
    place=out/'placement';place.mkdir();write_report(place,report)
    # Exclude all reference objects by collection membership, not name substring.
    reference=bpy.data.collections['REFERENCE_ONLY - hide for authored-room delivery']
    reference.hide_render=True
    renderables=[o for o in scene.objects if o.type in {'MESH','CURVE','FONT'} and o.name not in reference.all_objects and not o.hide_render]
    scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_percentage=100
    scene.render.resolution_x=672;scene.render.resolution_y=378
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
    scene.view_settings.view_transform='Standard';scene.view_settings.look='None';scene.view_settings.exposure=0
    scene.display.shading.color_type='OBJECT';scene.display.shading.light='STUDIO'
    scene.display.shading.show_shadows=False;scene.display.shading.show_cavity=False
    scene.display.render_aa='16'
    source_camera=scene.camera
    targets=[('furniture/desk',224),('furniture/chair-guest-1',224),('furniture/chair-guest-2',224),
             ('furniture/chair-operator',224),('furniture/shelf',224),('furniture/cabinet',302),
             ('lighting/chandelier',146),('architecture/wall-back',146),('architecture/wall-left',146),
             ('architecture/entry-return',0)]
    packet=[]
    for identity,source_id in targets:
        scene.camera=source_camera;scene.frame_set(source_id+1)
        for o in renderables:
            o.hide_render=owner(o)!=identity;o.color=(1.,.28,.035,1)
        scene.render.film_transparent=True
        path=out/(identity.replace('/','_')+'_isolated.png');scene.render.filepath=str(path)
        bpy.ops.render.render(write_still=True)
        packet.append(dict(instance_id=identity,source_frame=source_id,isolated_image=path.name,meaning='Exact-source-camera isolated silhouette, other objects hidden; shows occluded surfaces'))
    for o in renderables:o.hide_render=False;o.color=(.65,.65,.65,1)
    cam=bpy.data.objects.new('Diagnostic orthographic camera',bpy.data.cameras.new('Diagnostic orthographic camera'))
    scene.collection.objects.link(cam);cam.data.type='ORTHO';cam.data.ortho_scale=5.4;scene.camera=cam
    scene.render.resolution_x=640;scene.render.resolution_y=640
    scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1;scene.render.film_transparent=False
    ortho=[]
    for name,location,target,hide in [
        ('plan',(-.4,2.6,8),(-.4,2.6,0),['architecture/ceiling','architecture/wall','architecture/entry','architecture/gable','architecture/timber','architecture/ridge']),
        ('front',(-.4,-6,1.9),(-.4,2.6,1.9),['architecture/entry']),
        ('side',(7,2.7,1.9),(-.4,2.7,1.9),['architecture/wall-right','architecture/entry','architecture/door'])]:
        cam.location=location;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
        for o in renderables:o.hide_render=any(str(owner(o) or '').startswith(s) for s in hide)
        scene.render.filepath=str(out/(name+'_cutaway.png'));bpy.ops.render.render(write_still=True)
        ortho.append(dict(view=name,hidden_id_prefixes=hide,location=location,target=target))
    (out/'focus_manifest.json').write_text(json.dumps(dict(stage='early object review, not upstream layout acceptance',source_scene=bpy.data.filepath,objects=packet,orthographic_cutaways=ortho,placement_summary=report['summary']),indent=2)+'\n')
    print('OFFICE48_REVIEW_PACKET_OK',report['summary'])


if __name__=='__main__':main()
