"""Repair source/placement findings in an existing independent candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bpy
import bmesh

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'third_party/aha-3d/src'))
from aha3d.blender.ensemble import camera_check
from aha3d.blender.semantics import descendants,export_semantics
from aha3d.blender.orientation import place_root,tag_orientation


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);out=(ROOT/a.out).resolve();out.mkdir(parents=True,exist_ok=False)
    scene=bpy.context.scene
    source=Path(bpy.data.filepath);original=hashlib.sha256(source.read_bytes()).hexdigest()
    roots={o['instance_id']:o for o in scene.objects if o.get('instance_id')}
    for o in descendants(roots['architecture/door-double']):
        if 'outer-left' in o.name or 'outer-right' in o.name:
            o.dimensions.z=2.125;o.location.z=2.125/2
        elif o.name.endswith('/sill'):
            o.dimensions.z=.02;o.location.z=.01
    for o in descendants(roots['architecture/baseboards']):
        if o.type=='MESH' and o.location.x>1.0 and o.location.y<2.0:
            o.location.y=(1.45+1.72)/2;o.dimensions.y=1.72-1.45
    for o in descendants(roots['decor/calendar']):
        if o.type=='MESH':o.location.y=4.13;o.dimensions.y=.18
    for o in descendants(roots['furniture/rug']):
        if o.type=='MESH':o.location.y=2.65;o.dimensions.y=2.0
    # Furniture feet rest on the actual rug top; move supported tabletop items
    # together with their support rather than leaving them embedded/floating.
    for identity in ['furniture/desk','decor/folio-0','decor/folio-1','decor/paper','decor/water-bottle']:
        roots[identity].location.z+=.014
    for identity,direction in [('furniture/chair-guest-1',(-1,0,0)),
                               ('furniture/chair-guest-2',(-1,0,0)),
                               ('furniture/chair-operator',(1,0,0))]:
        root=roots[identity]
        for obj in descendants(root):
            if obj.type=='MESH' and obj.name.startswith('curved upholstered back'):
                bm=bmesh.new();bm.from_mesh(obj.data)
                bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
                bm.to_mesh(obj.data);bm.free()
        place_root(root,facing_direction=direction)
    door=roots['architecture/door-double']
    tag_orientation(door,dict(schema_version=1,front_axis='-X',up_axis='Z',symmetry='none',
                    origin='source_root',semantic_front='generic',status='authored',
                    evidence='Office48 source 0: interior handle and glazing side faces room -X; static source-root placement'))
    place_root(door,facing_direction=(-1,0,0))
    # Keep the observed interior surfaces fixed while giving architecture a
    # closed collision shell on its unobserved exterior side.
    for identity in ['architecture/ceiling-left','architecture/ceiling-right','architecture/gable-back']:
        for obj in descendants(roots[identity]):
            if obj.type!='MESH':continue
            bm=bmesh.new();bm.from_mesh(obj.data)
            bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-6)
            bm.to_mesh(obj.data);bm.free()
            modifier=obj.modifiers.new('Inferred exterior shell thickness','SOLIDIFY')
            modifier.thickness=.08;modifier.offset=-1.;modifier.use_even_offset=True
            obj['shell_thickness_provenance']='Unobserved exterior completion; interior source-supported surface preserved'
    scene.frame_set(147);scene.render.resolution_percentage=100
    target=out/'room.blend';bpy.ops.wm.save_as_mainfile(filepath=str(target))
    bpy.ops.wm.open_mainfile(filepath=str(target));scene=bpy.context.scene
    cache=ROOT/'outputs/office48-baseline-001/inputs/camera-v001/camera.npz'
    camera=camera_check(scene,cache,dict(frames=303,fps='30',start=1,end=303),[1280,720],{})
    export_semantics(out/'semantics.json')
    for source_id in [0,78,146,224,302]:
        scene.frame_set(source_id+1);scene.render.resolution_percentage=50
        scene.render.filepath=str(out/f'source_{source_id:06d}_model.png');bpy.ops.render.render(write_still=True)
    report=dict(status='repaired initial candidate; not final acceptance',source_scene_sha256=original,
                scene_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),camera_after_reopen=camera,
                repairs=['Door outer jambs stop at floor; threshold bottom flush at Z=0',
                         'Right baseboard stops at entry jog instead of passing through it',
                         'Calendar moved into visible solid wall strip, away from window frame',
                         'Rug shortened to clear cabinet support footprint',
                         'Desk and tabletop props raised together to rug top',
                         'Curved chair-back normals recalculated before bevel; scene facing intent declared',
                         'Ceiling and gable given closed 8 cm outward shells; exterior thickness inferred'],
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'build_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('OFFICE48_CANDIDATE_REPAIRED',target)


if __name__=='__main__':main()
