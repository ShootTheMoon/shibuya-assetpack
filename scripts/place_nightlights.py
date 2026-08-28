"""Rebuild MAP_SHIBUYA_NIGHTLIGHTS - the night lighting rig.

This existed only inside the .blend. No .py produced it, so the entire night render was
unreproducible: delete the collection and it was gone for good. Same defect class as the two
S0 found, but larger - 137 lights plus MAP_SHIBUYA_LAMPS/_TREES/_NEON, 221 objects in total.

The rule was recovered by measurement, not guessed. Every one of the 137 lights sits within
1.0 m of a utility pole (137/137), the pole pass generates exactly 274 poles, and the light
z averages 26.67 m against a ~15 m valley floor. So: a warm point light on every SECOND
pole, at lamp-head height. Reading the poles out of the scene rather than re-deriving them
from tran_local.json keeps the two passes in sync by construction - if the pole spacing ever
changes, the lights follow.

Measured constants, all uniform across the 137 originals:
    POINT · energy 1400 W · radius 0.35 m · colour (1.0, 0.88, 0.68) · name NL_Pole###
"""
import bpy
import os
import sys

_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)
import shibuya_placement_lib as SPL

COLL = "MAP_SHIBUYA_NIGHTLIGHTS"
POLE_COLL = "MAP_SHIBUYA_UTILITY"
EVERY = 2                      # 274 poles -> 137 lights, matching the original exactly
# 8.60, not 11.70. The first value came from mean-light-z 26.67 minus an ASSUMED 15 m
# ground, and the assumption was wrong: rebuilding with 11.70 put the rig at z 24.4..39.3
# against the originals' measured 21.2..36.2 - every light 3.1 m too high, because the
# poles' own ground averages ~18 m, not 15. Derived from the real offset instead, and the
# z range is the check.
LAMP_H = 8.60                  # lamp head on a 12.6 m pole
ENERGY = 1400.0
RADIUS = 0.35
COLOUR = (1.0, 0.88, 0.68)     # warm sodium/LED mix


def run(every=EVERY, energy=ENERGY, height=LAMP_H):
    sc = bpy.context.scene
    col = bpy.data.collections.get(COLL)
    if col is None:
        col = bpy.data.collections.new(COLL)
        sc.collection.children.link(col)
    for o in list(col.objects):
        d = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if isinstance(d, bpy.types.Light) and d.users == 0:
            bpy.data.lights.remove(d)

    src = bpy.data.collections.get(POLE_COLL)
    if src is None:
        print("  %s missing - run place_phase1a.py first" % POLE_COLL)
        return 0
    poles = sorted([o for o in src.objects if o.name.startswith("POLE_")],
                   key=lambda o: o.name)
    if not poles:
        print("  no POLE_* objects in %s" % POLE_COLL)
        return 0

    n = 0
    for i, p in enumerate(poles):
        if i % every:
            continue
        lt = bpy.data.lights.new("NL_Pole%03d" % n, type='POINT')
        lt.energy = energy
        lt.color = COLOUR
        lt.shadow_soft_size = RADIUS
        ob = bpy.data.objects.new("NL_Pole%03d" % n, lt)
        ob.location = (p.location.x, p.location.y, p.location.z + height)
        col.objects.link(ob)
        n += 1
    zs = [o.location.z for o in col.objects]
    lo, hi = min(zs), max(zs)
    # the originals measured 21.2 .. 36.2; drifting off that means LAMP_H is wrong again
    ok = abs(lo - 21.2) < 1.5 and abs(hi - 36.2) < 1.5
    print("  %s: %d point lights on %d poles (every %d) | %.0f W r=%.2f | z %.1f..%.1f  %s"
          % (COLL, n, len(poles), every, energy, RADIUS, lo, hi,
             "(matches the originals' 21.2..36.2)" if ok
             else "!! originals were 21.2..36.2 - check LAMP_H"))
    return n


if globals().get("__name__") == "__main__":
    run()
    print("PLACE NIGHTLIGHTS DONE")
