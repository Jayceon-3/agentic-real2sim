"""Furnish the newly authored office; never reads the supplied authored example."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'third_party/aha-3d/src'))
sys.path.insert(0,str(ROOT/'scripts'))
from aha3d.blender import roomkit
from aha3d.blender.ensemble import camera_check
from aha3d.blender.semantics import export_semantics,tag_surface
from office48_furniture_parts import box,rod,sphere,chair,table,group


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mat(name,color,roughness=.6,metallic=0):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Roughness'].default_value=roughness;p.inputs['Metallic'].default_value=metallic
    return m


def main():
    if not bpy.app.background:raise RuntimeError('Run in background Blender')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prototype-only',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);out=(ROOT/a.out).resolve();out.relative_to(ROOT)
    if out.exists():raise ValueError('Choose a new output revision')
    source=Path(bpy.data.filepath) if bpy.data.filepath else None
    source_hash=sha(source) if source else None
    if a.prototype_only:bpy.ops.wm.read_factory_settings(use_empty=True)
    else:
        if bpy.context.scene.get('stage')!='architecture_blockout_unaccepted':raise ValueError('Expected newly authored architecture scene')
        prototype=ROOT/'outputs/office48-baseline-001/blender/chair-prototype-v001/prototype_review.json'
        if not prototype.is_file() or json.loads(prototype.read_text()).get('verdict')!='usable_for_initial_source_comparison':
            raise ValueError('Review the actual custom chair prototype before duplicating')
    scene=bpy.context.scene
    furniture=bpy.data.collections.new('Furniture and fixtures');scene.collection.children.link(furniture)
    wood=mat('Dark walnut source furniture',(.025,.014,.007),.63)
    metal=mat('Black bronze hardware',(.016,.014,.012),.38,.55)
    fabric=mat('Grey woven upholstery',(.16,.17,.165),.88)
    black=mat('Charcoal office-chair fabric',(.022,.027,.028),.8)
    white=mat('Paper and clock cream',(.77,.75,.68),.8)
    if a.prototype_only:
        chair('prototype/guest-chair',furniture,fabric,wood,metal)
        floor=box('studio floor',(0,0,-.04),(200,200,.08),mat('studio grey',(.22,.22,.22)),furniture,0)
        cam=bpy.data.objects.new('prototype camera',bpy.data.cameras.new('prototype camera'));scene.collection.objects.link(cam)
        cam.location=(1.4,-2.2,1.4);cam.rotation_euler=(Vector((0,0,.5))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=52;scene.camera=cam
        scene.world=bpy.data.worlds.new('studio world');scene.world.use_nodes=True
        scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.45
        roomkit.area_light('studio key',(1,-2,3),(0,0,.5),180,2)
        scene.render.resolution_x=480;scene.render.resolution_y=480
    else:
        # Repair the observed dark entry strip: the return and jog had coincident
        # front faces over X=1.20..1.452. End the return at the jog's outer edge.
        entry_return=bpy.data.objects['entry-return']
        entry_return.dimensions.x=2.90-1.452
        entry_return.location.x=(2.90+1.452)/2
        desk=table('furniture/desk',furniture,wood);desk.location=(-1.07,2.73,0)
        operator=chair('furniture/chair-operator',furniture,black,wood,metal,True)
        operator.location=(-1.72,2.94,0);operator.rotation_euler.z=math.pi/2
        for i,y in enumerate([2.32,3.07]):
            obj=chair(f'furniture/chair-guest-{i+1}',furniture,fabric,wood,metal)
            obj.location=(-.26,y,0);obj.rotation_euler.z=-math.pi/2
        rugmat=mat('Warm grey low-pile rug',(.17,.18,.17),.96)
        rug=box('rug',(-1.0,2.7,.008),(2.45,2.05,.012),rugmat,furniture,.008)
        group([rug],'furniture/rug','furniture/rug')
        # Plank seams and source-colored timber stay editable, without image dependencies.
        floorcol=bpy.data.collections.new('Editable grey-oak planks');scene.collection.children.link(floorcol)
        plankmats=[mat('Grey oak '+str(i),(.20+i*.012,.192+i*.011,.173+i*.010),.72) for i in range(4)]
        planks=[];x=-2.265;index=0
        while x<1.452-.001:
            width=min(.16,1.452-x);y=.25
            length=.65 if index%2 else 1.15
            while y<4.24-.001:
                end=min(y+length,4.24)
                obj=box('floor plank',(x+width/2,(y+end)/2,.002),(width-.002,end-y-.002,.004),plankmats[(index+len(planks))%4],floorcol,.0006)
                tag_surface(obj,'floor');planks.append(obj);y=end;length=1.15
            x+=width;index+=1
        group(planks,'architecture/floor-planks','architecture/floor')
        # Source ladder shelf: rear uprights plus leaning front supports.
        shelf=[];cx=1.00
        for x in [cx-.29,cx+.29]:
            shelf.append(rod('shelf rear upright',(x,4.18,.02),(x,4.18,1.70),.012,metal,furniture))
            shelf.append(rod('shelf leaning upright',(x,3.80,.02),(x,4.09,1.70),.012,metal,furniture))
        for i,z in enumerate([.13,.49,.85,1.21,1.60]):
            front=3.80+.29*z/1.70
            shelf.append(box('shelf board',(cx,(front+4.19)/2,z),(.61,4.19-front,.028),wood,furniture))
        group(shelf,'furniture/shelf','furniture/shelf')
        for i in range(4):
            book=box('shelf binder',(.84+i*.075,4.06,.66),(.06,.14,.28),metal if i%2 else white,furniture,.002)
            group([book],f'decor/shelf-binder-{i}','decor/book')
        cabinet=[box('cabinet body',(-1.86,3.94,.34),(.55,.45,.68),wood,furniture,.008)]
        cabinet.append(box('cabinet door',(-1.86,3.702,.34),(.49,.025,.56),wood,furniture,.005))
        cabinet.append(box('cabinet pull',(-1.68,3.68,.40),(.018,.025,.09),metal,furniture))
        group(cabinet,'furniture/cabinet','furniture/storage')
        # Visible tabletop items, with source-observed categories and simple unseen backs.
        for i,(x,y,sx,sy) in enumerate([(-1.12,2.30,.29,.21),(-1.14,3.02,.29,.20)]):
            o=box('desk folio',(x,y,.737),(sx,sy,.012),metal,furniture,.005);group([o],f'decor/folio-{i}','decor/book')
        paper=box('desk paper',(-1.07,2.73,.734),(.23,.18,.002),white,furniture,.001)
        group([paper],'decor/paper','decor/paper')
        bottlemat=mat('Water bottle transparent plastic',(.7,.82,.86),.1)
        bottlemat.node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value=.9
        bottle=[rod('water bottle',(-1.16,2.92,.74),(-1.16,2.92,.98),.032,bottlemat,furniture,24),
                rod('bottle neck',(-1.16,2.92,.98),(-1.16,2.92,1.025),.016,bottlemat,furniture,16),
                rod('bottle cap',(-1.16,2.92,1.025),(-1.16,2.92,1.045),.017,white,furniture,16)]
        group(bottle,'decor/water-bottle','decor/bottle')
        # Ring chandelier with eight warm candle lights.
        # Center triangulated from manually reviewed ring centers in source
        # frames 78 (285,173) and 146 (372,137); ray separation about 0.026 m.
        center=Vector((-.425,2.666,2.44));parts=[]
        bpy.ops.mesh.primitive_torus_add(major_segments=64,minor_segments=10,location=center,major_radius=.37,minor_radius=.012)
        ring=bpy.context.object;ring.name='bronze chandelier ring';ring.data.materials.append(metal)
        for c in list(ring.users_collection):c.objects.unlink(ring)
        furniture.objects.link(ring);parts.append(ring)
        parts.append(rod('chandelier chain',(center.x,center.y,2.81),(center.x,center.y,3.97),.009,metal,furniture))
        glow=mat('Warm candle glow',(1,.65,.25),.4)
        sh=glow.node_tree.nodes.get('Principled BSDF');sh.inputs['Emission Color'].default_value=(1,.55,.16,1);sh.inputs['Emission Strength'].default_value=3
        for i in range(8):
            angle=math.tau*i/8;x=center.x+.37*math.cos(angle);y=center.y+.37*math.sin(angle)
            parts.append(rod('candle stem',(x,y,2.44),(x,y,2.56),.012,white,furniture))
            parts.append(sphere('candle bulb',(x,y,2.58),.018,glow,furniture))
            if i%2==0:parts.append(rod('chandelier suspension',(x,y,2.44),(center.x,center.y,2.81),.007,metal,furniture))
        lamp=group(parts,'lighting/chandelier','lighting/chandelier');lamp['support_id']='architecture/ridge-beam'
        # Clock is mounted on the back wall, above the shelf.
        clock=[rod('clock face',(.99,4.19,1.99),(.99,4.22,1.99),.135,white,furniture,48)]
        clock.append(rod('clock minute hand',(.99,4.172,1.99),(.94,4.172,2.07),.004,metal,furniture))
        clock.append(rod('clock hour hand',(.99,4.17,1.99),(1.05,4.17,2.015),.005,metal,furniture))
        for i in range(12):
            angle=math.tau*i/12
            clock.append(sphere('clock hour marker',(.99+.112*math.sin(angle),4.17,1.99+.112*math.cos(angle)),.006,metal,furniture))
        obj=group(clock,'decor/wall-clock','decor/clock');obj['support_id']='architecture/wall-back'
        calendar=box('calendar board',(-2.23,4.04,1.43),(.018,.28,.57),white,furniture)
        group([calendar],'decor/calendar','decor/wall-panel')['support_id']='architecture/wall-left'
        # A source-visible dark cabinet on the entry return; mirror is approximate.
        entry=[box('entry cabinet',(1.73,.68,1.71),(.69,.19,.88),wood,furniture,.012)]
        mirror=mat('Entry mirror',(.85,.85,.85),.04,1)
        entry.append(box('entry mirror',(1.90,.576,1.71),(.28,.012,.79),mirror,furniture,.004))
        group(entry,'furniture/entry-wall-cabinet','furniture/storage')['support_id']='architecture/entry-return'
        for name,color in [('Warm grey painted plaster',(.25,.19,.16)),
                           ('Dark stained ceiling timber',(.027,.015,.007))]:
            material=bpy.data.materials[name]
            material.diffuse_color=(*color,1)
            material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(*color,1)
        roomkit.area_light('Entry-return daylight fill',(2.,-.5,2.4),(1.7,.78,1.5),100,2)
        # Glazing can reflect light sources; exclude those sources from camera rays.
        for obj in scene.objects:
            if obj.type=='LIGHT':
                obj.visible_camera=False;obj.visible_glossy=False;obj.visible_transmission=False
        scene['stage']='furnished_initial_candidate_unaccepted'
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16
    scene.cycles.use_denoising=True;scene.render.image_settings.file_format='PNG'
    scene.render.resolution_percentage=100
    out.mkdir(parents=True,exist_ok=False)
    target=out/('chair_prototype.blend' if a.prototype_only else 'room.blend')
    bpy.ops.wm.save_as_mainfile(filepath=str(target))
    if a.prototype_only:
        scene.render.filepath=str(out/'chair_prototype.png');bpy.ops.render.render(write_still=True)
    else:
        bpy.ops.wm.open_mainfile(filepath=str(target));scene=bpy.context.scene
        cache=ROOT/'outputs/office48-baseline-001/inputs/camera-v001/camera.npz'
        checks=camera_check(scene,cache,dict(frames=303,fps='30',start=1,end=303),[1280,720],{})
        export_semantics(out/'semantics.json')
        for source in [0,78,146,224,302]:
            scene.frame_set(source+1);scene.render.resolution_percentage=50
            scene.render.filepath=str(out/f'source_{source:06d}_model.png');bpy.ops.render.render(write_still=True)
    report=dict(status='custom prototype awaits review' if a.prototype_only else 'initial furnished candidate; review required',
                source_scene_sha256=source_hash,scene_sha256=sha(target),script_sha256=sha(Path(__file__)),
                parts_script_sha256=sha(ROOT/'scripts/office48_furniture_parts.py'),
                asset_search='Registered foot desk and upholstered open-frame chair examined in asset index; source uses narrow trestle desk and solid curved upholstered guest chairs. Source-shaped editable geometry authored instead. Ladder shelf search had no direct match.',
                placement_basis='Locked static reference height slices and native source observations; no supplied office geometry reused',
                camera_after_reopen=None if a.prototype_only else checks,
                limitations=['Inferred hidden furniture surfaces','Uncalibrated scale','Exterior is unmodeled','Materials are initial approximations'])
    (out/'build_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('OFFICE48_FURNITURE_BUILT',target)


if __name__=='__main__':main()
