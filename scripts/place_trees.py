"""Rebuild MAP_SHIBUYA_TREES.

Another collection that existed only in the .blend. The rule was recovered by matching the
45 placed trees against the source data: 21 land exactly (within 2 m) on the OSM
`natural=tree` nodes in poi_local.json, and the PLATEAU `veg` extract carries exactly 24
SolitaryVegetationObject records - 21 + 24 = 45, the collection count.

PLATEAU records carry a real measured height, so those trees are scaled to it rather than
jittered. The OSM nodes carry no height, so they get the jitter the originals had
(measured range 0.84 - 1.22).
"""
import bpy
import json
import math
import os
import random
import sys

_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)
import shibuya_placement_lib as SPL

SHIB = r"C:\Work\blender\Shibuya"
PACK = r"C:\Work\blender\ShibuyaAssetPack\00_Source_Blender"
ASSET = os.path.join(PACK, "VG_Vegetation", "VG_StreetTree_A.blend")
NAME = "VG_StreetTree_A"
COLL = "MAP_SHIBUYA_TREES"
CROP = 315.0
SCALE_LO, SCALE_HI = 0.84, 1.22      # measured spread of the 45 originals


def master():
    o = bpy.data.objects.get(NAME)
    if o is None:
        with bpy.data.libraries.load(ASSET, link=False) as (df, dt):
            dt.objects = [n for n in df.objects if n == NAME]
        o = bpy.data.objects.get(NAME)
    if o and not o.users_collection:
        bpy.context.scene.collection.objects.link(o)
    if o:
        o.hide_render = True
        o.hide_viewport = True
    return o


def run(seed=20260731):
    rnd = random.Random(seed)
    m = master()
    if m is None:
        print("  !! %s not found in %s" % (NAME, ASSET))
        return 0
    native = max(v.co.z for v in m.data.vertices) - min(v.co.z for v in m.data.vertices)

    col = bpy.data.collections.get(COLL)
    if col is None:
        col = bpy.data.collections.new(COLL)
        bpy.context.scene.collection.children.link(col)
    for o in list(col.objects):
        bpy.data.objects.remove(o, do_unlink=True)

    G = SPL.GroundSampler()
    pts = []
    vp = os.path.join(SHIB, "frn", "veg_local.json")
    if os.path.exists(vp):
        for r in json.load(open(vp, encoding="utf-8"))["objs"]:
            # PLATEAU measured the height, so use it instead of inventing a jitter
            pts.append((r["cx"], r["cy"], (r.get("h") or native)/native, "veg"))
    pp = os.path.join(SHIB, "osm", "poi_local.json")
    if os.path.exists(pp):
        for xy in json.load(open(pp, encoding="utf-8")).get("trees", []):
            pts.append((xy[0], xy[1], rnd.uniform(SCALE_LO, SCALE_HI), "osm"))

    occ = SPL.Occupancy(2.5)
    n = 0
    n_skip = 0
    for x, y, sc, src in pts:
        if abs(x) > CROP or abs(y) > CROP:
            n_skip += 1
            continue
        if not occ.try_mark(x, y):
            n_skip += 1
            continue
        z = G.z(x, y)
        if z is None:                     # fail closed - never invent a height
            n_skip += 1
            continue
        o = m.copy()
        o.data = m.data                   # linked duplicate
        o.name = "TREE_%03d" % n
        o.hide_render = False
        o.hide_viewport = False
        o.location = (x, y, z)
        o.rotation_euler = (0, 0, rnd.uniform(0, 6.283))
        o.scale = (sc, sc, sc)
        col.objects.link(o)
        n += 1
    print("  %s: %d trees (%d skipped) from %d candidates | native height %.2f m"
          % (COLL, n, n_skip, len(pts), native))
    G.report("trees")
    return n


if globals().get("__name__") == "__main__":
    run()
    print("PLACE TREES DONE")
