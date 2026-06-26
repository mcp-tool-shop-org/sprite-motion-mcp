"""DIAGNOSE + CLEAN the UniRig auto-skin on the blackguard so rigid plate armor deforms cleaner.
Grounded in the verified deform science: UniRig emits standard LBS weights (arXiv:2504.12451) ->
candy-wrapper at bent joints (Kavan 2008); first-line fix is weight cleanup (limit influences +
normalize + smooth at the joint) before correctives. Rigid plate wants near-rigid binding (1 dominant
bone) so the bend creases instead of melting.

Phase A: DIAGNOSE (numeric, reliable) - influence-count histogram, stray cross-region weights at the
right-arm verts, weight 'softness' at the elbow band.
Phase B (--apply): limit_total(4) + normalize + optional rigidify (snap arm verts toward dominant
limb bone by --rigidify factor) + smooth, then export a cleaned rigged glb.

Run (diagnose):  blender -b --python _clean_skin.py -- --glb blackguard/blackguard_dec_rigged.glb
Run (clean):     blender -b --python _clean_skin.py -- --glb <in>.glb --apply --rigidify 0.7 --out <out>.glb
"""
import bpy, sys, math, mathutils
argv = sys.argv[sys.argv.index("--")+1:]
def arg(n, d=None): return argv[argv.index(n)+1] if n in argv else d
def has(n): return n in argv
GLB = arg("--glb"); OUT = arg("--out"); APPLY = has("--apply"); RIGID = float(arg("--rigidify", "0.0"))
V = mathutils.Vector

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
arm = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"][0]
# drop stray bounding sphere
for o in [m for m in bpy.context.scene.objects if m.type == "MESH" and len(m.data.vertices) < 300]:
    bb = [o.matrix_world @ v.co for v in o.data.vertices]
    if bb and max(max(p[i] for p in bb)-min(p[i] for p in bb) for i in range(3)) > 1.4: bpy.data.objects.remove(o, do_unlink=True)
m = max([o for o in bpy.context.scene.objects if o.type == "MESH"], key=lambda o: len(o.data.vertices))
gi2name = {g.index: g.name for g in m.vertex_groups}
name2gi = {g.name: g.index for g in m.vertex_groups}

ARM_R = {"bone_6","bone_7","bone_8","bone_9"}                  # shoulder/upper/fore/hand R
ARM_R_GI = {name2gi[b] for b in ARM_R if b in name2gi}
# elbow band: verts near bone_8 head (the elbow) in world
elbow = arm.matrix_world @ arm.data.bones["bone_8"].head_local

from collections import Counter
infl_hist = Counter(); stray = 0; elbow_verts = 0; elbow_blend = 0
maxinfl = 0
for v in m.data.vertices:
    gs = [(g.group, g.weight) for g in v.groups if g.weight > 1e-4]
    infl_hist[len(gs)] += 1; maxinfl = max(maxinfl, len(gs))
    wpos = m.matrix_world @ v.co
    # right-arm vert if dominant group is an arm-R bone
    if gs:
        dom = max(gs, key=lambda t: t[1])[0]
        if dom in ARM_R_GI:
            # stray = weight to a non-arm, non-finger bone (torso/leg/left)
            for grp, w in gs:
                nm = gi2name.get(grp, "")
                if grp not in ARM_R_GI and not (nm.startswith("bone_1") or nm.startswith("bone_2")) and w > 0.12:
                    if nm in ("bone_0","bone_3","bone_32","bone_33","bone_36","bone_37","bone_19","bone_20"): stray += 1; break
    if (wpos - elbow).length < 0.05:                          # elbow band
        elbow_verts += 1
        if len(gs) >= 3 or (gs and max(g[1] for g in gs) < 0.6): elbow_blend += 1   # heavily blended = candy-wrapper risk

print("=== SKIN DIAGNOSIS (blackguard) ===", flush=True)
print(f"  verts={len(m.data.vertices)}  vgroups={len(m.vertex_groups)}  max_influences/vert={maxinfl}", flush=True)
print(f"  influence-count histogram: {dict(sorted(infl_hist.items()))}", flush=True)
print(f"  right-arm verts with STRAY torso/leg/left weight(>0.12): {stray}", flush=True)
print(f"  elbow-band verts={elbow_verts}  heavily-blended(>=3 infl or max<0.6)={elbow_blend}  ({100*elbow_blend/max(1,elbow_verts):.0f}%)", flush=True)

if APPLY:
    bpy.ops.object.select_all(action='DESELECT'); m.select_set(True); bpy.context.view_layer.objects.active = m
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.vertex_group_limit_total(limit=4)                    # standard cleanup: <=4 influences
    bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    if RIGID > 0:
        # rigidify: for verts dominated by a LIMB bone, push weight toward the dominant bone (crease, not melt)
        for v in m.data.vertices:
            gs = [(g.group, g.weight) for g in v.groups if g.weight > 1e-4]
            if not gs: continue
            dom_grp, dom_w = max(gs, key=lambda t: t[1])
            nm = gi2name.get(dom_grp, "")
            is_limb = nm in ("bone_1","bone_2","bone_3",                                  # torso/breastplate: rigid plate twists+leans as a unit (else the spine twist candy-wrappers the chest armor)
                              "bone_6","bone_7","bone_8","bone_9","bone_13","bone_14","bone_15","bone_16",
                              "bone_20","bone_21","bone_22","bone_23","bone_24","bone_25","bone_26","bone_27")
            if is_limb and dom_w < 0.98:
                for g in v.groups:
                    if g.group == dom_grp: g.weight = dom_w + (1.0 - dom_w) * RIGID
                    else: g.weight = g.weight * (1 - RIGID)
        bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    print(f"[clean] limit_total(4)+normalize" + (f"+rigidify({RIGID})" if RIGID>0 else ""), flush=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', use_selection=True)
    print(f"[export] {OUT}", flush=True)
print("CLEAN DONE", flush=True)
