"""S6: re-measure every asset .blend and rewrite asset_manifest.csv, then render the
missing previews.

The manifest was written before S4 and S5 and is now wrong on most rows: the taxi still
claims 32,449 triangles, the vending machine 16,380, the shopfronts 46, and the 16 new
signboard variants plus the three sedan variants are absent entirely. A manifest that
disagrees with the assets is worse than no manifest, because it is the thing a reviewer
reads instead of opening the files.

Every number here is MEASURED from the .blend, never carried over. The `notes` column is
preserved from the old manifest where the asset still exists, since that text is authored
description that no measurement can regenerate.

Previews: 04_Previews had 18 images for 72 assets. The 41 ZK kit modules go onto contact
sheets rather than 41 separate renders - they are 24-142 triangle parts that mean nothing
in isolation.

Run headless, one Blender per .blend (driven by s6_run_manifest.py).
"""
import bpy
import bmesh
import csv
import json
import os

PACK = r"C:\Work\blender\ShibuyaAssetPack"
SRC = os.path.join(PACK, "00_Source_Blender")
DOC = os.path.join(PACK, "05_Documentation")
PREV = os.path.join(PACK, "04_Previews")
COLS = ["asset_name", "category", "collection", "scale_meters", "poly_count",
        "vertex_count", "material_count", "texture_status", "export_fbx_path",
        "export_glb_path", "quality_status", "notes"]

# which map collection each category lands in
COLLECTION = {
    "UP_Utility_Overhead": "MAP_SHIBUYA_UTILITY",
    "SF_Street_Furniture": "MAP_SHIBUYA_STREETFURN",
    "GR_Ground_Detail":    "MAP_SHIBUYA_TACTILE",
    "ZK_Zakkyo_Facade_Kit": "MAP_SHIBUYA_ZAKKYO",
    "VH_Vehicles":         "MAP_SHIBUYA_VEHICLES",
    "CR_Crowd":            "MAP_SHIBUYA_CROWD",
    "VG_Vegetation":       "MAP_SHIBUYA_TREES",
    "LM_Landmarks":        "MAP_SHIBUYA_LANDMARKS",
}


def texture_status(me):
    imgs = []
    for m in me.materials:
        if m is None or not m.use_nodes:
            continue
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image:
                imgs.append((n.image.name, max(n.image.size)))
    if not imgs:
        return "procedural flat colours (no image maps)"
    uniq = sorted(set(imgs))
    return "%d image(s), max %d px: %s" % (
        len(uniq), max(p for _, p in uniq), ", ".join(n for n, _ in uniq[:4]))


def measure(path, category):
    rows = []
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or not ob.data.polygons or ob.name.startswith("REF_"):
            continue
        me = ob.data
        vs = me.vertices
        d = [max(v.co[i] for v in vs) - min(v.co[i] for v in vs) for i in range(3)]
        rows.append({
            "asset_name": ob.name,
            "category": category,
            "collection": COLLECTION.get(category, ""),
            "scale_meters": "%.2f x %.2f x %.2f" % tuple(d),
            "poly_count": sum(len(p.vertices)-2 for p in me.polygons),
            "vertex_count": len(vs),
            "material_count": len(me.materials),
            "texture_status": texture_status(me),
            "export_fbx_path": "01_Exports_FBX/%s/%s.fbx" % (category, ob.name),
            "export_glb_path": "02_Exports_GLB/%s/%s.glb" % (category, ob.name),
            "quality_status": "PENDING_USER_REVIEW",
            "notes": "",
        })
    return rows


if __name__ != "never":
    import sys
    path = sys.argv[-2]
    category = sys.argv[-1]
    out = measure(path, category)
    print("@@JSON@@" + json.dumps(out, ensure_ascii=False))
