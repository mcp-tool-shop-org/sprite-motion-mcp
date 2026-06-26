"""Decimate a TRELLIS mesh GLB to a target triangle count, preserving UVs + baked material.
TRELLIS meshes are ~800k-vert; game assets want ~30-50k tris. Collapse decimate keeps the
silhouette + UVs; re-rig AFTER so skin weights are computed for the final game-weight mesh.

Run: blender -b --python _decimate.py -- --in <in>.glb --out <out>.glb --target 40000
"""
import bpy, sys, os, bmesh
argv = sys.argv[sys.argv.index("--")+1:]
def arg(n, d=None): return argv[argv.index(n)+1] if n in argv else d
IN = arg("--in"); OUT = arg("--out"); TARGET = int(arg("--target", "40000"))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=IN)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
bpy.ops.object.select_all(action='DESELECT')
for o in meshes: o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1: bpy.ops.object.join()
mesh = bpy.context.view_layer.objects.active; mesh.name = "char_mesh"
# bake any object transform into the geometry so the decimated GLB stays in original world space
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# triangulate first for an accurate tri count + clean collapse
me = mesh.data
bm = bmesh.new(); bm.from_mesh(me)
bmesh.ops.triangulate(bm, faces=bm.faces)
bm.to_mesh(me); bm.free()
before_tris = len(me.polygons); before_verts = len(me.vertices)
print(f"[before] verts={before_verts} tris={before_tris}", flush=True)

ratio = min(1.0, TARGET / max(1, before_tris))
mod = mesh.modifiers.new("dec", 'DECIMATE')
mod.decimate_type = 'COLLAPSE'; mod.ratio = ratio; mod.use_collapse_triangulate = True
bpy.ops.object.modifier_apply(modifier=mod.name)
after_tris = len(mesh.data.polygons); after_verts = len(mesh.data.vertices)
print(f"[after] verts={after_verts} tris={after_tris} ratio={ratio:.4f}", flush=True)

# COLLAPSE leaves orphaned verts + THIN SLIVER triangles (the source of the "ribbon strip / shard"
# artifacts that the vision jury flags on thin plate armor — greaves, sabatons, pauldrons).
# Clean rig-ready mesh: merge near-duplicate verts, DISSOLVE DEGENERATE (kills zero-area slivers),
# strip loose, recompute normals. This is the higher-fidelity fix, not just a higher tri count.
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.remove_doubles(threshold=0.00015)                 # weld coincident verts the collapse left
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.dissolve_degenerate(threshold=0.0002)             # remove near-zero-area sliver triangles
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.delete_loose(use_verts=True, use_edges=True, use_faces=False)
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode='OBJECT')
clean_verts = len(mesh.data.vertices); clean_tris = len(mesh.data.polygons)
print(f"[clean] verts={clean_verts} tris={clean_tris} (removed {after_verts-clean_verts} loose/sliver)", flush=True)

bpy.ops.object.select_all(action='DESELECT'); mesh.select_set(True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', use_selection=True)
print(f"[export] {OUT} ({os.path.getsize(OUT)//1024} KB)", flush=True)
print("DECIMATE OK", flush=True)
