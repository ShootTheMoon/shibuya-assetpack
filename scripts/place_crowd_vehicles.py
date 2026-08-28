"""Phase 1c pass 2 (Blender): instance the crowd and vehicles from the transforms
computed by compute_crowd_vehicles.py. Linked duplicates only (Tier C) - Geometry
Nodes instances realise on glTF export, which would blow the OVERDARE budget.

Pedestrian meshes face local -Y, so world yaw phi maps to rotation_z = phi + pi/2.
Both are draped onto SHIBUYA_GROUND by ray_cast; the crowd transforms are 2D.

v027: this script used to read NO building geometry at all - pass 1 runs in system Python
and only ever sees tran_local.json, so neither pass could tell a wall from open street.
Both loops now reject placements that are walled in (SPL.enclosed against the building
soup). The crowd is OFF by default because v026 ships without it; run(crowd=True) to
rebuild it deliberately.
"""
import bpy, os, sys, json, math, random
from mathutils import Vector
from mathutils.bvhtree import BVHTree

_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)             # every script here is exec()'d, so __file__ may not exist
import shibuya_placement_lib as SPL

PACK = r"C:\Work\blender\ShibuyaAssetPack"
TR   = os.path.join(PACK, "06_Placement", "transforms")
CROWD_BLEND = os.path.join(PACK, "00_Source_Blender", "CR_Crowd", "CR_Pedestrians.blend")
VEH_BLEND   = os.path.join(PACK, "00_Source_Blender", "VH_Vehicles", "VH_TaxiCrown_A.blend")
PEDS = SPL.PEDESTRIANS      # single roster, shared with compute_crowd_vehicles.py
# compute_crowd_vehicles.py has written a variant id `v` (0-3) per vehicle since Phase 1c
# and this placer ignored it, so all 88 cars were the same taxi. These MUST be four separate
# mesh datablocks: shibuya_export_v2.classify() keys on o.data.name, so material-only
# variants would collapse into one export entry and the variety would never reach OVERDARE.
# They share the reduced Crown Comfort bodyshell - only variant 0 keeps the andon roof lamp.
VEHS = ["VH_TaxiCrown_A", "VH_SedanWhite_A", "VH_SedanSilver_A", "VH_SedanBlue_A"]
FACE_OFFSET = math.pi / 2          # model forward is -Y


def link_from(path, names):
    missing = [n for n in names if n not in bpy.data.objects]
    if missing:
        with bpy.data.libraries.load(path, link=False) as (df, dt):
            dt.objects = [n for n in df.objects if n in missing]
    out = {}
    for n in names:
        o = bpy.data.objects.get(n)
        if o is None: continue
        if not o.users_collection: bpy.context.scene.collection.objects.link(o)
        o.hide_render = True; o.hide_viewport = True
        out[n] = o
    return out


def fresh(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name); bpy.context.scene.collection.children.link(c)
    for o in list(c.objects): bpy.data.objects.remove(o, do_unlink=True)
    return c


def run(crowd_limit=None, veh_limit=None, radius=200.0, crowd=False):
    # crowd defaults OFF. v026 has no MAP_SHIBUYA_CROWD: the 1,084 pedestrians were deleted
    # on purpose for the empty-background look, and shibuya_export_v2.INSTANCED_COLLECTIONS
    # carries the matching "# CROWD removed from the map" comment. fresh() CREATES the
    # collection when it is missing, so the old default would have put every one of them
    # back into the .blend - and into the triangle budget - on a bare v027 rebuild call.
    # Skipping link_from as well keeps 18 unused CR_Pedestrian datablocks out of the file.
    rnd = random.Random(1357)
    ped = link_from(CROWD_BLEND, PEDS) if crowd else {}
    veh = link_from(VEH_BLEND, VEHS)
    if (crowd and not ped) or not veh:
        print("MISSING masters ped=%d veh=%d" % (len(ped), len(veh))); return 0, 0

    # this was already the only correctly fail-closed probe in the codebase; it is now
    # the shared one, so the miss count shows up in the log like everywhere else.
    G = SPL.GroundSampler(top=400.0)
    gz = G.z

    # The containment check this script never had. compute_crowd_vehicles.py cannot do it:
    # it runs in system Python with no bpy and sees only tran_local.json, so it has no
    # notion of a building at all. enclosed() is parity AND no horizontal escape - parity
    # alone overcounts ~5.7x. The current map-wide containment rate is 0.34% (65 of 22,331
    # zakkyo instances, measured by audit_map); the 3.0% quoted in
    # shibuya_placement_lib.enclosed() is an older 421-instance sample. Requiring both
    # conditions is what stops this gate deleting people who are legitimately standing in a
    # facade recess or under an overhang.
    bvh_bld, ntri = SPL.make_bvh(SPL.buildings())
    print("building BVH: %d tris" % ntri)

    C = json.load(open(os.path.join(TR, "crowd.json")))["crowd"] if crowd else []
    V = json.load(open(os.path.join(TR, "vehicles.json")))["veh"]
    # `if crowd_limit:` made a limit of 0 mean "no limit" and instanced the whole file.
    if crowd_limit is not None: C = C[:crowd_limit]
    if veh_limit is not None:   V = V[:veh_limit]

    # fresh() creates the collection when it is missing, so this line is exactly what would
    # resurrect the deleted crowd. Only touch MAP_SHIBUYA_CROWD when it was asked for.
    cc = fresh("MAP_SHIBUYA_CROWD") if crowd else None
    vc = fresh("MAP_SHIBUYA_VEHICLES")
    n_c = n_v = skipped = walled = 0
    for i, p in enumerate(C):
        if math.hypot(p["x"], p["y"]) > radius: continue
        z = gz(p["x"], p["y"])
        if z is None: skipped += 1; continue
        # Probe the EXACT world Z the audit will probe: audit_map.py:142 tests
        # enclosed(..., o.location.z + 1.2) and location.z is set to ground + 0.02 below.
        # enclosed() is not monotonic in Z - a point can be open at 1.00 m and pinched at
        # 1.22 m - so a gate at a different height does not actually guarantee the metric.
        # Written as the literal sum so the two stay coupled if either lift changes.
        if SPL.enclosed(bvh_bld, p["x"], p["y"], z + 0.02 + 1.2): walled += 1; continue
        m = ped[PEDS[p["v"] % len(PEDS)]]
        o = m.copy(); o.data = m.data
        o.name = "CR_%05d" % n_c
        o.hide_render = False; o.hide_viewport = False
        o.location = (p["x"], p["y"], z + 0.02)
        o.rotation_euler = (0, 0, p["yaw"] + FACE_OFFSET)
        cc.objects.link(o); n_c += 1
    for i, p in enumerate(V):
        if math.hypot(p["x"], p["y"]) > radius: continue
        z = gz(p["x"], p["y"])
        if z is None: skipped += 1; continue
        # Drawn BEFORE the reject so the fixed seed 1357 keeps its call order. rnd is
        # consumed exactly once per PLACED vehicle, so putting the gate above this line
        # would re-roll the jitter of every later taxi the moment one is rejected - and
        # shift every VH_%04d name by one - making the run non-comparable to the baseline
        # for a change that is meant to move almost nothing.
        jit = rnd.uniform(-0.03, 0.03)
        # same world Z as the audit: location.z is ground + 0.01 below, audit adds 1.2
        if SPL.enclosed(bvh_bld, p["x"], p["y"], z + 0.01 + 1.2): walled += 1; continue
        m = veh[VEHS[p["v"] % len(VEHS)]]
        o = m.copy(); o.data = m.data
        o.name = "VH_%04d" % n_v
        o.hide_render = False; o.hide_viewport = False
        o.location = (p["x"], p["y"], z + 0.01)
        # The old comment here said "+Y long axis, so it needs no extra quarter turn" and
        # had it exactly backwards. `yaw` is atan2(ay, ax) - an angle from +X - while all
        # four car meshes measure long-axis Y 4.60..4.74 m against X 1.75 m, i.e. they face
        # local +Y, which already sits at +90deg. Setting rotation_z = yaw therefore aimed
        # every car at yaw+90deg and parked all 92 of them broadside across the road.
        # Same correction the pedestrians already carry at :115, opposite sign because they
        # face -Y and these face +Y.
        o.rotation_euler = (0, 0, p["yaw"] - math.pi/2 + jit)
        vc.objects.link(o); n_v += 1
    print("crowd=%d vehicles=%d (ground miss %d, walled-in rejected %d)"
          % (n_c, n_v, skipped, walled))
    if not crowd:
        print("  crowd SKIPPED: v026 ships without it, MAP_SHIBUYA_CROWD was NOT created."
              "  run(crowd=True) rebuilds ~1,084 pedestrians (+617,880 tris, +8.8%).")
    G.report("crowd/vehicles")
    return n_c, n_v
