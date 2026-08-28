"""Single-entry coordinate audit for the whole Shibuya map. Run it as a GATE.

Replaces audit_placement.py, which had three problems: nothing ever called it, it only
looked at one collection (MAP_SHIBUYA_ZAKKYO), and the four single-mesh builders - station,
hall, viaduct, sidewalk - were structurally invisible to it even though they are the
objects that actually drive geometry through buildings.

Renders are not a check. Five zakkyo re-placement rounds were spent on this: only two were
real placer bugs, three were defects in the CHECKING criteria (dedup keyed on module name,
distance measured to the AABB, roof sampled straight up from the instance). So every
criterion here carries the measurement that justifies it, and the baseline is captured on
an UNMODIFIED scene before any fix lands - a number with no baseline cannot be falsified.

    audit_map()                      # everything, prints tables, returns a dict
    audit_map(json_out="a.json")     # ... and writes it for a later diff

Whitelisting: the user's call was that station columns and viaduct piers legitimately
share walls with buildings (deleting them leaves the deck floating), so intersections are
bucketed BY MATERIAL INDEX and only the support indices are excused. Deck, ribbon, slab
and barrier stay hard failures - otherwise the allowance hides the next regression.
"""
import bpy
import os
import math
import json
import hashlib
import struct
import collections
from mathutils import Vector

import sys
_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)
import shibuya_placement_lib as SPL

SHIB = r"C:\Work\blender\Shibuya"
PACK = r"C:\Work\blender\ShibuyaAssetPack"
TEXD = os.path.join(PACK, "03_Textures")

# A parapet or signboard standing 1-3 m proud of the roofline is normal on a real
# building; a 0.8 m threshold flagged 338 instances of which only 6 were actually wrong.
ABOVE_TOL = 4.0
# These sit ON a surface, so probing from z+1.2 would always report exactly 1.2 m.
ON_SURFACE = ("ZK_ACUnit_A", "ZK_WaterTank_A")
# Module pairs placed together on purpose - not an overlap.
INTENDED = {frozenset(("SHOP", "ZK_Storefront_Module_A")),
            frozenset(("SIGN", "ZK_SignRail_Module_A"))}

# mode: "wall" instances hang off a facade, "ground" instances stand on the terrain.
INSTANCE_SPEC = {
    "MAP_SHIBUYA_ZAKKYO":     dict(mode="wall",   quant=0.5,  gtol=None),
    "MAP_SHIBUYA_TACTILE":    dict(mode="ground", quant=0.25, gtol=0.40),
    "MAP_SHIBUYA_UTILITY":    dict(mode="ground", quant=1.0,  gtol=0.50),
    "MAP_SHIBUYA_STREETFURN": dict(mode="ground", quant=1.0,  gtol=0.50),
    "MAP_SHIBUYA_VEHICLES":   dict(mode="ground", quant=2.0,  gtol=0.50),
    "MAP_SHIBUYA_TREES":      dict(mode="ground", quant=2.0,  gtol=0.60),
    "MAP_SHIBUYA_LAMPS":      dict(mode="ground", quant=1.0,  gtol=0.50),
    "MAP_SHIBUYA_CROWD":      dict(mode="ground", quant=0.5,  gtol=0.40),
    # landmarks deliberately seat into their podium (109 at zmin-0.4, Scramble at -0.3),
    # so ground deviation is reported but is not a defect
    "MAP_SHIBUYA_LANDMARKS":  dict(mode="ground", quant=4.0,  gtol=None),
}

# material index -> (name, excused). Excused indices are load-bearing supports that share
# walls with buildings in reality.
MESH_SPEC = {
    "SHIBUYA_STATION": {0: ("ballast", False), 1: ("rail", False), 2: ("platform", False),
                        3: ("canopy", False), 4: ("column", True)},
    "SHIBUYA_STATION_HALL": {0: ("shell", False), 1: ("rib/column", True),
                             2: ("glass", False), 3: ("concrete", False)},
    "SHIBUYA_VIADUCT": {0: ("deck", False), 1: ("barrier", False), 2: ("pier", True)},
    "SHIBUYA_SIDEWALK": {},
}


def _tris(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def _is_instance(o):
    """True for a genuine linked duplicate (mesh data shared with a master).

    Checks [C] and [E] are only meaningful for those. Both read `o.location` as the
    placement point, which is right for an instance whose mesh sits at the local origin
    and wrong for a baked single mesh with the offset welded into its vertices - such an
    object has location (0,0,0), so on the first run SHIBUYA_CABLES reported "15.21 m
    below the ground at (0,0)" and all 18 unique landmark meshes collapsed into one cell
    and reported a 72% overlap rate. Both were criterion defects, not map defects."""
    return o.data.users > 1


# ----------------------------------------------------------------- instance collections
def audit_instances(name, bvh_bld, ground, spec):
    col = bpy.data.collections.get(name)
    if col is None:
        return None
    objs = [o for o in col.objects if o.type == 'MESH' and o.data.vertices]
    N = len(objs)
    if not N:
        return dict(total=0)

    hz = {}
    for o in objs:
        if o.data.name not in hz:
            hz[o.data.name] = max(v.co.z for v in o.data.vertices)

    far = []
    above = []
    gdev = []
    encl = []
    singles = [o.name for o in objs if not _is_instance(o)]

    for o in objs:
        p = o.location
        if spec["mode"] == "wall":
            # [A] distance to the real building SURFACE. Measuring to the AABB instead
            # hid 1,065 modules up to 26.9 m above their own roof.
            base = o.data.name.split('.')[0]
            lift = 0.05 if base in ON_SURFACE else 1.2
            loc, nor, idx, d = bvh_bld.find_nearest(Vector((p.x, p.y, p.z + lift)), 6.0)
            dd = 99.0 if loc is None else d
            if dd > 1.0:
                far.append((round(dd, 2), base, round(p.x, 1), round(p.y, 1), round(p.z, 1)))
            # [B] roof compared along the INWARD wall direction. The placer sets yaw so
            # local +Y is the outward normal, hence inward = (sin yaw, -cos yaw).
            th = o.rotation_euler.z
            roof = SPL.roof_max(bvh_bld, p.x, p.y, math.sin(th), -math.cos(th))
            if roof is not None and p.z + hz[o.data.name] > roof + ABOVE_TOL:
                above.append((round(p.z + hz[o.data.name] - roof, 1), base,
                              round(p.x, 1), round(p.y, 1)))
        elif spec["gtol"] is not None and _is_instance(o):
            # [E] does it actually sit on the ground?
            g = ground.z(p.x, p.y)
            if g is None:
                gdev.append((99.0, o.data.name.split('.')[0], round(p.x, 1), round(p.y, 1)))
            elif abs(p.z - g) > spec["gtol"]:
                gdev.append((round(p.z - g, 2), o.data.name.split('.')[0],
                             round(p.x, 1), round(p.y, 1)))
        # [F] really walled in - parity AND no horizontal escape (parity alone
        # overcounts 5.7x: 17% vs a measured 3.0%)
        if SPL.enclosed(bvh_bld, p.x, p.y, p.z + 1.2):
            encl.append((o.data.name.split('.')[0], round(p.x, 1), round(p.y, 1),
                         round(p.z, 1)))

    # [C] unintended overlap in one cell, keyed by FAMILY not module name (keying on the
    # name let two signboard variants share a cell - 7,339 surplus instances)
    q = 1.0 / spec["quant"]
    cell = collections.defaultdict(set)
    for o in objs:
        if not _is_instance(o):
            continue
        p = o.location
        cell[(round(p.x*q)/q, round(p.y*q)/q, round(p.z*q)/q)].add(
            SPL.family(o.data.name.split('.')[0]))
    bad = 0
    kinds = collections.Counter()
    for k, fams in cell.items():
        if len(fams) < 2 or frozenset(fams) in INTENDED:
            continue
        bad += len(fams) - 1
        kinds[tuple(sorted(fams))] += 1

    # [D] centre inside a roadway/intersection polygon
    on_road = None
    tp = os.path.join(SHIB, "tran", "tran_local.json")
    if spec["mode"] == "wall" and os.path.exists(tp):
        T = json.load(open(tp, encoding="utf-8"))
        road = [[(q2[0], q2[1]) for q2 in pp["pts"]] for pp in T["polys"]
                if pp["kind"] == "TA" and pp["fn"] in ("1000", "1020")
                and not pp.get("elevated")]
        on_road = 0
        for o in objs:
            p = o.location
            if any(SPL.inside(r, p.x, p.y) for r in road):
                on_road += 1

    return dict(total=N, far=far, above=above, gdev=gdev, enclosed=encl,
                overlap=bad, overlap_kinds=kinds, on_road=on_road, mode=spec["mode"],
                singles=singles)


# ------------------------------------------------------------------ single-mesh builders
def audit_meshes(bvh_objs):
    out = {}
    for name, matmap in MESH_SPEC.items():
        ob = bpy.data.objects.get(name)
        if ob is None or not ob.data.polygons:
            continue
        r = SPL.overlap_tris([ob], bvh_objs)
        rows = []
        hard_hit = 0
        hard_tot = 0
        for mi in sorted(r["tot_per_mat"]):
            nm, excused = matmap.get(mi, ("mat%d" % mi, False))
            h = r["per_mat"].get(mi, 0)
            t = r["tot_per_mat"][mi]
            rows.append((mi, nm, excused, h, t))
            if not excused:
                hard_hit += h
                hard_tot += t
        out[name] = dict(total=r["total"], hit=r["hit"], rows=rows,
                         hard_hit=hard_hit, hard_tot=hard_tot)
    return out


# ----------------------------------------------------------------------------- budget
def audit_budget():
    rows = []
    masters = collections.defaultdict(lambda: [0, 0, 0])   # mesh -> [inst, tris, verts]
    for c in bpy.data.collections:
        if not c.name.startswith("MAP_SHIBUYA"):
            continue
        n = 0
        shown = 0
        uniq = set()
        for o in c.objects:
            # "displayed" means what renders: MAP_SHIBUYA_LM_ORIG holds the superseded
            # PLATEAU boxes with hide_render set, and counting them inflates the budget.
            if o.type != 'MESH' or not o.data.polygons or o.hide_render:
                continue
            t = _tris(o.data)
            n += 1
            shown += t
            uniq.add(o.data.name)
            m = masters[o.data.name]
            m[0] += 1
            m[1] = t
            m[2] = len(o.data.vertices)
        if n:
            rows.append((c.name, n, len(uniq), shown))
    rows.sort(key=lambda r: -r[3])
    total = sum(r[3] for r in rows)
    over30k = [(k, v) for k, v in masters.items() if v[1] > 30000]
    heavy = sorted(((v[0]*v[1], k, v[0], v[1], v[2]) for k, v in masters.items()),
                   reverse=True)[:12]
    return dict(rows=rows, total=total, over30k=over30k, heavy=heavy,
                n_masters=len(masters))


# ---------------------------------------------------------------------------- textures
def _png_size(path):
    with open(path, "rb") as f:
        head = f.read(26)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def _jpg_size(path):
    with open(path, "rb") as f:
        if f.read(2) != b"\xff\xd8":
            return None
        while True:
            b = f.read(1)
            while b and b != b"\xff":
                b = f.read(1)
            m = f.read(1)
            while m == b"\xff":
                m = f.read(1)
            if not m:
                return None
            if m[0] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                f.read(3)
                h, w = struct.unpack(">HH", f.read(4))
                return w, h
            ln = struct.unpack(">H", f.read(2))[0]
            f.seek(ln - 2, 1)


def audit_textures(maxpx=512, maxmb=15.0, root_dir=None):
    """Texture compliance.

    `root_dir` defaults to 03_Textures, which is the AUTHORING source - and measuring the
    512 rule against it is the wrong test. OVERDARE's 512 guidance applies to what ships,
    and shibuya_export_v2.prep_image already writes EX_*.png at <=512 for delivery (with
    ZK_SignAtlas / ZK_ShopAtlas held at 1024 by KEEP_1024, because 64 sign cells at 512
    leaves each one 128x32 px and the Japanese text turns to mush).

    So the source figure is INFORMATIONAL and the delivered figure is the gate. Pass the
    export texture folder as root_dir to test the real thing."""
    TEX_ROOT = root_dir or TEXD
    if not os.path.isdir(TEX_ROOT):
        return None
    files = []
    for root, _, names in os.walk(TEX_ROOT):
        for n in names:
            if not n.lower().endswith((".png", ".jpg", ".jpeg")):
                continue
            p = os.path.join(root, n)
            sz = _png_size(p) if n.lower().endswith(".png") else _jpg_size(p)
            files.append(dict(path=os.path.relpath(p, TEX_ROOT),
                              px=(max(sz) if sz else -1),
                              mb=os.path.getsize(p)/1048576.0,
                              md5=hashlib.md5(open(p, "rb").read()).hexdigest()))
    dup = collections.defaultdict(list)
    for f in files:
        dup[f["md5"]].append(f["path"])
    return dict(n=len(files),
                over_px=sorted([f for f in files if f["px"] > maxpx],
                               key=lambda f: -f["px"]),
                over_mb=[f for f in files if f["mb"] > maxmb],
                dupes=[v for v in dup.values() if len(v) > 1])


# -------------------------------------------------------------------------------- main
def audit_map(json_out=None, skip=()):
    bld = SPL.buildings()
    bvh_bld, ntri = SPL.make_bvh(bld)
    ground = SPL.GroundSampler()
    print("=== AUDIT  scene=%s" % os.path.basename(bpy.data.filepath or "(unsaved)"))
    print("    building BVH: %d objects / %s tris\n" % (len(bld), format(ntri, ',')))

    res = {"instances": {}, "meshes": {}, "budget": None, "textures": None}

    print("--- [1] instance collections " + "-"*52)
    hdr = ("%-24s %7s %8s %8s %8s %8s %8s"
           % ("collection", "count", "[A]far", "[B]roof", "[C]ovlp", "[E]gnd", "[F]encl"))
    print(hdr)
    for name, spec in INSTANCE_SPEC.items():
        if name in skip:
            continue
        r = audit_instances(name, bvh_bld, ground, spec)
        if r is None or not r["total"]:
            continue
        res["instances"][name] = dict(
            total=r["total"], far=len(r["far"]), above=len(r["above"]),
            overlap=r["overlap"], gdev=len(r["gdev"]), enclosed=len(r["enclosed"]),
            on_road=r["on_road"], singles=r["singles"])
        def pc(v):
            return "-" if v is None else "%d(%.2f%%)" % (v, 100.0*v/r["total"])
        print("%-24s %7d %8s %8s %8s %8s %8s"
              % (name, r["total"],
                 pc(len(r["far"])) if r["mode"] == "wall" else "-",
                 pc(len(r["above"])) if r["mode"] == "wall" else "-",
                 pc(r["overlap"]),
                 pc(len(r["gdev"])) if spec["gtol"] is not None else "-",
                 pc(len(r["enclosed"]))))
        for lab, rowsrc, fmt in (("[A]", r["far"], "d=%-6s %-24s (%7s, %7s, %6s)"),
                                 ("[B]", r["above"], "+%-5s %-24s (%7s, %7s)"),
                                 ("[E]", r["gdev"], "dz=%-6s %-24s (%7s, %7s)")):
            for row in sorted(rowsrc, key=lambda t: -abs(t[0]))[:4]:
                print("      %s %s" % (lab, fmt % row))
        for k, c in r["overlap_kinds"].most_common(3):
            print("      [C] x%-5d %s" % (c, ", ".join(map(str, k))))
        for row in r["enclosed"][:4]:
            print("      [F] %-24s (%7s, %7s, %6s)" % row)
        if r["singles"]:
            print("      -- %d baked single-mesh object(s) exempt from [C]/[E]: %s"
                  % (len(r["singles"]), ", ".join(r["singles"][:4])))
    ground.report("audit")

    print("\n--- [2] single-mesh builders vs buildings (exact BVH.overlap) " + "-"*17)
    res["meshes"] = mres = audit_meshes(bld)
    print("%-24s %9s %9s %9s   %s"
          % ("object", "tris", "hit", "hit%", "hard-fail (supports excused)"))
    for name, m in mres.items():
        print("%-24s %9s %9s %8.1f%%   %d/%d = %.1f%%"
              % (name, format(m["total"], ','), format(m["hit"], ','),
                 100.0*m["hit"]/max(1, m["total"]),
                 m["hard_hit"], m["hard_tot"],
                 100.0*m["hard_hit"]/max(1, m["hard_tot"])))
        for mi, nm, exc, h, t in m["rows"]:
            print("      mi=%d %-12s %-8s %6d / %6d = %5.1f%%"
                  % (mi, nm, "EXCUSED" if exc else "", h, t, 100.0*h/max(1, t)))

    print("\n--- [3] triangle budget " + "-"*55)
    res["budget"] = b = audit_budget()
    print("%-26s %8s %7s %12s %7s" % ("collection", "objects", "meshes", "tris", "share"))
    for nm, n, u, t in b["rows"]:
        print("%-26s %8d %7d %12s %6.1f%%"
              % (nm, n, u, format(t, ','), 100.0*t/max(1, b["total"])))
    print("%-26s %8s %7d %12s" % ("TOTAL", "", b["n_masters"], format(b["total"], ',')))
    print("    masters over the 30,000 tri/mesh cap: %d" % len(b["over30k"]))
    for k, v in b["over30k"]:
        print("      %-30s %s tris x %d instances" % (k, format(v[1], ','), v[0]))
    print("    heaviest on screen (instances x tris):")
    for tot, k, ni, t, nv in b["heavy"]:
        print("      %-30s %4d x %7s = %10s   (%s verts/mesh)"
              % (k, ni, format(t, ','), format(tot, ','), format(nv, ',')))

    print("\n--- [4] textures " + "-"*62)
    res["textures"] = tx = audit_textures()
    if tx:
        print("    AUTHORING SOURCE 03_Textures (informational, not the gate):")
        print("      %d files | over 512 px: %d | over 15 MB: %d | md5-identical groups: %d"
              % (tx["n"], len(tx["over_px"]), len(tx["over_mb"]), len(tx["dupes"])))
        for f in tx["over_px"][:4]:
            print("        %5d px  %6.2f MB  %s" % (f["px"], f["mb"], f["path"]))
        for g in tx["dupes"]:
            print("        DUPE  %s" % " == ".join(g))
    # the gate: what actually ships
    for cand in (os.path.join(r"C:\Work\MeshTest", d)
                 for d in ("_texwork_v6", "_texwork_v5")):
        if os.path.isdir(cand):
            dl = audit_textures(root_dir=cand)
            res["textures_delivered"] = dl
            print("    DELIVERED %s (the gate):" % os.path.basename(cand))
            print("      %d files | over 512 px: %d | over 15 MB: %d"
                  % (dl["n"], len(dl["over_px"]), len(dl["over_mb"])))
            for f in dl["over_px"][:4]:
                print("        %5d px  %6.2f MB  %s  %s"
                      % (f["px"], f["mb"], f["path"],
                         "(KEEP_1024 by design)" if "Atlas" in f["path"] else "<-- CHECK"))
            break
    else:
        print("    DELIVERED: no export texture folder yet - run S7 first")

    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, default=str)
        print("\n    wrote %s" % json_out)
    print("\nAUDIT DONE")
    return res
