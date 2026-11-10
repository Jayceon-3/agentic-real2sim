"""Author office48 structure in a saved reference setup using RoomKit primitives."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "third_party/aha-3d/src"))
from aha3d.blender import roomkit
from aha3d.blender.ensemble import camera_check
from aha3d.blender.semantics import adopt_group, export_semantics, tag_surface


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def material(name, color, roughness=.65, transmission=0., metallic=0.):
    value = bpy.data.materials.new(name)
    value.diffuse_color = (*color, 1)
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Transmission Weight"].default_value = transmission
    shader.inputs["Metallic"].default_value = metallic
    return value


def group(parts, identity, semantic, pivot=(0, 0, 0)):
    return adopt_group(parts, semantic, identity, placement_matrix=Matrix.Translation(pivot))


def main():
    if not bpy.app.background or not bpy.data.filepath:
        raise RuntimeError("Open reference_setup.blend in background Blender")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/office48_room_v001.json"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=16)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = (ROOT / args.out).resolve()
    out.relative_to(ROOT)
    if out.exists():
        raise ValueError("Output exists; choose a new revision")
    source = Path(bpy.data.filepath)
    source_hash = digest(source)
    cfg = json.loads((ROOT / args.config).read_text())
    measurement = json.loads((ROOT / cfg["measurement_report"]).read_text())
    if bpy.context.scene.get("stage") != "reference_setup_only_no_authored_room":
        raise ValueError("Expected the independently prepared reference setup")
    scene = bpy.context.scene
    t = dict(frames=303, fps="30", start=1, end=303)
    cache = ROOT / "outputs/office48-baseline-001/inputs/camera-v001/camera.npz"
    camera_before = camera_check(scene, cache, t, [1280, 720], {})
    authored = bpy.data.collections["AUTHORED_ROOM - empty"]
    authored.name = "AUTHORED_ROOM"
    reference = bpy.data.collections["REFERENCE_ONLY - hide for authored-room delivery"]
    reference.hide_render = True
    reference.hide_viewport = True
    architecture = bpy.data.collections.new("Architecture")
    authored.children.link(architecture)
    ceiling_collection = bpy.data.collections.new("Ceiling and roof structure")
    authored.children.link(ceiling_collection)
    props = bpy.data.collections.new("Fixtures and trim")
    authored.children.link(props)
    lights = bpy.data.collections.new("Reconstruction lighting - approximate")
    scene.collection.children.link(lights)
    wallmat = material("Warm grey painted plaster", (.52, .49, .445), .85)
    trim = material("Off-white painted trim", (.84, .83, .79), .55)
    ceilingmat = material("Warm white ceiling", (.79, .77, .71), .8)
    wood = material("Dark stained ceiling timber", (.055, .032, .016), .65)
    floormat = material("Grey oak floor base", (.30, .285, .25), .65)
    glass = material("Window clear glazing", (.96, .98, 1), .035, 1.)
    metal = material("Dark door hardware", (.025, .024, .022), .35, metallic=.65)
    left, right = cfg["bounds"]["left"], cfg["bounds"]["right"]
    back, front = cfg["bounds"]["back"], cfg["bounds"]["front_completion"]
    thick = cfg["wall_thickness"]
    yfit = cfg["roof_fit_at_y"]
    a, by, c = measurement["roofs"]["left"]["z_equals_ax_by_c"]
    d, ey, f = measurement["roofs"]["right"]["z_equals_ax_by_c"]
    b, e = by * yfit + c, ey * yfit + f
    ridge = (e - b) / (a - d)
    peak = a * ridge + b
    zleft, zright = a * left + b, d * right + e
    eave = min(zleft, zright)

    def box(name, location, dimensions, mat, target=architecture, edge=.004):
        return roomkit.box(name, location, dimensions, mat, target, edge)

    floor = box("architecture/floor surface", ((left+right)/2, (front+back)/2, -.06),
                (right-left+.2, back-front+.25, .12), floormat)
    tag_surface(floor, "floor")
    group([floor], "architecture/floor", "architecture/floor")

    def wall_parts(name, axis, coordinate, lo, hi, holes):
        horizontal = sorted(set([lo, hi] + [x for h in holes for x in h["span"]]))
        vertical = sorted(set([0., eave] + [x for h in holes for x in (h["bottom"], h["top"])]))
        pieces = []
        for u0, u1 in zip(horizontal, horizontal[1:]):
            for z0, z1 in zip(vertical, vertical[1:]):
                u, z = (u0+u1)/2, (z0+z1)/2
                if any(h["span"][0] < u < h["span"][1] and h["bottom"] < z < h["top"] for h in holes):
                    continue
                loc = (coordinate, u, z) if axis == 0 else (u, coordinate, z)
                size = (thick, u1-u0, z1-z0) if axis == 0 else (u1-u0, thick, z1-z0)
                obj = box(f"{name}/panel-{len(pieces):02d}", loc, size, wallmat, edge=0)
                tag_surface(obj, "wall")
                pieces.append(obj)
        group(pieces, name, "architecture/wall")

    windows = cfg["windows"]
    wall_parts("architecture/wall-left", 0, left-thick/2, front, back,
               [w for w in windows if w["wall"] == "left"])
    wall_parts("architecture/wall-right", 0, right+thick/2, cfg.get("right_wall_start", front), back, [cfg["door"]])
    if cfg.get("entry_return"):
        r=cfg['entry_return']
        part=box('entry-jog',(r['inner_x']+(right-r['inner_x'])/2,(r['y']+r['join_y'])/2,eave/2),
                 (right-r['inner_x'],r['join_y']-r['y'],eave),wallmat,edge=0)
        tag_surface(part,'wall')
        group([part],'architecture/entry-jog','architecture/wall')
        part=box('entry-return',((r['inner_x']+r['far_x'])/2,r['y']+thick/2,eave/2),
                 (r['far_x']-r['inner_x'],thick,eave),wallmat,edge=0)
        tag_surface(part,'wall')
        group([part],'architecture/entry-return','architecture/wall')
    wall_parts("architecture/wall-back", 1, back+thick/2, left, right,
               [w for w in windows if w["wall"] == "back"])

    def face(name, vertices, mat, col, semantic, role):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], [tuple(range(len(vertices)))])
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        col.objects.link(obj)
        mesh.materials.append(mat)
        tag_surface(obj, role)
        group([obj], name, semantic)
        return obj

    face("architecture/gable-back", [(left,back,eave),(right,back,eave),(right,back,zright),
         (ridge,back,peak),(left,back,zleft)], wallmat, architecture, "architecture/wall", "wall")
    face("architecture/ceiling-left", [(left,front,zleft),(left,back,zleft),
         (ridge,back,peak),(ridge,front,peak)], ceilingmat, ceiling_collection, "architecture/ceiling", "ceiling")
    face("architecture/ceiling-right", [(ridge,front,peak),(ridge,back,peak),
         (right,back,zright),(right,front,zright)], ceilingmat, ceiling_collection, "architecture/ceiling", "ceiling")

    def frame_element(name, wall, u, z, length, height, depth, mat):
        if wall == "back":
            return box(name, (u,back-.018,z), (length,depth,height), mat, props)
        x = left+.018 if wall == "left" else right-.018
        return box(name, (x,u,z), (depth,length,height), mat, props)

    for opening in [*windows, cfg["door"]]:
        ident, wall = opening["id"], opening["wall"]
        lo, hi = opening["span"]
        bottom, top = opening["bottom"], opening["top"]
        middle = (lo+hi)/2
        parts = []
        def member(suffix, u, z, width, height, depth=.075, mat=trim):
            obj = frame_element(ident+"/"+suffix, wall,u,z,width,height,depth,mat)
            parts.append(obj)
            return obj
        member("outer-left", lo-.043,(top+bottom)/2,.086,top-bottom+.17)
        member("outer-right", hi+.043,(top+bottom)/2,.086,top-bottom+.17)
        member("header", middle,top+.06,hi-lo+.24,.12,.09)
        member("sill", middle,bottom-.035,hi-lo+.22,.07,.14)
        for j in range(opening["columns"]):
            l=lo+(hi-lo)*j/opening["columns"]
            r=lo+(hi-lo)*(j+1)/opening["columns"]
            member(f"jamb-{j}", l+.018,(bottom+top)/2,.036,top-bottom,.055)
            member(f"glass-{j}", (l+r)/2,(bottom+top)/2,r-l-.055,top-bottom-.07,.008,glass)
            member(f"rail-top-{j}", (l+r)/2,top-.025,r-l,.05,.055)
            member(f"rail-bottom-{j}", (l+r)/2,bottom+.025,r-l,.05,.055)
            member(f"rail-middle-{j}", (l+r)/2,1.04,r-l,.04,.055)
            member(f"mullion-{j}", (l+r)/2,(bottom+top)/2,.024,top-bottom,.04)
        member("last-jamb",hi-.018,(bottom+top)/2,.036,top-bottom,.055)
        if wall == "right":
            member("door-meeting-stile",middle,(top+bottom)/2,.055,top-bottom,.07)
            member("handle-left",middle-.11,.95,.025,.19,.12,metal)
            member("handle-right",middle+.11,.95,.025,.19,.12,metal)
        group(parts, ident, "architecture/door" if wall=="right" else "architecture/window")

    # Solid trim runs stop at the full-height doorway.
    skirting=[]
    for x in [left+.015,right-.015]:
        intervals=[(front,back)] if x<0 else [(front,cfg["door"]["span"][0]),(cfg["door"]["span"][1],back)]
        for y0,y1 in intervals:
            skirting.append(box("baseboard",(x,(y0+y1)/2,.06),(.035,y1-y0,.12),trim,props))
    skirting.append(box("baseboard-back",((left+right)/2,back-.018,.06),(right-left,.035,.12),trim,props))
    group(skirting,"architecture/baseboards","architecture/trim")

    def beam(name, p0, p1, width=.14, depth=.18):
        v0,v1=Vector(p0),Vector(p1)
        obj=box(name,(v0+v1)/2,(width,depth,(v1-v0).length),wood,ceiling_collection,.006)
        obj.rotation_mode='QUATERNION'
        obj.rotation_quaternion=(v1-v0).to_track_quat('Z','Y')
        return obj
    for index,y in enumerate(cfg["timber_frame_y"]):
        pieces=[beam("rafter-left",(left,y,zleft-.09),(ridge,y,peak-.09)),
                beam("rafter-right",(ridge,y,peak-.09),(right,y,zright-.09))]
        tie=3.40
        pieces.append(beam("collar-tie",((tie-b)/a,y,tie-.09),((tie-e)/d,y,tie-.09),.13,.14))
        group(pieces,f"architecture/timber-frame-{index+1}","architecture/beam")
    group([beam("ridge-timber",(ridge,front,peak-.08),(ridge,back,peak-.08),.13,.13)],
          "architecture/ridge-beam","architecture/beam")

    scene.world.use_nodes=True
    background=scene.world.node_tree.nodes.get('Background')
    background.inputs['Color'].default_value=(.78,.85,1.,1)
    background.inputs['Strength'].default_value=.6
    def area(name,position,target,energy,size):
        obj=roomkit.area_light(name,position,target,energy,size)
        obj.visible_camera=False
        obj.visible_glossy=False
        obj.visible_transmission=False
        for col in list(obj.users_collection): col.objects.unlink(obj)
        lights.objects.link(obj)
    area('Daylight through back window',(-.4,4.0,2.1),(-.4,2.2,.7),180,1.7)
    area('Daylight through left windows',(-2.05,2.7,2.0),(.2,2.7,.8),150,1.5)
    area('Soft entry fill',(.1,.5,2.4),(-.4,3.0,1.2),90,2.5)
    scene.render.engine='CYCLES'
    scene.cycles.device='CPU'
    scene.cycles.samples=args.samples
    scene.cycles.use_denoising=True
    scene.cycles.max_bounces=6
    scene.render.film_transparent=False
    scene.view_settings.view_transform='AgX'
    scene.view_settings.exposure=.4
    scene.render.resolution_percentage=100
    scene['stage']='architecture_blockout_unaccepted'
    scene.frame_set(147)
    authored['status']='Architecture blockout; no furniture yet; review pending'
    out.mkdir(parents=True,exist_ok=False)
    target=out/'room.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(target))
    bpy.ops.wm.open_mainfile(filepath=str(target))
    scene=bpy.context.scene
    camera_after=camera_check(scene,cache,t,[1280,720],{})
    export_semantics(out/'semantics.json')
    for source_id in [0,78,146,224,302]:
        scene.frame_set(source_id+1)
        scene.render.resolution_percentage=50
        scene.render.filepath=str(out/f'source_{source_id:06d}_model.png')
        bpy.ops.render.render(write_still=True)
    scene.render.resolution_percentage=100
    report=dict(schema_version=1,status='architecture blockout; visual review required',
                source_reference_scene_sha256=source_hash,scene_sha256=digest(target),
                config_sha256=digest(ROOT/args.config),script_sha256=digest(Path(__file__)),
                camera_before=camera_before,camera_after_reopen=camera_after,
                estimated_room_bounds=cfg['bounds'],roof={'ridge_x':ridge,'peak_z':peak,'left_eave_z':zleft,'right_eave_z':zright},
                assumptions=cfg['assumptions'],reference_rendered=False,people_included=False,
                furniture='not yet authored',render_source_frames=[0,78,146,224,302])
    (out/'build_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('OFFICE48_ARCHITECTURE_BUILT',target)


if __name__=='__main__':
    main()
