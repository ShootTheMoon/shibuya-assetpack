"""Place Phase 1a assets into the Shibuya map.
Reads the existing geodata (PLATEAU sidewalk polys + OSM POIs) and instances the
pack assets as LINKED DUPLICATES so mesh data is shared.
exec() this inside shibuya_detail_v005.blend."""
import bpy, bmesh, os, sys, json, math, random
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)             # every script here is exec()'d, so __file__ may not exist
import shibuya_placement_lib as SPL   # NOT `as L`: `L` is a local segment length below

SHIB = r"C:\Work\blender\Shibuya"
PACK = r"C:\Work\blender\ShibuyaAssetPack\00_Source_Blender"
ASSETS = {
    "UP_UtilityPole_A":       os.path.join(PACK, "UP_Utility_Overhead", "UP_UtilityPole_A.blend"),
    "SF_VendingMachine_A":    os.path.join(PACK, "SF_Street_Furniture", "SF_VendingMachine_A.blend"),
    "SF_TrafficSignal_A":     os.path.join(PACK, "SF_Street_Furniture", "SF_TrafficSignal_A.blend"),
    "GR_TactilePaving_Dot_A": os.path.join(PACK, "GR_Ground_Detail", "GR_TactilePaving.blend"),
    "GR_TactilePaving_Bar_A": os.path.join(PACK, "GR_Ground_Detail", "GR_TactilePaving.blend"),
}

def col(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name); bpy.context.scene.collection.children.link(c)
    return c

def append_masters():
    masters = {}
    for name, path in ASSETS.items():
        if name in bpy.data.objects:
            masters[name] = bpy.data.objects[name]; continue
        with bpy.data.libraries.load(path, link=False) as (df, dt):
            dt.objects = [n for n in df.objects if n == name]
        o = bpy.data.objects.get(name)
        if o is None:
            print("  !! append failed:", name); continue
        if not o.users_collection:
            bpy.context.scene.collection.objects.link(o)
        o.hide_render = True; o.hide_viewport = True      # master stays hidden
        masters[name] = o
    return masters

def instance(master, name, loc, rz, target_col, scale=1.0):
    o = master.copy(); o.data = master.data          # linked duplicate
    o.name = name
    o.hide_render = False; o.hide_viewport = False
    o.location = loc; o.rotation_euler = (0, 0, rz)
    if scale != 1.0: o.scale = (scale, scale, scale)
    target_col.objects.link(o)
    return o

# ---------------- main ----------------
def run():
    rnd = random.Random(20260728)
    T = json.load(open(os.path.join(SHIB, "tran", "tran_local.json"), encoding="utf-8"))
    P = json.load(open(os.path.join(SHIB, "osm", "poi_local.json"), encoding="utf-8"))
    OSM = json.load(open(os.path.join(SHIB, "osm", "shibuya_overpass.json"), encoding="utf-8"))
    # the old sampler returned a flat 15.0 on a ray miss, which is why props showed up
    # hanging in the air out in the undulating outskirts. Now a miss skips the instance
    # and gets counted.
    G = SPL.GroundSampler()
    gz = G.z
    M = append_masters()
    print("masters:", sorted(M.keys()))

    C_UTIL = col("MAP_SHIBUYA_UTILITY"); C_SF = col("MAP_SHIBUYA_STREETFURN")
    C_GR   = col("MAP_SHIBUYA_TACTILE")
    for c in (C_UTIL, C_SF, C_GR):
        for o in list(c.objects): bpy.data.objects.remove(o, do_unlink=True)

    # (removed) `xings` - crossing centroids were computed here and never read anywhere in
    # this file. They were also accumulated in lon/lat DEGREES, not the local metre frame
    # that every other coordinate in this script uses, so the "avoid planting poles in a
    # crossing mouth" rejection they were meant to drive could never have worked without a
    # projection step. Deleting the block also drops one full pass over OSM["elements"].

    # ---- 1) utility poles along sidewalk ring perimeters, every 30 m ----
    occ = SPL.Occupancy(14.0)
    poles = []
    for p in T["polys"]:
        if p["kind"] != "TA" or p["fn"] != "2000" or p.get("elevated"): continue
        ring = [(q[0], q[1]) for q in p["pts"]]
        if len(ring) < 3: continue
        cx = sum(a for a, _ in ring)/len(ring); cy = sum(b for _, b in ring)/len(ring)
        closed = ring + [ring[0]]; acc = 0.0
        for a, b in zip(closed, closed[1:]):
            seg = math.hypot(b[0]-a[0], b[1]-a[1])
            if seg < 1e-6: continue
            t = 30.0 - acc
            while t < seg:
                x = a[0] + (b[0]-a[0])*(t/seg); y = a[1] + (b[1]-a[1])*(t/seg)
                dx, dy = cx-x, cy-y; L = math.hypot(dx, dy) or 1.0
                x += dx/L*0.7; y += dy/L*0.7          # nudge onto the sidewalk
                if abs(x) <= 315 and abs(y) <= 315 and occ.try_mark(x, y):
                    poles.append((x, y))
                t += 30.0
            acc = (acc + seg) % 30.0
    npole = 0
    for i, (x, y) in enumerate(poles):
        z = gz(x, y)
        if z is None: continue
        instance(M["UP_UtilityPole_A"], "POLE_%03d" % i, (x, y, z),
                 rnd.uniform(0, 6.283), C_UTIL)
        npole += 1
    print("utility poles:", npole, "of", len(poles), "candidates")

    # ---- 2) cables: connect each pole to its 1-2 nearest neighbours < 45 m ----
    M_WIRE = bpy.data.materials.get("M_UP_Wire")
    if M_WIRE is None:
        M_WIRE = bpy.data.materials.new("M_UP_Wire"); M_WIRE.use_nodes = True
        b = M_WIRE.node_tree.nodes.get("Principled BSDF")
        b.inputs["Base Color"].default_value = (0.045, 0.045, 0.05, 1)
        b.inputs["Roughness"].default_value = 0.62
    bm = bmesh.new()
    # 3-sided, 5-sample tubes. At 4 sides x 11 samples this one mesh was 75,600 tris -
    # over OVERDARE's 30,000-per-mesh cap - for cable 8-12 m overhead at a 0.016 m radius,
    # where neither the cross-section nor the tessellation of the sag is resolvable. The
    # sag is a parabola, and 5 samples carry a parabola. Now 315 x 3 x 4 x 3 x 2 = 22,680.
    def tube(pts, r, sides=3):
        rings = []
        for i, pt in enumerate(pts):
            a = Vector(pts[max(i-1, 0)]); b2 = Vector(pts[min(i+1, len(pts)-1)])
            d = (b2 - a)
            if d.length < 1e-9: d = Vector((1, 0, 0))
            d.normalize()
            side = d.cross(Vector((0, 0, 1)))
            if side.length < 1e-9: side = Vector((0, 1, 0))
            side.normalize(); nrm = side.cross(d); nrm.normalize()
            ring = []
            for k in range(sides):
                a2 = 2*math.pi*k/sides
                ring.append(bm.verts.new(Vector(pt) + side*(math.cos(a2)*r) + nrm*(math.sin(a2)*r)))
            rings.append(ring)
        bm.verts.ensure_lookup_table()
        for i in range(len(rings)-1):
            for k in range(sides):
                k2 = (k+1) % sides
                try: bm.faces.new([rings[i][k], rings[i][k2], rings[i+1][k2], rings[i+1][k]])
                except ValueError: pass

    done = set(); nspan = 0
    for i, (x1, y1) in enumerate(poles):
        d = sorted(((math.hypot(x2-x1, y2-y1), j) for j, (x2, y2) in enumerate(poles) if j != i))
        for dist, j in d[:2]:
            if dist > 45.0: continue
            key = (min(i, j), max(i, j))
            if key in done: continue
            done.add(key)
            x2, y2 = poles[j]; z1 = gz(x1, y1); z2 = gz(x2, y2)
            if z1 is None or z2 is None: continue
            for (hz, sag, rr) in ((11.85, 0.55, 0.016), (10.15, 0.62, 0.016), (8.95, 0.95, 0.026)):
                pts = []
                for s in range(5):
                    t = s/4.0
                    pts.append((x1 + (x2-x1)*t, y1 + (y2-y1)*t,
                                (z1 + (z2-z1)*t) + hz - sag*4*t*(1-t)))
                tube(pts, rr)
            nspan += 1
    # The object is deleted with the collection above, but its MESH datablock survives, so
    # meshes.new() kept handing back SHIBUYA_CABLES.001, .002, ... and every earlier 75,600
    # tri mesh stayed in the file as an orphan. Drop the old datablock first.
    _old_me = bpy.data.meshes.get("SHIBUYA_CABLES")
    if _old_me is not None and _old_me.users == 0:
        bpy.data.meshes.remove(_old_me)
    me = bpy.data.meshes.new("SHIBUYA_CABLES"); bm.to_mesh(me); bm.free()
    me.materials.append(M_WIRE)
    cab = bpy.data.objects.new("SHIBUYA_CABLES", me); C_UTIL.objects.link(cab)
    print("cable spans:", nspan, "| cable tris:", sum(len(p.vertices)-2 for p in me.polygons))

    # ---- 3) traffic signals at the 43 OSM nodes (replace the 32-vert procedural ones) ----
    old = [o for o in bpy.data.objects if o.name.startswith("SIGNAL_")]
    for o in old: bpy.data.objects.remove(o, do_unlink=True)
    # OSM tags each APPROACH of a junction as its own traffic_signals node, so one
    # four-way crossing can carry 2-4 nodes a few metres apart. Measured on the real
    # poi_local.json: of the 42 nodes inside the crop the closest pair is 6.77 m, 4 nodes
    # have a neighbour under 8 m, 8 have one under 10 m, and the median nearest-neighbour
    # distance is 25.3 m. 8.0 drops the 2 tightest duplicates (42 -> 40). Radius 10.0 would
    # give 38, but 8-10 m is also the spacing of two heads on OPPOSITE corners of one real
    # Shibuya junction, so 10.0 starts deleting signals that should be there.
    sigocc = SPL.Occupancy(8.0)
    n = 0
    for i, (x, y) in enumerate(P["signals"]):
        if abs(x) > 315 or abs(y) > 315: continue
        z = gz(x, y)
        # ground probe FIRST so a probe miss cannot consume an occupancy slot - same
        # ordering as the vending pass below.
        if z is None or not sigocc.try_mark(x, y): continue
        instance(M["SF_TrafficSignal_A"], "SIG_%03d" % i, (x, y, z),
                 rnd.uniform(0, 6.283), C_SF); n += 1
    print("traffic signals:", n, "(old procedural removed:", len(old), ")")

    # ---- 4) vending machines at shop/food POIs, snapped to the nearest building wall ----
    bl = [o for o in bpy.data.objects if o.type == 'MESH' and
          (o.name.startswith("SHIBUYA_BLDG__") or o.name.startswith("LM_"))]
    V = []; F = []
    for o in bl:
        mw = o.matrix_world; b = len(V)
        V.extend([mw @ v.co for v in o.data.vertices])
        F.extend([[k+b for k in p.vertices] for p in o.data.polygons])
    bbvh = BVHTree.FromPolygons(V, F)
    occ2 = SPL.Occupancy(5.0, cell=6.0)
    nv = 0
    cand = [p for p in P["poi"] if p["k"] in ("shop", "fast_food", "cafe") and abs(p["x"]) <= 300 and abs(p["y"]) <= 300]
    for i, p in enumerate(cand):
        if nv >= 90: break
        x, y = p["x"], p["y"]
        z = gz(x, y)
        if z is None: continue
        hit = bbvh.find_nearest(Vector((x, y, z+1.0)), 14.0)
        if hit is None or hit[0] is None: continue
        loc, nrm, _, dist = hit
        nn = Vector(nrm); nn.z = 0
        if nn.length < 1e-4: continue
        nn.normalize()
        px, py = loc.x + nn.x*0.42, loc.y + nn.y*0.42
        pz = gz(px, py)
        if pz is None or not occ2.try_mark(px, py): continue
        yaw = math.atan2(nn.y, nn.x) - math.pi/2
        instance(M["SF_VendingMachine_A"], "VEND_%03d" % i, (px, py, pz), yaw, C_SF)
        nv += 1
    print("vending machines:", nv)

    # ---- 5) tactile paving along the inner edge of the sidewalk rings near the Scramble ----
    # (removed) a SECOND dead loop lived here: it walked every OSM crossing way, built an
    # empty `pts` list and `pass`ed. Same lon/lat-vs-local-metres problem as `xings`, and
    # the crossings are already in the baked ground texture. Only the sidewalk-ring strip
    # below ever placed anything.
    nt = 0
    # place a warning-block strip along the inner edge of the 6 sidewalk rings closest to origin
    rings = [p for p in T["polys"] if p["kind"] == "TA" and p["fn"] == "2000" and not p.get("elevated")]
    def ring_d(p):
        cx = sum(q[0] for q in p["pts"])/len(p["pts"]); cy = sum(q[1] for q in p["pts"])/len(p["pts"])
        return math.hypot(cx, cy)
    rings.sort(key=ring_d)
    # 0.22, NOT the 0.28 the plan asked for - measured against these exact 6 rings.
    # The 0.45 m nudge below is RADIAL toward each ring's own centroid, so it contracts the
    # along-edge pitch by about (R-0.45)/R where R is the distance to that centroid. The
    # realised in-line pitch is therefore not a clean 0.30: median 0.2908, p5 0.2726,
    # p1 0.2436, min 0.1672. Occupancy(0.28) deletes 88 tiles of which at most 7 are
    # genuine stacks - the other ~81 are punched out of the MIDDLE of intended runs and
    # leave 0.58 m holes in a continuous tactile strip. Occupancy(0.30) deletes exactly 50%
    # (every other tile), which is the clearest proof the operating pitch sits just under
    # 0.30. Real stacking is tiny: counting only neighbours that are NOT the previous tile
    # of the same run, 2 pairs are under 0.20 m and 7 under 0.28 m.
    # 0.22 sits below the 1st-percentile in-line pitch so it cannot thin a normal run,
    # while a 0.30 m tile at 0.22 m spacing is a 27% overlap - real z-fight material.
    # Measured keeps: 0.20 -> 1303, 0.22 -> 1299, 0.25 -> 1291, 0.28 -> 1217, 0.30 -> 653.
    tacocc = SPL.Occupancy(0.22)
    for p in rings[:6]:
        ring = [(q[0], q[1]) for q in p["pts"]]
        closed = ring + [ring[0]]; acc = 0.0
        cx = sum(a for a, _ in ring)/len(ring); cy = sum(b for _, b in ring)/len(ring)
        for a, b in zip(closed, closed[1:]):
            seg = math.hypot(b[0]-a[0], b[1]-a[1])
            if seg < 1e-6: continue
            ang = math.atan2(b[1]-a[1], b[0]-a[0])
            t2 = 0.30 - acc
            while t2 < seg:
                x = a[0] + (b[0]-a[0])*(t2/seg); y = a[1] + (b[1]-a[1])*(t2/seg)
                dx, dy = cx-x, cy-y; L = math.hypot(dx, dy) or 1.0
                x += dx/L*0.45; y += dy/L*0.45
                if abs(x) <= 120 and abs(y) <= 120:
                    tz = gz(x, y)
                    if tz is not None and tacocc.try_mark(x, y):
                        instance(M["GR_TactilePaving_Bar_A"], "TAC_%04d" % nt,
                                 (x, y, tz+0.01), ang, C_GR)
                        nt += 1
                t2 += 0.30
            acc = (acc + seg) % 0.30
    print("tactile tiles:", nt)
    G.report("phase1a")

    tot = sum(len(o.data.vertices) for o in bpy.data.objects if o.type == 'MESH')
    print("\nscene verts now:", tot, "| objects:", len(bpy.data.objects))
