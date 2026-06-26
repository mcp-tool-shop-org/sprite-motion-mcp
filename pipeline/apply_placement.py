"""sprite-motion BRIDGE — apply editor placement(s) to rigged character GLB(s).
Each weapon is dropped at its exact attachPoint (+ orientation + scale), with a non-deform
weapon_grip bone (child of the named bone) so it rides the hand. No coordinate guessing.

SINGLE character ("Export JSON" from the editor):
  blender -b --python apply_placement.py -- --char <rigged>.glb --placement <placement>.json \
      --weapons halberd=<halberd>.glb [--out <out>.glb]

WHOLE ROSTER ("Export all placements"):
  blender -b --python apply_placement.py -- --placement <placements>.json \
      --manifest <manifest>.json --outdir <dir>
    placements = { "format":"sprite-motion.placements", "characters":[ <block>, ... ] }
    manifest   = { "characters": { "<skeleton name>": "<rigged glb>", ... },
                   "weapons":    { "<asset>": "<weapon glb>", ... } }
  --weapons asset=glb,... augments/overrides the manifest's weapon map.

PLACEMENT FORMATS (dispatched per-weapon):
  v4 (3D editor) — weapon carries `rootTransform {position,quaternion,scale}` resolved to the CHARACTER
    ROOT in three.js / glTF **Y-up** space, plus `attachPoint` (grip) and `tipPoint`, also character-root
    Y-up. The bridge converts Y-up -> Blender **Z-up** (Rx+90), sets the weapon's world matrix DIRECTLY
    (WYSIWYG — what the editor showed is what lands; no auto-orientation), then builds weapon_grip->weapon_tip.
  v3 (legacy 2D editor) — weapon carries `offset` + `attachPoint` (Blender **Z-up**) + in-plane `rotationDeg`
    + image-space `gripAnchor`/`tipAnchor`; the weapon is auto-oriented from its geometry. Still supported.
  Dispatch key: presence of `rootTransform` -> v4, else v3.
"""
import bpy, sys, os, json, math, mathutils, numpy as np
argv = sys.argv[sys.argv.index("--")+1:]
def arg(n, d=None): return argv[argv.index(n)+1] if n in argv else d
PLACE = arg("--placement"); CHAR = arg("--char"); OUT = arg("--out")
MANIFEST = arg("--manifest"); OUTDIR = arg("--outdir")
ASSETS_CLI = dict(kv.split("=", 1) for kv in arg("--weapons", "").split(",") if "=" in kv)
V = mathutils.Vector
C = mathutils.Matrix.Rotation(math.radians(90), 4, 'X')   # glTF/three.js (Y-up) -> Blender (Z-up)
P = json.load(open(PLACE, encoding="utf-8"))

def co(o): return np.array([(v.co.x, v.co.y, v.co.z) for v in o.data.vertices])

def _import_weapon(asset, path):
    """Import a weapon GLB, join to one mesh, drop empties, bake the import transform. Shared by v3 + v4."""
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.context.scene.objects if o not in before]
    hm = [o for o in new if o.type == "MESH"]
    bpy.ops.object.select_all(action='DESELECT')
    for o in hm: o.select_set(True)
    bpy.context.view_layer.objects.active = hm[0]
    if len(hm) > 1: bpy.ops.object.join()
    hal = bpy.context.view_layer.objects.active; hal.name = "wpn_" + asset
    for o in new:
        if o.type == "EMPTY":
            try: bpy.data.objects.remove(o, do_unlink=True)
            except Exception: pass
    bpy.ops.object.select_all(action='DESELECT'); hal.select_set(True); bpy.context.view_layer.objects.active = hal
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return hal

def _build_grip_chain(arm, bone, asset, gripw, tipw):
    """weapon_grip (HEAD at the grip) -> weapon_tip (HEAD at the business end). glTF stores joint HEADS,
    not tails, so the meaningful positions go in the heads (KB rigging: the tip joint feeds hit-box / tip-velocity).
    gripw/tipw are world-space (Blender Z-up) points. Returns the grip bone name (for parenting)."""
    Minv = arm.matrix_world.inverted()
    grip_local = Minv @ gripw; tip_local = Minv @ tipw
    d = tip_local - grip_local; L = d.length; d = d / L if L > 1e-5 else V((0, 0, 1))
    bpy.context.view_layer.objects.active = arm; bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.data.edit_bones; hb = eb[bone]; gn = "weapon_grip_" + asset; tn = "weapon_tip_" + asset
    g = eb.new(gn); g.head = grip_local; g.tail = grip_local + d * max(0.08, L * 0.3); g.parent = hb; g.use_deform = False; g.use_connect = False
    t = eb.new(tn); t.head = tip_local; t.tail = tip_local + d * 0.05; t.parent = g; t.use_deform = False; t.use_connect = False
    bpy.ops.object.mode_set(mode='OBJECT')
    return gn

def place(w, arm, figureH, assets):
    """v3 (legacy): auto-orient the weapon from its geometry, then drop at attachPoint (Blender Z-up) + in-plane rotationDeg."""
    asset = w["asset"]; path = assets.get(asset); bone = w["bone"]
    if not path or not os.path.exists(path): print(f"[skip] no GLB for '{asset}'", flush=True); return
    if bone not in arm.data.bones: print(f"[skip] bone '{bone}' absent", flush=True); return
    hal = _import_weapon(asset, path)
    c = co(hal); ext = c.max(0) - c.min(0); la = int(np.argmax(ext))     # longest axis -> Z
    if la != 2:
        hal.rotation_euler = (0, math.radians(90), 0) if la == 0 else (math.radians(90), 0, 0)
        bpy.ops.object.transform_apply(rotation=True); c = co(hal)
    zmin, zmax = c[:, 2].min(), c[:, 2].max(); zr = zmax - zmin          # head (wider end) -> +Z
    top = c[c[:, 2] > zmin + 0.78*zr]; bot = c[c[:, 2] < zmin + 0.22*zr]
    tw = (top[:, 0].max() - top[:, 0].min()) if len(top) > 3 else 0
    bw = (bot[:, 0].max() - bot[:, 0].min()) if len(bot) > 3 else 0
    if bw > tw: hal.rotation_euler = (math.radians(180), 0, 0); bpy.ops.object.transform_apply(rotation=True); c = co(hal)
    zmin, zmax = c[:, 2].min(), c[:, 2].max(); haft = c[c[:, 2] < zmin + 0.4*(zmax - zmin)]
    cx, cy = haft[:, 0].mean(), haft[:, 1].mean()                         # recenter haft -> x=y=0, butt -> z=0
    for v in hal.data.vertices: v.co.x -= cx; v.co.y -= cy; v.co.z -= zmin
    c = co(hal); Hn = c[:, 2].max() - c[:, 2].min(); s = (w.get("scale", 1.0)*figureH)/max(1e-6, Hn)
    for v in hal.data.vertices: v.co *= s                                # uniform scale -> scale*figureH
    gf = 1.0 - w.get("gripAnchor", [0.5, 0.5])[1]
    c = co(hal); Hn = c[:, 2].max() - c[:, 2].min(); gz = c[:, 2].min() + gf*Hn
    for v in hal.data.vertices: v.co.z -= gz                             # grip -> origin
    hal.data.update()
    ap = w["attachPoint"]
    hal.rotation_euler = (0, math.radians(w.get("rotationDeg", 0)), 0)   # in-plane (about depth axis)
    hal.location = V((ap[0], ap[1], ap[2]))
    bpy.context.view_layer.update()
    apw = V((ap[0], ap[1], ap[2]))
    MW = mathutils.Matrix.Translation(apw) @ mathutils.Euler((0, math.radians(w.get("rotationDeg", 0)), 0), 'XYZ').to_matrix().to_4x4()
    tA = w.get("tipAnchor")
    if tA:                                              # editor's explicit tip: image-v maps to haft height
        c = co(hal); Hloc = c[:, 2].max() - c[:, 2].min()
        tip_z = (w.get("gripAnchor", [0.5, 0.5])[1] - tA[1]) * Hloc
        tipw = MW @ V((0.0, 0.0, tip_z))                # on the haft axis at the tip height (grip is at z=0 local)
    else:                                               # fallback: weapon's far end from the grip
        tipw = max((MW @ v.co for v in hal.data.vertices), key=lambda p: (p - apw).length)
    gn = _build_grip_chain(arm, bone, asset, apw, tipw)
    bpy.ops.object.select_all(action='DESELECT'); hal.select_set(True); arm.select_set(True); bpy.context.view_layer.objects.active = arm
    arm.data.bones.active = arm.data.bones[gn]
    bpy.ops.object.parent_set(type='BONE', keep_transform=True)
    print(f"[placed v3] {asset} -> {bone}  at {ap}  rot={w.get('rotationDeg',0)} scale={w.get('scale',1.0)}", flush=True)

def place_v4(w, arm, assets):
    """v4 (3D editor): explicit weapon transform (three.js Y-up, relative to the character root) -> WYSIWYG.
    No auto-orientation; the editor already oriented the weapon. Convert Y-up -> Z-up via C (Rx+90)."""
    asset = w["asset"]; path = assets.get(asset); bone = w["bone"]
    if not path or not os.path.exists(path): print(f"[skip] no GLB for '{asset}'", flush=True); return
    if bone not in arm.data.bones: print(f"[skip] bone '{bone}' absent", flush=True); return
    hal = _import_weapon(asset, path)                                    # verts now baked to C @ v_local (Blender Z-up)
    rt = w["rootTransform"]; q = rt["quaternion"]; s = float(rt.get("scale", 1.0))
    quat = mathutils.Quaternion((q[3], q[0], q[1], q[2]))               # three.js [x,y,z,w] -> mathutils (w,x,y,z)
    M_gltf = mathutils.Matrix.Translation(V(rt["position"])) @ quat.to_matrix().to_4x4() @ mathutils.Matrix.Scale(s, 4)
    hal.matrix_world = C @ M_gltf @ C.inverted()                        # weapon world matrix, Blender space (conjugation)
    bpy.context.view_layer.update()
    grip = w.get("attachPoint"); tip = w.get("tipPoint")               # character-root Y-up points -> Blender via C
    gripw = (C @ V(grip)) if grip else (hal.matrix_world @ V((0.0, 0.0, 0.0)))
    tipw = (C @ V(tip)) if tip else max((hal.matrix_world @ v.co for v in hal.data.vertices), key=lambda p: (p - gripw).length)
    gn = _build_grip_chain(arm, bone, asset, gripw, tipw)
    bpy.ops.object.select_all(action='DESELECT'); hal.select_set(True); arm.select_set(True); bpy.context.view_layer.objects.active = arm
    arm.data.bones.active = arm.data.bones[gn]
    bpy.ops.object.parent_set(type='BONE', keep_transform=True)         # keep_transform -> Blender computes the bone-local offset; no bone-axis math
    print(f"[placed v4] {asset} -> {bone}  scale={s}  grip={[round(x,4) for x in gripw]} tip={[round(x,4) for x in tipw]}", flush=True)

def _bone_depth(arm, name):
    d = 0; b = arm.data.bones.get(name)
    while b is not None and b.parent is not None: b = b.parent; d += 1
    return d

def apply_pose(arm, pose):
    """Pose the armature from the editor's baked per-bone root-relative world transforms
    (poseForChar -> world.{p,q}, three.js Y-up). World transforms port across the three.js/Blender
    bone-axis difference (Y-up -> Z-up via C); local delta-quats do NOT. Sets each pose bone parent-first;
    rig_character then bakes the posed deformation into the mesh (apply Armature modifier) so the glTF
    export carries the posed shape — armature_apply re-rests the skeleton but the bound mesh would NOT follow."""
    if not pose: return
    bd = pose.get("bones", {})
    posed = [n for n in bd if n in arm.pose.bones and bd[n].get("world")]
    if not posed: return
    posed.sort(key=lambda n: _bone_depth(arm, n))                          # parent-first: children inherit posed parents
    bpy.ops.object.select_all(action='DESELECT'); arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    Minv = arm.matrix_world.inverted()
    for name in posed:
        wd = bd[name]["world"]; q = wd["q"]
        quat = mathutils.Quaternion((q[3], q[0], q[1], q[2]))              # three.js [x,y,z,w] -> mathutils (w,x,y,z)
        M_root = mathutils.Matrix.Translation(V(wd["p"])) @ quat.to_matrix().to_4x4()
        arm.pose.bones[name].matrix = Minv @ (C @ M_root @ C.inverted())  # absolute posed transform, Blender space
        bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"[posed] {len(posed)} bone(s)", flush=True)

def _role_delta_steps(spec):
    """Normalize a role's rotation spec to an ordered list of (axis, deg).
    Accepts BOTH the single-axis form {axis,deg} (back-compat) and the multi-axis
    sequence [{axis,deg}, ...] — a real stance needs >1 axis per joint, so the
    sequence is applied in order (each step is an OUTER world-axis rotation on top
    of the prior). A bare list of [x,y,z,deg]-less dicts is tolerated too."""
    if spec is None: return []
    seq = spec if isinstance(spec, list) else [spec]
    out = []
    for s in seq:
        if not isinstance(s, dict): continue
        out.append((V(s.get("axis", [1, 0, 0])).normalized(), float(s.get("deg", 0))))
    return out

def apply_role_pose(arm, pose, rolemap):
    """Apply a Claude/MCP-authored canonical pose: per-role WORLD-axis delta rotations (Blender Z-up frame:
    X=left/right, Y=depth/-Y-forward, Z=up), resolved to bones via the roleMap, applied FK parent-first.
    World-axis deltas port cleanly (no bone-axis issue) and are authorable WITHOUT the editor.
    Each role may carry a SEQUENCE of {axis,deg} (multi-axis) — required for real stances; a single
    {axis,deg} still works. Steps for one bone share the bone's (posed) head, so composing the rotations
    and applying once about that head is exact (rotations about a fixed point compose: piv(R2,h)piv(R1,h)=piv(R2R1,h))."""
    rr = pose.get("roleRotations", {})
    items = [(role, rolemap.get(role)) for role in rr if rolemap.get(role) in arm.pose.bones]
    if not items: return
    items.sort(key=lambda it: _bone_depth(arm, it[1]))                         # parent-first: children inherit posed parents
    Rarm_inv = arm.matrix_world.to_3x3().inverted()                            # world-axis -> armature space (identity for this rig)
    bpy.ops.object.select_all(action='DESELECT'); arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    nstep = 0
    for role, bname in items:
        steps = _role_delta_steps(rr[role])
        if not steps: continue
        composed = mathutils.Matrix.Identity(3)
        for axis, deg in steps:                                               # later step = outer (world) rotation
            a = (Rarm_inv @ axis).normalized()
            composed = mathutils.Matrix.Rotation(math.radians(deg), 3, a) @ composed
            nstep += 1
        bpy.context.view_layer.update()                                       # read the parent-posed head
        pb = arm.pose.bones[bname]; cur = pb.matrix.copy()
        new = (composed @ cur.to_3x3()).to_4x4(); new.translation = cur.translation   # rotate about the FK head; keep it
        pb.matrix = new
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"[posed-roles] {len(items)} role(s) {nstep} step(s): {[r for r, _ in items]}", flush=True)

def rig_character(char_glb, block, assets, out):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=char_glb)
    arm = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"][0]
    cm = [m for m in bpy.context.scene.objects if m.type == "MESH"]
    if len(cm) > 1:                                                       # drop UniRig's stray bounding sphere
        keep = max(cm, key=lambda m: len(m.data.vertices))
        for o in cm:
            if o is not keep: bpy.data.objects.remove(o, do_unlink=True)
    charmesh = max([m for m in bpy.context.scene.objects if m.type == "MESH"], key=lambda m: len(m.data.vertices))
    zs = [(charmesh.matrix_world @ v.co).z for v in charmesh.data.vertices]; figureH = max(zs) - min(zs)
    print(f"[char] {os.path.basename(char_glb)}  figureH={figureH:.3f}  weapons={len(block.get('weapons', []))}  pose={'yes' if block.get('pose',{}).get('bones') else 'no'}", flush=True)
    _pose = block.get("pose") or {}                                       # pose BEFORE weapons (they ride the posed hand)
    if _pose.get("roleRotations"): apply_role_pose(arm, _pose, block.get("roleMap", {}))
    else: apply_pose(arm, _pose)
    if _pose.get("roleRotations") or _pose.get("bones"):                  # bake the posed deformation into the mesh so the export carries it
        for _m in [o for o in bpy.context.scene.objects if o.type == "MESH"]:
            _am = [md for md in _m.modifiers if md.type == "ARMATURE"]
            if _am:
                _am[0].use_deform_preserve_volume = True                  # DQS bake: dual-quaternion skinning avoids the LBS candy-wrapper collapse
                bpy.ops.object.select_all(action='DESELECT'); _m.select_set(True); bpy.context.view_layer.objects.active = _m
                try: bpy.ops.object.modifier_apply(modifier=_am[0].name)   #   at bent joints (Kavan et al. 2008, DOI 10.1145/1409625.1409627). UniRig emits standard LBS
                except Exception as e: print(f"[pose] modifier_apply warn: {e}", flush=True)   #   weights (arXiv:2504.12451), so the raw bake tears the elbow past ~85deg; ROM is capped in the pose too.
    for w in block.get("weapons", []):
        place_v4(w, arm, assets) if "rootTransform" in w else place(w, arm, figureH, assets)
    for o in [m for m in list(bpy.context.scene.objects) if m.type == "MESH" and len(m.data.vertices) < 300]:
        bb = [o.matrix_world @ V(c) for c in o.bound_box]
        if max(max(p[i] for p in bb) - min(p[i] for p in bb) for i in range(3)) > 1.4: bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=True)
    print(f"[export] {out} ({os.path.getsize(out)//1024} KB)", flush=True)

man = json.load(open(MANIFEST, encoding="utf-8")) if MANIFEST else {}
assets = dict(man.get("weapons", {})); assets.update(ASSETS_CLI)
man_chars = man.get("characters", {})

if P.get("format") == "sprite-motion.placements" or "characters" in P:    # whole roster
    outdir = OUTDIR or "."; os.makedirs(outdir, exist_ok=True)
    chars = P.get("characters", [])
    print(f"[bridge] roster: {len(chars)} character(s)", flush=True)
    for block in chars:
        name = block.get("skeleton"); glb = man_chars.get(name)
        if not glb or not os.path.exists(glb):
            print(f"[skip] no rigged GLB mapped for '{name}'", flush=True); continue
        rig_character(glb, block, assets, os.path.join(outdir, f"{name}_placed.glb"))
else:                                                                     # single character
    if not CHAR: print("[error] single placement needs --char <rigged>.glb", flush=True); sys.exit(1)
    rig_character(CHAR, P, assets, OUT or os.path.splitext(CHAR)[0] + "_placed.glb")
print("BRIDGE DONE", flush=True)
