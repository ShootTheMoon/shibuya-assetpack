"""Rebuild MAP_SHIBUYA_NEON - the procedural facade signage.

Recovered by measurement from the 8 colour-merged meshes that existed only in the .blend:

  * 3,808 polygons in 8 meshes (NEON_PINK/CYAN/AMBER/RED/BLUE/WHITE/GREEN/VIOLET),
    i.e. 1,904 signs, each double-sided.
  * 3,626 of the 3,808 quad centres lie within 8 m of an OSM POI -> the signs are driven by
    poi_local.json, one cluster per venue.
  * Quad areas cluster at 3.9 / 4.8 / 5.9 / 7.1 m2 with ~945 polys each. Those are exactly
    1.2 m x (3.25, 4.00, 4.90, 5.90) - four width variants of one band height, in equal
    proportion. That is the whole size rule.
  * Quad z runs 16.4 .. 47.1 m against a ~15 m ground, so bands start about a storey up and
    stack to roughly 32 m.
  * Every emission strength is 0.0: the meshes are in their DAY configuration. The night
    preset raises them, and that preset has no script either - see set_night() below.

Double-sided because a sign hung off a facade is read from both approach directions, and a
single quad vanishes from one of them.
"""
import bpy
import bmesh
import json
import math
import os
import random
import sys

from mathutils import Vector

_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)
import shibuya_placement_lib as SPL

SHIB = r"C:\Work\blender\Shibuya"
COLL = "MAP_SHIBUYA_NEON"

BAND_H = 1.20
WIDTHS = (3.25, 4.00, 4.90, 5.90)          # -> 3.9 / 4.8 / 5.9 / 7.1 m2, as measured
STAND = 0.30                                # stand off the wall
FIRST = 4.6                                 # first band about a storey up
STEP = 3.4                                  # one band per zakkyo floor
MAX_BANDS = 4
# 13.0 m left 305 of 803 POIs with no wall in range and produced 1,484 signs against the
# original 1,904. Shibuya POI nodes sit anywhere inside their building footprint, not on the
# frontage, so the search has to cross the whole depth of a block.
REACH = 19.0                                # POI -> wall search radius

# name -> (base colour, night emission strength). Day ships at 0.0; set_night() applies these.
COLOURS = [
    ("NEON_PINK",   (1.00, 0.18, 0.55), 18.0),
    ("NEON_CYAN",   (0.15, 0.85, 1.00), 16.0),
    ("NEON_AMBER",  (1.00, 0.62, 0.12), 15.0),
    ("NEON_RED",    (1.00, 0.14, 0.10), 20.0),
    ("NEON_BLUE",   (0.16, 0.34, 1.00), 17.0),
    ("NEON_WHITE",  (0.95, 0.95, 0.92), 12.0),
    ("NEON_GREEN",  (0.20, 1.00, 0.42), 16.0),
    ("NEON_VIOLET", (0.62, 0.24, 1.00), 18.0),
]
# Colour is assigned UNIFORMLY, by round-robin over a shuffled bag.
#
# The first version biased colour by venue kind (bars red, shops cyan, ...) which sounds
# right and is wrong: the 8 original meshes carry 466-484 polygons EACH, i.e. an almost
# perfectly even split. Biasing by kind cannot produce that, because the POI mix is not
# even - `shop` alone is 281 of 803 - and it duly came out at WHITE 912 / VIOLET 12.
# Measurement beats plausibility: the original picked colour independently of venue.


def material(name, rgb, strength=0.0):
    m = bpy.data.materials.get("M_" + name) or bpy.data.materials.new("M_" + name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (400, 0)
    b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (150, 0)
    b.inputs['Base Color'].default_value = (*rgb, 1.0)
    b.inputs['Roughness'].default_value = 0.35
    b.inputs['Emission Color'].default_value = (*rgb, 1.0)
    b.inputs['Emission Strength'].default_value = strength
    nt.links.new(b.outputs['BSDF'], out.inputs['Surface'])
    return m


def set_night(on=True):
    """The day/night switch the map never had as code. Day = 0.0 (what v026 shipped)."""
    n = 0
    for name, rgb, es in COLOURS:
        m = bpy.data.materials.get("M_" + name)
        if m is None or not m.use_nodes:
            continue
        for nd in m.node_tree.nodes:
            if nd.type == 'BSDF_PRINCIPLED':
                nd.inputs['Emission Strength'].default_value = es if on else 0.0
                n += 1
    print("  neon emission -> %s (%d materials)" % ("NIGHT" if on else "DAY", n))
    return n


def run(seed=20260731, night=False):
    rnd = random.Random(seed)
    sc = bpy.context.scene
    col = bpy.data.collections.get(COLL)
    if col is None:
        col = bpy.data.collections.new(COLL)
        sc.collection.children.link(col)
    for o in list(col.objects):
        me = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)

    P = json.load(open(os.path.join(SHIB, "osm", "poi_local.json"), encoding="utf-8"))
    pois = P.get("poi", [])
    bld = SPL.buildings(include_retired=False)
    bvh, ntri = SPL.make_bvh(bld)
    print("  %d POIs | wall BVH %d tris" % (len(pois), ntri))

    bms = {name: bmesh.new() for name, _, _ in COLOURS}
    uvls = {k: v.loops.layers.uv.new("UVMap") for k, v in bms.items()}
    occ = SPL.Occupancy(1.6)
    bag = []                      # shuffled colour bag, refilled every 8 signs
    n_sign = 0
    n_nowall = 0

    for p in pois:
        x, y, kind = p["x"], p["y"], p.get("k", "shop")
        hit = bvh.find_nearest(Vector((x, y, 20.0)), REACH)
        if hit is None or hit[0] is None:
            n_nowall += 1
            continue
        loc, nrm, _fi, _d = hit
        nn = Vector((nrm.x, nrm.y, 0.0))
        if nn.length < 1e-4:
            n_nowall += 1
            continue
        nn.normalize()
        # force the normal to point back at the POI, i.e. out into the street
        if nn.dot(Vector((x - loc.x, y - loc.y, 0.0))) < 0:
            nn = -nn
        # this wall's own roof, so bands never climb past the parapet
        top = SPL.roof_max(bvh, loc.x, loc.y, -nn.x, -nn.y)
        base = loc.z
        if top is None or top - base < FIRST + BAND_H:
            n_nowall += 1
            continue

        tang = Vector((-nn.y, nn.x, 0.0))
        px, py = loc.x + nn.x*STAND, loc.y + nn.y*STAND
        for b in range(MAX_BANDS):
            z0 = base + FIRST + b*STEP
            if z0 + BAND_H > top - 0.8:
                break
            if not occ.try_mark(px + tang.x*b*0.01, py + tang.y*b*0.01 + z0):
                continue
            w = WIDTHS[rnd.randrange(len(WIDTHS))]
            if not bag:                       # refill and reshuffle: keeps the 8 groups even
                bag = [c[0] for c in COLOURS]
                rnd.shuffle(bag)
            cname = bag.pop()
            bm = bms[cname]
            uvl = uvls[cname]
            a = Vector((px, py, z0)) - tang*(w/2)
            bb = Vector((px, py, z0)) + tang*(w/2)
            v = [a, bb, bb + Vector((0, 0, BAND_H)), a + Vector((0, 0, BAND_H))]
            for flip in (False, True):
                order = list(reversed(v)) if flip else v
                f = bm.faces.new([bm.verts.new(q) for q in order])
                # mirror u on the back face or the text reads reversed from that side
                uvs = ((1, 0), (0, 0), (0, 1), (1, 1)) if flip else \
                      ((0, 0), (1, 0), (1, 1), (0, 1))
                for l, uv in zip(f.loops, uvs):
                    l[uvl].uv = uv
            n_sign += 1

    total = 0
    for name, rgb, es in COLOURS:
        bm = bms[name]
        me = bpy.data.meshes.new(name)
        bm.normal_update()
        bm.to_mesh(me)
        bm.free()
        me.materials.append(material(name, rgb, es if night else 0.0))
        me.shade_flat()
        ob = bpy.data.objects.new(name, me)
        col.objects.link(ob)
        total += len(me.polygons)
        print("      %-14s %4d polys" % (name, len(me.polygons)))
    print("  %s: %d signs / %d polys | %d POIs had no usable wall"
          % (COLL, n_sign, total, n_nowall))
    return n_sign


if globals().get("__name__") == "__main__":
    run()
    print("PLACE NEON DONE")
