"""Classify what is actually wrong with the PLATEAU buildings.

"Some buildings still look strange" is an observation, not a defect list. This turns it
into counts per failure mode so the fixes can be ranked and their effect measured, instead
of chasing whatever the last render happened to show.

Each check is chosen because it produces a DISTINCT visual symptom:

  [T] no texture at all          -> flat grey box among photo-textured neighbours
  [M] texture file missing       -> renders magenta / black
  [U] degenerate UVs             -> the whole face samples ONE texel: a smear of flat colour
  [D] low texel density          -> a photo stretched over too many metres, blurred to mush
  [N] inward-facing normals      -> reads black, or the interior shows through
  [Z] zero-area faces            -> shading artefacts, z-fighting slivers
  [R] no roof                    -> open box seen from above
  [X] interpenetrating neighbour -> two solids fighting in the same space
  [S] shape outlier              -> a 3 m x 3 m x 90 m spike, or a 1-face sliver

Run headless; prints a table and the worst offenders per mode with their names so they can
be rendered and looked at.
"""
import bpy
import os
import math
import collections
from mathutils import Vector

import sys
_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)
import shibuya_placement_lib as SPL

UV_DEGEN = 1e-7          # UV-space area below this = the face samples a single texel
DENSITY_LOW = 3.0        # texels per metre; below this a facade photo is visibly mush
AREA_MIN = 1e-5          # world-space face area treated as degenerate


def img_of(mat):
    if mat is None or not mat.use_nodes:
        return None
    for n in mat.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image:
            return n.image
    return None


def analyse(ob):
    me = ob.data
    r = dict(name=ob.name, tris=sum(len(p.vertices)-2 for p in me.polygons),
             verts=len(me.vertices))
    vs = me.vertices
    d = [max(v.co[i] for v in vs)-min(v.co[i] for v in vs) for i in range(3)]
    r["dims"] = d
    r["h"] = d[2]

    # ---- materials / images ----
    imgs = {}
    n_notex = 0
    n_missing = 0
    for i, m in enumerate(me.materials):
        im = img_of(m)
        imgs[i] = im
        if im is None:
            n_notex += 1
        else:
            p = bpy.path.abspath(im.filepath) if im.filepath else ""
            if not im.packed_file and not (p and os.path.exists(p)):
                n_missing += 1
    r["mats"] = len(me.materials)
    r["mat_notex"] = n_notex
    r["mat_missing"] = n_missing

    uvl = me.uv_layers[0].uv if me.uv_layers else None
    a_degen = 0.0
    a_lowden = 0.0
    a_total = 0.0
    a_zero = 0
    dens = []
    for p in me.polygons:
        a = p.area
        a_total += a
        if a < AREA_MIN:
            a_zero += 1
            continue
        if uvl is None:
            a_degen += a
            continue
        li = list(p.loop_indices)
        uv = [uvl[k].vector for k in li]
        # shoelace in UV space
        auv = 0.0
        for k in range(len(uv)):
            x1, y1 = uv[k]
            x2, y2 = uv[(k+1) % len(uv)]
            auv += x1*y2 - x2*y1
        auv = abs(auv)*0.5
        if auv < UV_DEGEN:
            a_degen += a
            continue
        im = imgs.get(p.material_index)
        if im is None:
            continue
        px = max(im.size) or 1
        # texels per metre along the surface
        t_per_m = math.sqrt(auv/a) * px
        dens.append(t_per_m)
        if t_per_m < DENSITY_LOW:
            a_lowden += a
    r["area"] = a_total
    r["uv_degen_frac"] = a_degen/a_total if a_total else 1.0
    r["lowden_frac"] = a_lowden/a_total if a_total else 0.0
    r["density_med"] = sorted(dens)[len(dens)//2] if dens else 0.0
    r["zero_faces"] = a_zero

    # ---- normals: fraction of area whose normal points at the object centroid ----
    c = Vector((sum(v.co.x for v in vs)/len(vs), sum(v.co.y for v in vs)/len(vs),
                sum(v.co.z for v in vs)/len(vs)))
    a_in = 0.0
    for p in me.polygons:
        if p.area < AREA_MIN:
            continue
        if (p.center - c).dot(p.normal) < 0:
            a_in += p.area
    r["inward_frac"] = a_in/a_total if a_total else 0.0

    # ---- roof: any upward face in the top 15% of the height ----
    zmax = max(v.co.z for v in vs)
    zmin = min(v.co.z for v in vs)
    band = zmax - (zmax-zmin)*0.15
    r["roof_area"] = sum(p.area for p in me.polygons
                         if p.normal.z > 0.55 and p.center.z >= band)
    r["footprint"] = d[0]*d[1]
    return r


def run(coll="MAP_SHIBUYA_BUILDINGS", show=6):
    c = bpy.data.collections.get(coll)
    if c is None:
        print("no collection", coll); return
    objs = [o for o in c.objects if o.type == 'MESH' and o.data.polygons]
    print("=== building audit: %d objects in %s\n" % (len(objs), coll))
    rows = [analyse(o) for o in objs]

    modes = [
        ("[T] no texture on any slot",
         lambda r: r["mats"] > 0 and r["mat_notex"] == r["mats"], "mat_notex"),
        ("[M] texture file missing",
         lambda r: r["mat_missing"] > 0, "mat_missing"),
        ("[U] >30% area on degenerate UVs (single-texel smear)",
         lambda r: r["uv_degen_frac"] > 0.30, "uv_degen_frac"),
        ("[D] >50%% area under %.1f texels/m (blurred photo)" % DENSITY_LOW,
         lambda r: r["lowden_frac"] > 0.50, "lowden_frac"),
        ("[N] >30% area facing inward (reads black)",
         lambda r: r["inward_frac"] > 0.30, "inward_frac"),
        ("[Z] degenerate faces",
         lambda r: r["zero_faces"] > 0, "zero_faces"),
        ("[R] no roof face in the top 15%",
         lambda r: r["roof_area"] < 1.0, "roof_area"),
        ("[S] shape outlier (h>60 m on a <120 m2 footprint, or <4 faces)",
         lambda r: (r["h"] > 60 and r["footprint"] < 120) or r["tris"] < 4, "h"),
    ]
    hits = {}
    print("%-58s %6s %7s" % ("failure mode", "count", "share"))
    for label, test, key in modes:
        sel = [r for r in rows if test(r)]
        hits[label] = (sel, key)
        print("%-58s %6d %6.1f%%" % (label, len(sel), 100.0*len(sel)/len(rows)))

    print("\n--- worst offenders ---")
    for label, (sel, key) in hits.items():
        if not sel:
            continue
        print("\n  %s" % label)
        rev = key not in ("roof_area", "density_med")
        for r in sorted(sel, key=lambda r: r[key], reverse=rev)[:show]:
            print("      %-30s tris=%-6d %5.1fx%5.1fx%5.1f m  %s=%s  texels/m=%.1f"
                  % (r["name"], r["tris"], r["dims"][0], r["dims"][1], r["dims"][2],
                     key, (("%.2f" % r[key]) if isinstance(r[key], float) else r[key]),
                     r["density_med"]))

    d = [r["density_med"] for r in rows if r["density_med"] > 0]
    d.sort()
    if d:
        print("\n  texel density across %d buildings: p10 %.1f  median %.1f  p90 %.1f /m"
              % (len(d), d[len(d)//10], d[len(d)//2], d[9*len(d)//10]))
    clean = [r for r in rows if not any(t(r) for _, t, _ in modes)]
    print("  buildings with NO flagged defect: %d of %d (%.1f%%)"
          % (len(clean), len(rows), 100.0*len(clean)/len(rows)))
    return rows, hits


if globals().get("__name__") == "__main__":
    run()
    print("BUILDING AUDIT DONE")
