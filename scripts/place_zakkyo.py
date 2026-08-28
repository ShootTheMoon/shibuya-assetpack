"""Instance the zakkyo facade kit onto buildings fronting the Scramble / Center Gai.
Street-facing footprint edges -> 3.0 m bays -> per-bay ground unit + per-floor sign rail
+ signboard stacks, roof water tank / AC / parapet. Linked duplicates only."""
import bpy, os, sys, json, math, random
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)             # every script here is exec()'d, so __file__ may not exist
import shibuya_placement_lib as SPL   # NOT `as L`: `L` is a local edge length below

SHIB = r"C:\Work\blender\Shibuya"
KIT  = r"C:\Work\blender\ShibuyaAssetPack\00_Source_Blender\ZK_Zakkyo_Facade_Kit\ZK_FacadeKit.blend"
BAY, FLOOR = 3.0, 3.4
MODH = 3.2          # tallest wall module: the signboard stack tops out at 3.13 m
# 40 meshes. 24 of them carried ~5,000 placed stacks, so one silhouette repeated ~208
# times; s5_expand_kit.py added 16 more that between them reach all 64 atlas cells (the
# original 24 reached 53). Adding variants does NOT add instances - the placer puts a stack
# on 62% of upper floors either way - so this is variety at zero screen cost.
SIGNS   = ["ZK_SignboardStack_%02d" % i for i in range(40)]
SHOPS   = ["ZK_ShopFront_%d" % i for i in range(8)]           # lit ground-floor storefronts
MODULES = ["ZK_Storefront_Module_A","ZK_RollerShutter_Module_A","ZK_Window_Module_A",
           "ZK_SignRail_Module_A","ZK_Parapet_Module_A","ZK_Drainpipe_Module_A",
           "ZK_ACUnit_A","ZK_WaterTank_A","ZK_ExternalStair_A"] + SIGNS + SHOPS

def load_kit():
    have = [n for n in MODULES if n in bpy.data.objects]
    if len(have) < len(MODULES):
        with bpy.data.libraries.load(KIT, link=False) as (df, dt):
            dt.objects = [n for n in df.objects if n in MODULES]
    M = {}
    for n in MODULES:
        o = bpy.data.objects.get(n)
        if o is None: continue
        if not o.users_collection: bpy.context.scene.collection.objects.link(o)
        o.hide_render = True; o.hide_viewport = True
        M[n] = o
    return M

def footprint_edges(ob):
    """bottom-ring edges of the building, as ((x1,y1),(x2,y2)) in world space"""
    me = ob.data
    zs = [v.co.z for v in me.vertices]
    if not zs: return []
    zmin = min(zs); band = zmin + 0.6
    edges = []
    for e in me.edges:
        a = me.vertices[e.vertices[0]].co; b = me.vertices[e.vertices[1]].co
        if a.z < band and b.z < band and (a - b).length > 1.2:
            edges.append(((a.x, a.y), (b.x, b.y)))
    return edges

def run(limit=130, radius=210.0):
    rnd = random.Random(4242)
    T = json.load(open(os.path.join(SHIB, "tran", "tran_local.json"), encoding="utf-8"))
    P = json.load(open(os.path.join(SHIB, "osm", "poi_local.json"), encoding="utf-8"))
    M = load_kit()
    print("kit modules:", len(M))

    walks = []
    for p in T["polys"]:
        if p["kind"] == "TA" and p["fn"] == "2000" and not p.get("elevated"):
            pts = [(q[0], q[1]) for q in p["pts"]]
            cx = sum(a for a, _ in pts)/len(pts); cy = sum(b for _, b in pts)/len(pts)
            r = max(math.hypot(a-cx, b-cy) for a, b in pts)
            walks.append((cx, cy, r))
    def near_walk(x, y, tol=7.0):
        for cx, cy, r in walks:
            if math.hypot(x-cx, y-cy) < r + tol: return True
        return False

    pois = [q for q in P["poi"]]
    def poi_kind(cx, cy):
        best = None; bd = 1e18
        for q in pois:
            d = (q["x"]-cx)**2 + (q["y"]-cy)**2
            if d < bd: bd = d; best = q
        return (best["k"] if (best and bd < 400) else None)

    # A footprint edge is NOT proof of a wall. PLATEAU LOD2 carries decks, canopies and
    # overhangs near the ground, and adjacent buildings each own the shared party wall, so
    # edge-following alone put 2,701 modules in open space (up to 29.6 m from any building)
    # and stacked 1,137 exact duplicates. Both are now checked against the real geometry.
    # make_bvh / roof_at / roof_min / family / wall_at now live in shibuya_placement_lib -
    # they were duplicated (with drifting behaviour) across five scripts.
    bvh_bld, ntri = SPL.make_bvh(SPL.buildings())
    print("wall BVH: %d tris" % ntri)
    # A SECOND soup, without the retired originals, used ONLY for the "is anything above
    # this roof?" test. include_retired=True (the default, and what bvh_bld needs so that
    # wall_at keeps its current behaviour) leaves the superseded PLATEAU boxes of 109,
    # Hachiko and Scramble Square in the soup - see the SPL.buildings docstring. Those sit
    # at the SAME coordinates as their hand-modelled replacements with a different roof
    # height, so `top > r + 0.5` would fire on every rooftop candidate of exactly the three
    # buildings the shot cares most about and silently strip their props.
    bvh_top, _ = SPL.make_bvh(SPL.buildings(include_retired=False))
    # Nothing in this script ever looked at SHIBUYA_GROUND: the ground floor was seated at
    # the SHELL's zmin, so wherever the PLATEAU shell base sits below the draped terrain the
    # whole shopfront is buried. Probe the terrain per bay instead. A miss returns None and
    # the bay is SKIPPED - never 0.0, never 15.0 (see the GroundSampler docstring).
    gs = SPL.GroundSampler()

    seen = set()

    col = bpy.data.collections.get("MAP_SHIBUYA_ZAKKYO")
    if col is None:
        col = bpy.data.collections.new("MAP_SHIBUYA_ZAKKYO"); bpy.context.scene.collection.children.link(col)
    for o in list(col.objects): bpy.data.objects.remove(o, do_unlink=True)

    bl = SPL.buildings(require_faces=False)
    def dist0(o):
        vs = o.data.vertices
        if not vs: return 1e9
        cx = sum(v.co.x for v in vs)/len(vs); cy = sum(v.co.y for v in vs)/len(vs)
        return math.hypot(cx, cy)
    bl = [o for o in bl if dist0(o) < radius]
    bl.sort(key=dist0)
    bl = bl[:limit]
    print("target buildings:", len(bl))

    n_inst = 0; n_bldg = 0; n_dup = 0; n_air = 0
    n_gmiss = 0; n_low = 0; n_lift = 0; n_roof_rej = 0; n_roof_gmiss = 0; lift_max = 0.0
    # NB `rz` below is the YAW, not a roof height - the roof height is passed as `roof`.
    def put(mod, loc, rz, sc=1.0, nrm=None, roof=None):
        nonlocal n_inst, n_dup, n_air
        m = M.get(mod)
        if m is None: return
        k = (SPL.family(mod), round(loc[0]*2)/2, round(loc[1]*2)/2, round(loc[2]*2)/2)
        if k in seen:
            n_dup += 1; return
        if nrm is not None:
            if not SPL.wall_at(bvh_bld, loc[0], loc[1], loc[2] + 1.2, nrm[0], nrm[1]):
                n_air += 1; return
        else:
            # `nrm is None` is EXACTLY the rooftop path, and it used to bypass every
            # surface test - a prop only had to be non-duplicate to get linked. Demand
            # proof instead: the caller hands over the OWNING building's BVH plus the roof
            # height it sampled, and this re-probes it. No normal and no roof = no proof.
            if roof is None:
                n_air += 1; return
            rbvh, rz_exp = roof
            rr = SPL.roof_at(rbvh, loc[0], loc[1])
            if rr is None or abs(rr - rz_exp) > 0.5 or abs(loc[2] - rr) > 0.5:
                n_air += 1; return
        seen.add(k)
        o = m.copy(); o.data = m.data
        o.name = "ZK_%05d" % n_inst
        o.hide_render = False; o.hide_viewport = False
        o.location = loc; o.rotation_euler = (0, 0, rz)
        if sc != 1.0: o.scale = (sc, sc, sc)
        col.objects.link(o); n_inst += 1

    for ob in bl:
        vs = ob.data.vertices
        if not vs: continue
        bvh_self, _ = SPL.make_bvh([ob])      # roof heights come from THIS building only
        zmin = min(v.co.z for v in vs); zmax = max(v.co.z for v in vs)
        H = zmax - zmin
        if H < 4.0: continue
        floors = max(1, min(9, int(H / FLOOR)))
        cx = sum(v.co.x for v in vs)/len(vs); cy = sum(v.co.y for v in vs)/len(vs)
        kind = poi_kind(cx, cy)
        used_any = False
        for (a, b) in footprint_edges(ob):
            mx, my = (a[0]+b[0])/2, (a[1]+b[1])/2
            if not near_walk(mx, my): continue
            dx, dy = b[0]-a[0], b[1]-a[1]
            L = math.hypot(dx, dy)
            if L < BAY*0.8: continue
            ux, uy = dx/L, dy/L
            nx, ny = -uy, ux                       # outward-ish normal
            if (nx*(mx-cx) + ny*(my-cy)) < 0: nx, ny = -nx, -ny
            yaw = math.atan2(ny, nx) - math.pi/2
            nb = max(1, int(L // BAY))
            for i in range(nb):
                t = (i + 0.5) * (L/nb)
                bx, by = a[0] + ux*t + nx*0.10, a[1] + uy*t + ny*0.10
                # floors must come from the roof height AT THIS BAY, not from the whole
                # object. A PLATEAU building often bundles a low annex with a tall main
                # block, so one global floor count pushed signs up to 26.9 m above the
                # annex roof - that is the "floating in the air" the eye was catching.
                rz = SPL.roof_min(bvh_self, bx, by, nx, ny)
                if rz is None: continue
                # ...and the BOTTOM has to come from the terrain, not from the shell. Seat
                # this bay at the higher of the shell base and the draped ground. A ground
                # miss is a SKIP, not a substituted height.
                gz = gs.z(bx, by)
                if gz is None:
                    n_gmiss += 1; continue
                z0 = max(zmin, gz)
                if z0 - zmin > 0.05:
                    n_lift += 1
                    if z0 - zmin > lift_max: lift_max = z0 - zmin
                if rz - z0 < 0.5:
                    n_low += 1; continue   # this bay's own roof is at or under the seat
                # Capping the floor COUNT was not enough: every z was still measured from
                # the object's global zmin, so on a building that bundles a low annex with
                # a tall block the parapet still landed 26.9 m above the annex roof.
                # Solve for the highest floor whose module TOP still fits under this bay's
                # own roof, and seat the parapet on that roof directly. z0, NOT zmin: the
                # whole stack rides the seat. Leave this on zmin and a bay lifted 2.0 m
                # puts floor 1 (zmin + 3.40) 1.4 m INSIDE the 3.2 m ground module.
                fmax = int((rz - z0 - MODH) / FLOOR) + 1
                floors_here = max(1, min(floors, fmax))
                # ground floor: a lit shopfront is what carries the street at night,
                # so it is the default; shutters are the exception, not the rule
                g = rnd.random()
                if kind in ("shop","restaurant","cafe","fast_food","bar","pub") or g < 0.72:
                    put("ZK_Storefront_Module_A", (bx, by, z0), yaw, nrm=(nx, ny))   # glazing + frame
                    put(rnd.choice(SHOPS), (bx, by, z0), yaw, nrm=(nx, ny))          # lit interior + noren
                elif g < 0.90:
                    put("ZK_RollerShutter_Module_A", (bx, by, z0), yaw, nrm=(nx, ny))
                else:
                    put("ZK_Storefront_Module_A", (bx, by, z0), yaw, nrm=(nx, ny))
                # upper floors: z0, not zmin - see the fmax comment. The stack has to start
                # where the ground module actually is or floor 1 lands inside it.
                for f in range(1, floors_here):
                    z = z0 + f*FLOOR
                    put("ZK_SignRail_Module_A", (bx, by, z), yaw, nrm=(nx, ny))
                    r = rnd.random()
                    if r < 0.62:
                        # random atlas variant + jitter: identical stacks on a grid read
                        # as an office block, not zakkyo
                        put(rnd.choice(SIGNS),
                            (bx + nx*0.14, by + ny*0.14, z + rnd.uniform(-0.14, 0.14)), yaw, nrm=(nx, ny))
                    elif r < 0.85:
                        put("ZK_Window_Module_A", (bx, by, z + 0.95), yaw, nrm=(nx, ny))
                if rnd.random() < 0.30:
                    # same seat as the bay it belongs to (the pipe is <=1.5 m along the
                    # edge, so re-probing the terrain there would only add jitter)
                    put("ZK_Drainpipe_Module_A", (bx + ux*BAY*0.5, by + uy*BAY*0.5, z0), yaw, nrm=(nx, ny))
                put("ZK_Parapet_Module_A", (bx, by, rz), yaw, nrm=(nx, ny))
                used_any = True
        if used_any:
            n_bldg += 1
            # roof kit
            # rooftop props were placed at the object's zmax with a +-4 m jitter and no
            # check, so they drifted off the roof and hung in mid-air at 64-125 m. Two bugs
            # survived that fix. The height came from bvh_bld, the COMBINED soup, so a
            # taller neighbour answered instead of this building - the failure roof_min's
            # docstring records at (264.4,-21.2), where every probe hits Hikarie at 199 m
            # over a 35 m roof. And the scatter centre was the VERTEX MEAN, which on an
            # L-shaped or podium+tower footprint is not over the building at all (and on a
            # podium+tower is dragged onto the podium by sheer vertex count).
            # Now: seed from the ROOF BAND, sample bvh_self, and prove the surface found is
            # THIS building's roof - nothing above it, flat for 0.7 m around.
            rvs = [v.co for v in vs if v.co.z > zmax - 0.5] or [v.co for v in vs]
            rcx = sum(p.x for p in rvs)/len(rvs); rcy = sum(p.y for p in rvs)/len(rvs)
            def on_roof(mod, spread):
                # separate ground-miss counter: the bay loop increments n_gmiss too, and
                # printing one number for two populations makes the only falsifiable
                # evidence this fix produces unreadable. gs.miss must equal the sum.
                nonlocal n_roof_rej, n_roof_gmiss
                for _ in range(12):
                    px = rcx + rnd.uniform(-spread, spread); py = rcy + rnd.uniform(-spread, spread)
                    r = SPL.roof_at(bvh_self, px, py)          # THIS building only
                    if r is None:
                        n_roof_rej += 1; continue              # candidate is off the footprint
                    gz = gs.z(px, py)
                    if gz is None:
                        n_roof_gmiss += 1; continue            # fail closed, no invented height
                    if r <= max(zmin, gz) + 3.0:
                        n_roof_rej += 1; continue              # that is a canopy at street level
                    top = SPL.roof_at(bvh_top, px, py)         # topmost over any LIVE building
                    if top is not None and top > r + 0.5:
                        n_roof_rej += 1; continue              # a neighbour/overhang is above
                    flat = True
                    for ox, oy in ((0.7, 0.0), (-0.7, 0.0), (0.0, 0.7), (0.0, -0.7)):
                        q = SPL.roof_at(bvh_self, px + ox, py + oy)
                        if q is None or abs(q - r) > 0.5:
                            flat = False; break
                    if not flat:
                        n_roof_rej += 1; continue              # roof edge or sloped patch
                    put(mod, (px, py, r), rnd.uniform(0, 6.28), roof=(bvh_self, r))
                    return True
                return False
            if H > 11.0: on_roof("ZK_WaterTank_A", 3.0)
            for k in range(rnd.randint(1, 3)): on_roof("ZK_ACUnit_A", 4.0)
    print("buildings dressed: %d | kit instances: %d | rejected %d dup / %d floating"
          % (n_bldg, n_inst, n_dup, n_air))
    print("  bays: %d seated on terrain above the shell base (max lift %.2f m)"
          % (n_lift, lift_max))
    print("  bays skipped: %d ground MISS / %d roof at-or-under seat"
          % (n_gmiss, n_low))
    print("  roof candidates rejected: %d (+ %d ground MISS) | gs.miss=%d must equal %d"
          % (n_roof_rej, n_roof_gmiss, gs.miss, n_gmiss + n_roof_gmiss))
    gs.report("zakkyo")
    return n_inst
