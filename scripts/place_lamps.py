"""Rebuild MAP_SHIBUYA_LAMPS.

Honest status: this is a REWRITE, not a recovery. The other three orphan collections had
their rules recovered by measurement - the night lights matched utility poles 137/137, the
trees matched OSM+PLATEAU 45/45 - but the 31 original lamps match nothing. Not the 3 OSM
`highway=street_lamp` nodes (0/31), not bus stops (0/31), not traffic signals (0/31); only
16 of 31 are even near a sidewalk ring vertex, their nearest-neighbour spacing runs from
23.9 m to 349.8 m, and they reach |r| = 433 m. That is a hand-scatter, and reproducing a
hand-scatter faithfully would mean shipping the coordinate list, which is not a rule.

It is also why three of them were sunk up to 3.93 m below the terrain: they sit past the
±320 m crop where the outskirts undulation kicks in, and they were never re-draped after
the ground was rebuilt on the graded grid.

So the rule here is one that can be stated and checked: modern street lamps along the two
NAMED arterial roads, at a fixed interval, on the sidewalk side, inside the crop where the
ground is authoritative.
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
ASSET = os.path.join(PACK, "SF_Street_Furniture", "SF_StreetLamp_A.blend")
NAME = "SF_StreetLamp_A"
COLL = "MAP_SHIBUYA_LAMPS"

SPACING = 38.0        # arterial lamp interval
CROP = 300.0          # stay inside the flat, authoritative ground - see the docstring
MIN_SEP = 18.0        # never two lamps within this of each other
POLE_CLEAR = 9.0      # do not stand a lamp next to a utility pole


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


def run(seed=20260731, spacing=SPACING):
    rnd = random.Random(seed)
    m = master()
    if m is None:
        print("  !! %s not found" % NAME)
        return 0

    col = bpy.data.collections.get(COLL)
    if col is None:
        col = bpy.data.collections.new(COLL)
        bpy.context.scene.collection.children.link(col)
    for o in list(col.objects):
        bpy.data.objects.remove(o, do_unlink=True)

    T = json.load(open(os.path.join(SHIB, "tran", "tran_local.json"), encoding="utf-8"))
    # the two named arterials: 国道246号 and 都道305号. Named roads are the ones that carry
    # arterial lighting; unnamed service polygons are not lit this way.
    art = [p for p in T["polys"]
           if p["kind"] == "TA" and p["fn"] == "1000" and not p.get("elevated")
           and p.get("name")]
    if not art:
        print("  no named arterial polygons - nothing to light")
        return 0

    G = SPL.GroundSampler()
    occ = SPL.Occupancy(MIN_SEP)
    # keep clear of the utility poles, which carry their own overhead gear
    pol = SPL.Occupancy(POLE_CLEAR)
    up = bpy.data.collections.get("MAP_SHIBUYA_UTILITY")
    if up:
        for o in up.objects:
            if o.name.startswith("POLE_"):
                pol.mark(o.location.x, o.location.y)

    n = 0
    n_skip = 0
    for p in art:
        pts = [(q[0], q[1]) for q in p["pts"]]
        if len(pts) < 3:
            continue
        ax, ay, cx, cy = SPL.pca(pts)          # run down the polygon's own long axis
        nx, ny = -ay, ax
        proj = [(x-cx)*ax + (y-cy)*ay for x, y in pts]
        off = [(x-cx)*nx + (y-cy)*ny for x, y in pts]
        half = max(abs(o) for o in off) * 0.82  # sidewalk side, not the carriageway centre
        t = min(proj) + spacing*0.5
        while t < max(proj):
            for side in (1, -1):
                x = cx + ax*t + nx*half*side
                y = cy + ay*t + ny*half*side
                t_ok = (abs(x) <= CROP and abs(y) <= CROP
                        and SPL.inside(pts, cx + ax*t, cy + ay*t)
                        and pol.free(x, y) and occ.try_mark(x, y))
                if not t_ok:
                    n_skip += 1
                    continue
                z = G.z(x, y)
                if z is None:                  # fail closed
                    n_skip += 1
                    continue
                o = m.copy()
                o.data = m.data
                o.name = "LAMP_%03d" % n
                o.hide_render = False
                o.hide_viewport = False
                o.location = (x, y, z)
                # head overhangs the carriageway, so face the lamp inward
                o.rotation_euler = (0, 0, math.atan2(-ny*side, -nx*side))
                col.objects.link(o)
                n += 1
            t += spacing
    zs = [o.location.z for o in col.objects]
    print("  %s: %d lamps on %d named arterial polygons (%d candidates rejected)"
          % (COLL, n, len(art), n_skip))
    if zs:
        print("      z %.1f..%.1f  (all inside +/-%.0f m where the ground is flat)"
              % (min(zs), max(zs), CROP))
    G.report("lamps")
    return n


if globals().get("__name__") == "__main__":
    run()
    print("PLACE LAMPS DONE")
