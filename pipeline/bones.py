"""Dump a rigged GLB's armature (bone names, parents, world head/tail) so we can find the
right-hand bone for the weapon chain, AND confirm the mesh deforms (rest vs arms-swung).
PIL montage is optional (Blender python may lack it).

Run: blender -b --python _bones.py -- --glb <rigged>.glb --out <dir>
"""
import bpy, sys, os, math, mathutils
argv = sys.argv[sys.argv.index("--")+1:]
def arg(n,d=None): return argv[argv.index(n)+1] if n in argv else d
GLB=arg("--glb"); OUT=arg("--out","."); os.makedirs(OUT,exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
arm=[o for o in bpy.context.scene.objects if o.type=="ARMATURE"][0]
mesh=max([o for o in bpy.context.scene.objects if o.type=="MESH"], key=lambda m:len(m.data.vertices))
print(f"ARM={arm.name} bones={len(arm.data.bones)} mesh={mesh.name} verts={len(mesh.data.vertices)} vgroups={len(mesh.vertex_groups)} mods={[m.type for m in mesh.modifiers]}", flush=True)
M=arm.matrix_world
for b in arm.data.bones:
    h=M@b.head_local; t=M@b.tail_local
    print(f"  {b.name:26s} parent={str(b.parent.name if b.parent else '-'):22s} head=({h.x:+.3f},{h.y:+.3f},{h.z:+.3f}) tail=({t.x:+.3f},{t.y:+.3f},{t.z:+.3f})", flush=True)
vs=[mesh.matrix_world@v.co for v in mesh.data.vertices]
xs=[v.x for v in vs]; ys=[v.y for v in vs]; zs=[v.z for v in vs]
cx=(min(xs)+max(xs))/2; cy=(min(ys)+max(ys))/2; cz=(min(zs)+max(zs))/2
W=max(xs)-min(xs); H=max(zs)-min(zs)
print(f"[mesh bbox] x=[{min(xs):+.3f},{max(xs):+.3f}] y=[{min(ys):+.3f},{max(ys):+.3f}] z=[{min(zs):+.3f},{max(zs):+.3f}]", flush=True)

# --- deform test render (rest vs arms-swung) ---
camd=bpy.data.cameras.new("C"); cam=bpy.data.objects.new("C",camd)
bpy.context.scene.collection.objects.link(cam); bpy.context.scene.camera=cam; camd.lens=80
ctr=mathutils.Vector((cx,cy,cz)); rad=max(W,H)
cam.location=(cx, cy-rad*2.7, cz)
tgt=bpy.data.objects.new("T",None); tgt.location=ctr; bpy.context.scene.collection.objects.link(tgt)
c=cam.constraints.new("TRACK_TO"); c.target=tgt; c.track_axis="TRACK_NEGATIVE_Z"; c.up_axis="UP_Y"
world=bpy.data.worlds.new("W"); bpy.context.scene.world=world; world.use_nodes=True
bg=world.node_tree.nodes["Background"]; bg.inputs[0].default_value=(0.215,0.215,0.235,1.0); bg.inputs[1].default_value=0.85
for nm,e,rot in [("k",5.2,(math.radians(58),0,math.radians(38))),("f",3.0,(math.radians(62),0,math.radians(-48))),("r",5.5,(math.radians(-48),0,math.radians(170)))]:
    L=bpy.data.lights.new(nm,"SUN"); L.energy=e; o=bpy.data.objects.new(nm,L); bpy.context.scene.collection.objects.link(o); o.rotation_euler=rot
sc=bpy.context.scene
try: sc.render.engine="BLENDER_EEVEE_NEXT"
except: sc.render.engine="BLENDER_EEVEE"
sc.view_settings.view_transform='Standard'; sc.render.resolution_x=560; sc.render.resolution_y=760
def render(p): sc.render.filepath=p; bpy.ops.render.render(write_still=True)
render(os.path.join(OUT,"rest.png"))
bpy.context.view_layer.objects.active=arm; bpy.ops.object.mode_set(mode='POSE')
moved=0
for pb in arm.pose.bones:
    hx=(arm.matrix_world@pb.head).x-cx; hz=(arm.matrix_world@pb.head).z
    if abs(hx)>0.12*W and hz>min(zs)+0.45*H:
        pb.rotation_mode='XYZ'; pb.rotation_euler.rotate_axis("Y", math.radians(55 if hx>0 else -55)); moved+=1
bpy.ops.object.mode_set(mode='OBJECT'); bpy.context.view_layer.update()
print(f"[deform] swung {moved} arm-ish bones", flush=True)
render(os.path.join(OUT,"posed.png"))
try:
    from PIL import Image
    a=Image.open(os.path.join(OUT,"rest.png")).convert("RGB"); b=Image.open(os.path.join(OUT,"posed.png")).convert("RGB")
    g=Image.new("RGB",(a.width+b.width+12,max(a.height,b.height)),(38,38,42)); g.paste(a,(0,0)); g.paste(b,(a.width+12,0))
    g.save(os.path.join(OUT,"_deform_2up.png")); print("MONTAGE ok", flush=True)
except Exception as e:
    print(f"[montage skipped] {e}", flush=True)
print("BONES DONE", flush=True)
