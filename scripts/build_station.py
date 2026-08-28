"""Build Shibuya station's rail infrastructure (MAP_SHIBUYA_STATION).

The map has had zero rail geometry since v003: SHIBUYA_RAIL was hidden when the ground
bake took over the corridor, and PLATEAU LOD2 is exterior shells only, so the station
itself was never built. Meanwhile OSM has carried 101 railway ways with full geometry
the whole time.

Built here: ballasted track ribbons for `railway=rail`, raised platform slabs with
canopies for `railway=platform`. `railway=subway` (38 ways) is skipped - it is
underground and would only show as geometry buried in the terrain.

The +/-340 m crop is applied as MAXIMAL CONTIGUOUS RUNS of in-crop vertices, never as a
flat vertex filter: a way that leaves and re-enters the box would otherwise have its two
surviving halves joined into one segment and lay a rail straight across the map. As of
the pinned shibuya_overpass.json no way actually does that (10 of 49 ways have out-of-crop
vertices, all at one end), so the splitter is currently a no-op guard.

All names printed ASCII-escaped: the Windows console is cp949 and raises on kanji.
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree

_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)             # every script here is exec()'d, so __file__ may not exist
import shibuya_placement_lib as SPL   # NOT `as L`: `L` is a local length variable below

SHIB = r"C:\Work\blender\Shibuya"
TRACK_W, BALLAST_H = 3.30, 0.42
RAIL_W, RAIL_H = 0.075, 0.16
PLAT_W, PLAT_H = 9.0, 1.10
CANOPY_H, CANOPY_W, COL_STEP = 4.60, 10.0, 18.0
FLOOR_H = 4.60                  # OSM `level` -> metres above ground
PIER_STEP, PIER_R = 24.0, 0.9   # supports under anything above grade


def mat(name, base, rough, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
    o = nt.nodes.new('ShaderNodeOutputMaterial'); o.location = (400, 0)
    b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (150, 0)
    b.inputs['Base Color'].default_value = (*base, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    nt.links.new(b.outputs['BSDF'], o.inputs['Surface'])
    return m


def run():
    sys.path.insert(0, os.path.join(SHIB, "osm"))
    ns = {}
    exec(compile(open(os.path.join(SHIB, "osm", "fetch_poi.py"), encoding="utf-8").read(),
                 "fetch_poi.py", "exec"), ns)
    to_local = ns["to_local"]

    d = json.load(open(os.path.join(SHIB, "osm", "shibuya_overpass.json"), encoding="utf-8"))
    ways = [e for e in d["elements"]
            if e.get("type") == "way" and "geometry" in e
            and e.get("tags", {}).get("railway") in ("rail", "platform")]
    ways = [w for w in ways if not SPL.level_of(w["tags"])[1]]   # drop the subway lines

    G = SPL.GroundSampler()
    gz = G.z

    # Track was laid straight from the OSM centrelines with no check against the city.
    # At level=2 (9.2 m) that drove 398 of 5,574 faces (7.1%) through buildings - the
    # "bridge overlapping things" that shows up around the station.
    bvh_bld, _ = SPL.make_bvh(SPL.buildings())

    m_bal  = mat("M_ST_Ballast",  (0.115, 0.108, 0.100), 0.88)
    m_rail = mat("M_ST_Rail",     (0.30, 0.28, 0.26),   0.42, 0.85)
    m_plat = mat("M_ST_Platform", (0.52, 0.52, 0.53),   0.62)
    m_can  = mat("M_ST_Canopy",   (0.30, 0.31, 0.33),   0.48, 0.35)
    m_col  = mat("M_ST_Column",   (0.38, 0.39, 0.40),   0.45, 0.55)

    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")

    def quad(p0, p1, p2, p3, mi):
        f = bm.faces.new([bm.verts.new(p) for p in (p0, p1, p2, p3)])
        f.material_index = mi
        for l in f.loops: l[uvl].uv = (0.001, 0.999)

    def ribbon(pts, half, z_off, thick, mi, mi_side=None, lift=0.0):
        """extrude a polyline into a slab draped on the ground.

        Returns (faces_made, skipped) where `skipped` holds the segment indices whose deck
        was dropped for running INSIDE a building. piers() and the canopy-column loop take
        that set so they stop building supports under nothing - measured at 38% of piers
        and 16% of canopy columns, which is what the white comb in the street renders is.

        Only the in-building skip goes in the set. The L < 0.6 and no-ground skips do not:
        a sub-metre segment still has ribbon on both sides of it, so a support there is
        holding up its neighbours, not thin air.
        """
        made = 0
        skipped = set()
        for i in range(len(pts)-1):
            (x0, y0), (x1, y1) = pts[i], pts[i+1]
            dx, dy = x1-x0, y1-y0
            L = math.hypot(dx, dy)
            if L < 0.6: continue
            nx, ny = -dy/L*half, dx/L*half
            g0, g1 = gz(x0, y0), gz(x1, y1)
            if g0 is None or g1 is None: continue
            a, b = g0+z_off+lift, g1+z_off+lift
            if lift > 0.5 and SPL.in_building(bvh_bld, (x0+x1)/2, (y0+y1)/2, (a+b)/2 + 0.5):
                skipped.add(i)
                continue                       # this span is inside a building
            quad((x0-nx, y0-ny, a+thick), (x0+nx, y0+ny, a+thick),
                 (x1+nx, y1+ny, b+thick), (x1-nx, y1-ny, b+thick), mi)
            if thick > 0.01 and mi_side is not None:
                for sgn in (1, -1):
                    quad((x0+sgn*nx, y0+sgn*ny, a), (x1+sgn*nx, y1+sgn*ny, b),
                         (x1+sgn*nx, y1+sgn*ny, b+thick), (x0+sgn*nx, y0+sgn*ny, a+thick), mi_side)
            made += 1
        return made, skipped

    def piers(pts, lift, half, skipped=()):
        """anything above grade needs to stand on something - and only if something is there.

        `skipped` comes from the ballast ribbon() that just ran over the same polyline. A
        pier on one of those segments would rise out of the road to meet a deck that was
        never built, because the track runs through the building at that point.
        """
        n = n_orphan = 0
        run = 0.0
        for i in range(len(pts)-1):
            (x0, y0), (x1, y1) = pts[i], pts[i+1]
            seg = math.hypot(x1-x0, y1-y0)
            t = 0.0
            while t < seg:
                run += 1.0
                if run >= PIER_STEP:
                    f = t/seg if seg else 0.0
                    cx, cy = x0+(x1-x0)*f, y0+(y1-y0)*f
                    g = gz(cx, cy)
                    if g is not None and i in skipped:
                        n_orphan += 1        # would have stood under nothing
                    elif g is not None:
                        for k in range(8):
                            a0 = 2*math.pi*k/8; a1 = 2*math.pi*(k+1)/8
                            quad((cx+PIER_R*math.cos(a0), cy+PIER_R*math.sin(a0), g-0.5),
                                 (cx+PIER_R*math.cos(a1), cy+PIER_R*math.sin(a1), g-0.5),
                                 (cx+PIER_R*math.cos(a1), cy+PIER_R*math.sin(a1), g+lift),
                                 (cx+PIER_R*math.cos(a0), cy+PIER_R*math.sin(a0), g+lift), 4)
                        n += 1
                    run = 0.0
                t += 1.0
        return n, n_orphan

    # ---- crop into MAXIMAL CONTIGUOUS RUNS, not a flat list of surviving vertices ----
    # Filtering per vertex made the survivors on either side of an out-of-crop excursion
    # adjacent in `pts`, so ribbon() / piers() / the canopy-column loop below joined two
    # nodes that were never neighbours and laid a rail straight across the map. Emitting
    # each run separately also restarts the per-run accumulators for free: the rail offset
    # polyline only ever sees in-run neighbours, `piers()`'s local `run` and the platform
    # branch's `run_len` are (re)initialised once per run, which is what we want - spacing
    # should restart at the start of a run, not carry a phase across a gap.
    jobs = []                     # (kind, lift, pts), one entry per contiguous run
    n_split = 0                   # ways that produced more than one run
    for w in ways:
        kind = w["tags"]["railway"]
        lift = SPL.level_of(w["tags"])[0] * FLOOR_H   # [0] = storey; [1] = underground, filtered above
        cur, nrun = [], 0
        for g in list(w["geometry"]) + [None]:        # sentinel closes the trailing run
            if g is not None:
                x, y = to_local(g["lat"], g["lon"])
                if abs(x) < 340 and abs(y) < 340:
                    cur.append((x, y)); continue
            if len(cur) >= 2:                         # same threshold as the old len(pts) < 2
                jobs.append((kind, lift, cur)); nrun += 1
            cur = []
        if nrun > 1: n_split += 1

    n_rail = n_plat = n_col = n_pier = 0
    n_pier_orphan = n_col_orphan = 0
    for kind, lift, pts in jobs:

        if kind == "rail":
            made, deck_gap = ribbon(pts, TRACK_W/2, 0.05, BALLAST_H, 0, 0, lift)
            n_rail += made
            for off in (-0.717, 0.717):                       # 1435 mm gauge
                rp = []
                for i, (x, y) in enumerate(pts):
                    if i == 0: dx, dy = pts[1][0]-x, pts[1][1]-y
                    else:      dx, dy = x-pts[i-1][0], y-pts[i-1][1]
                    L = math.hypot(dx, dy) or 1.0
                    rp.append((x - dy/L*off, y + dx/L*off))
                ribbon(rp, RAIL_W, BALLAST_H+0.05, RAIL_H, 1, 1, lift)
            if lift > 0.5:
                p, orph = piers(pts, lift, TRACK_W/2, deck_gap)
                n_pier += p; n_pier_orphan += orph
        else:
            n_plat += ribbon(pts, PLAT_W/2, 0.0, PLAT_H, 2, 2, lift)[0]
            # the columns hold up the CANOPY, so they follow the canopy's gaps, not the
            # platform's - the two ribbons test in_building at different heights
            _, roof_gap = ribbon(pts, CANOPY_W/2, CANOPY_H, 0.22, 3, 3, lift)
            run_len = 0.0
            for i in range(len(pts)-1):
                (x0, y0), (x1, y1) = pts[i], pts[i+1]
                seg = math.hypot(x1-x0, y1-y0)
                t = 0.0
                while t < seg:
                    if run_len + t >= COL_STEP:
                        f = (t/seg) if seg else 0
                        cx, cy = x0+(x1-x0)*f, y0+(y1-y0)*f
                        g = gz(cx, cy)
                        if g is not None and i in roof_gap:
                            n_col_orphan += 2      # a pair per station, both orphaned
                        elif g is not None:
                            g = g + lift
                            for sgn in (-1, 1):
                                dx, dy = x1-x0, y1-y0
                                L = math.hypot(dx, dy) or 1.0
                                ox, oy = -dy/L*(CANOPY_W/2-0.8)*sgn, dx/L*(CANOPY_W/2-0.8)*sgn
                                for k in range(6):
                                    a0 = 2*math.pi*k/6; a1 = 2*math.pi*(k+1)/6
                                    r = 0.16
                                    quad((cx+ox+r*math.cos(a0), cy+oy+r*math.sin(a0), g+PLAT_H),
                                         (cx+ox+r*math.cos(a1), cy+oy+r*math.sin(a1), g+PLAT_H),
                                         (cx+ox+r*math.cos(a1), cy+oy+r*math.sin(a1), g+CANOPY_H),
                                         (cx+ox+r*math.cos(a0), cy+oy+r*math.sin(a0), g+CANOPY_H), 4)
                                n_col += 1
                        run_len = 0.0
                    t += 1.0; run_len += 1.0

    me = bpy.data.meshes.new("SHIBUYA_STATION")
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.001)
    bm.normal_update(); bm.to_mesh(me); bm.free()
    for m in (m_bal, m_rail, m_plat, m_can, m_col): me.materials.append(m)
    me.shade_flat()
    col = bpy.data.collections.get("MAP_SHIBUYA_STATION")
    if col is None:
        col = bpy.data.collections.new("MAP_SHIBUYA_STATION")
        bpy.context.scene.collection.children.link(col)
    # Remove only THIS builder's output. Clearing the whole collection also deleted
    # SHIBUYA_STATION_HALL, which shares it - running build_station.py on its own silently
    # dropped the hall from the scene. build_station_hall.py:464 already does it this way.
    old = bpy.data.objects.get("SHIBUYA_STATION")
    if old is not None: bpy.data.objects.remove(old, do_unlink=True)
    ob = bpy.data.objects.new("SHIBUYA_STATION", me)
    col.objects.link(ob)
    print("SHIBUYA_STATION  rail_segs=%d plat_segs=%d columns=%d piers=%d  "
          "runs=%d/%d ways (%d split)  tris=%s" % (
              n_rail, n_plat, n_col, n_pier, len(jobs), len(ways), n_split,
              format(sum(len(p.vertices)-2 for p in me.polygons), ',')), flush=True)
    # auditable: how many supports were dropped, and for what share of the total
    print("  orphan supports removed: piers %d/%d (%.0f%%)  canopy columns %d/%d (%.0f%%)"
          % (n_pier_orphan, n_pier + n_pier_orphan,
             100.0*n_pier_orphan/max(n_pier + n_pier_orphan, 1),
             n_col_orphan, n_col + n_col_orphan,
             100.0*n_col_orphan/max(n_col + n_col_orphan, 1)), flush=True)
    G.report("station")
    return ob
