"""Editable source-shaped office furniture; dimensions are predicted, not calibrated."""
import math
import bpy
from mathutils import Vector, Matrix
from aha3d.blender import roomkit
from aha3d.blender.semantics import adopt_group
from aha3d.blender.orientation import tag_orientation


def group(parts, identity, category, pivot=(0,0,0)):
    return adopt_group(parts, category, identity, placement_matrix=Matrix.Translation(pivot))


def box(name, location, size, mat, col, edge=.006):
    return roomkit.box(name,location,size,mat,col,edge)


def rod(name, start, end, radius, mat, col, vertices=12):
    p,q=Vector(start),Vector(end)
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius,depth=(q-p).length,location=(p+q)/2)
    obj=bpy.context.object;obj.name=name
    obj.rotation_mode='QUATERNION';obj.rotation_quaternion=(q-p).to_track_quat('Z','Y')
    for c in list(obj.users_collection):c.objects.unlink(obj)
    col.objects.link(obj);obj.data.materials.append(mat)
    for face in obj.data.polygons:face.use_smooth=True
    return obj


def sphere(name, location, radius, mat, col):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6,radius=radius,location=location)
    obj=bpy.context.object;obj.name=name
    for c in list(obj.users_collection):c.objects.unlink(obj)
    col.objects.link(obj);obj.data.materials.append(mat)
    for face in obj.data.polygons:face.use_smooth=True
    return obj


def chair(identity,col,fabric,wood,metal,swivel=False):
    parts=[box('upholstered seat',(0,0,.46),(.50,.46,.105),fabric,col,.04)]
    # Curved, upholstered solid back. Local front is -Y.
    verts=[];widths=[.24,.255,.25,.23];zs=[.44,.62,.83,.99];segments=16
    for surface in [0,1]:
        for width,z in zip(widths,zs):
            for j in range(segments+1):
                u=j/segments*2-1
                verts.append((u*width,.22+.15*(z-.44)-.08*u*u+surface*.05,z))
    n=len(zs)*(segments+1);faces=[]
    for surf in [0,1]:
        for row in range(len(zs)-1):
            for j in range(segments):
                a=surf*n+row*(segments+1)+j
                f=(a,a+1,a+segments+2,a+segments+1)
                faces.append(f if surf else tuple(reversed(f)))
    for row in range(len(zs)-1):
        for j in [0,segments]:
            a=row*(segments+1)+j;b=(row+1)*(segments+1)+j
            faces.append((a,b,b+n,a+n))
    for row in [0,len(zs)-1]:
        for j in range(segments):
            a=row*(segments+1)+j
            faces.append((a,a+n,a+n+1,a+1))
    mesh=bpy.data.meshes.new('curved upholstered back');mesh.from_pydata(verts,[],faces);mesh.update()
    obj=bpy.data.objects.new('curved upholstered back',mesh);col.objects.link(obj);mesh.materials.append(fabric)
    for face in mesh.polygons:face.use_smooth=True
    bevel=obj.modifiers.new('soft upholstery edges','BEVEL');bevel.width=.012;bevel.segments=3
    parts.append(obj)
    if swivel:
        parts.append(rod('seat piston',(0,0,.09),(0,0,.42),.035,metal,col))
        for i in range(5):
            a=i*math.tau/5;p=(.26*math.cos(a),.26*math.sin(a),.055)
            parts.append(rod('swivel spoke',(0,0,.10),p,.018,metal,col))
            parts.append(sphere('caster',p,.037,metal,col))
    else:
        for x in [-1,1]:
            for y in [-1,1]:
                parts.append(rod('dark tapered leg',(x*.22,y*.205,.02),(x*.19,y*.16,.42),.022,wood,col))
        for j in range(15):
            u=j/14*2-1;z=.97
            parts.append(sphere('back nailhead',(u*.222,.22+.15*(z-.44)-.08*u*u+.054,z),.006,metal,col))
    root=group(parts,identity,'furniture/seating/chair')
    tag_orientation(root,dict(schema_version=1,front_axis='-Y',up_axis='Z',symmetry='none',origin='floor_center',semantic_front='seating',status='authored',evidence='Office48 native frames 0,224,302; source-shaped upholstered chair prototype reviewed before duplication'))
    return root


def table(identity,col,wood):
    parts=[box('trestle desk top',(0,0,.7075),(.66,1.50,.045),wood,col,.012)]
    for y in [-.51,.51]:
        parts.append(box('trestle foot',(0,y,.045),(.64,.16,.09),wood,col,.012))
        parts.append(box('trestle post',(0,y,.365),(.13,.15,.64),wood,col,.009))
        parts.append(box('trestle upper rail',(0,y,.66),(.57,.15,.065),wood,col,.008))
        for side in [-1,1]:
            parts.append(rod('trestle diagonal',(side*.23,y,.08),(0,y,.42),.035,wood,col))
    parts.append(box('longitudinal stretcher',(0,0,.22),(.10,1.15,.10),wood,col))
    return group(parts,identity,'furniture/table')
