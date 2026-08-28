"""Build the station buildings themselves - SHIBUYA_STATION_HALL.

build_station.py laid track and platforms but no station. And the platform data is
misleading: none of the 9 `railway=platform` ways are JR. The two at level=2 are the
Keio Inokashira line inside Mark City (x -230..-117), the one at level=3 is the Ginza
line (x 127..230), and the rest are deep underground. The JR Yamanote/Saikyo platforms
are simply not tagged as platforms in this extract - they exist only as 38 `railway=rail`
ways at level=2 running 2,904 m north-south.

So the halls are derived from the TRACK corridors instead:
  JR    - barrel-vaulted train shed over the level-2 corridor through the station zone,
          on a glazed concourse block from ground to platform level
  GINZA - the level-3 arched shell, the one recognisable piece of Shibuya station

A vault costs about the same as the flat canopy slabs it replaces and reads far better:
quality up, polygons flat.
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree

_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)             # every script here is exec()'d, so __file__ may not exist
import shibuya_placement_lib as SPL   # NOT `as L`: `L` is a local length variable below

SHIB = r"C:\Work\blender\Shibuya"
FLOOR_H = 4.60
ARC_SEG = 9                       # vault segments; 9 reads curved, 20 just costs tris
# First attempt used x 30..185 / y -265..-45 with half_w 26 and rise 13. That box swallows
# Scramble Square (x 96.8..191.3, y -169.9..-80.8) whole: a 52 m wide, 41 m tall white
# tube drove straight through the tower. Narrowed to the platform stretch, and any vault
# segment whose centre lands inside the tower footprint is skipped - which is also what
# the real shed does, emerging on both sides of the building that sits on top of it.
JR_ZONE  = (60.0, 160.0, -225.0, -110.0)
# Fallback only. The live value is DERIVED from LM_ScrambleSquare_A's world AABB by
# ss_box() - these literals are a hand-copy of numbers that also live in
# build_scramble_square.py, and two copies of one measurement drift.
SS_EXCL  = (94.0, 194.0, -172.0, -78.0)
COL_STEP = 21.0
# 2.7 m, not an arbitrary 1.5. The hand-written SS_EXCL was the tower AABB
# (x 96.8..191.3, y -169.9..-80.8) plus ~2.7 m, and that margin turns out to be doing real
# work: deriving the box with a 1.5 m pad makes it ~1.3 m tighter per side, one more vault
# segment survives, and that segment intersects - hall 24.5% -> 24.8%, hard-fail 39.8% ->
# 41.5%. Matching the measured margin keeps the derivation (no drift against
# build_scramble_square.py) without losing what the hand value had learned.
BLOCK_PAD = 2.7                   # margin around a blocking building's AABB
# A blocker must be a real solid, not a sign. SPL.buildings() matches on the LM_ prefix
# alone, so it returns LM_QFrontScreen - a 15 x 22 m FLAT emissive billboard whose AABB is
# degenerate in one axis and would delete a vault segment for a piece of signage.
MIN_BLOCK_FOOTPRINT = 4.0
# Orphan-column removal is OFF by default and must stay that way unless explicitly asked
# for. The reviewed patch tightened the column gate from `blocked(i)` to `i not in span`,
# which drops the station column count from 16 to 8-14 (mi=1: 192 -> 96..168 tris). The
# standing decision is that piers and columns stay - that is precisely why mi=1 is
# whitelisted in audit_map.MESH_SPEC - so this is a flag, not a default.
DROP_ORPHAN_COLUMNS = False
# The auto-blocker sweep is OFF, and this is a MEASURED verdict, not caution.
#
# The hypothesis was that the hall's 24.5% intersection comes from vault segments driven
# through tall buildings, so skipping those segments should cut it. It does not. With the
# sweep on: hall 368 -> 280 tris (a quarter of the shed deleted), intersection 24.5% ->
# 25.0% - it went UP, because the skipped segments were disproportionately the ones NOT
# intersecting - hard-fail 39.8% -> 39.7% (noise), mi=3 concrete 91.7% -> 90.0%, and
# station columns fell 16 -> 12 (mi=1 192 -> 144), breaking the standing rule that columns
# stay. Removing a quarter of the geometry to move a metric by 0.1 points is not a fix.
#
# The reading: Shibuya's shed genuinely runs under and through the buildings above it -
# Scramble Square is literally built on top of the station - so much of that 24.5% is
# correct. A real reduction needs a different idea (trimming the concourse footprint where
# it overlaps ground-level building volume), not a coarser segment filter.
AUTO_BLOCK = False
# Concourse trimming. Skipping whole vault segments failed (see AUTO_BLOCK above): it is
# too coarse, because a segment is ~9 m of a 23 m-wide box and the overlap is usually a
# few metres on ONE side. So instead of dropping the segment, fit its half-width: raycast
# outward from the centreline at concourse height and stop the wall where the building is.
# The concourse roof (mi=3) measured 11/12 = 91.7% intersecting, the worst number in the
# whole map, and it is a flat slab spanning the full 23 m - exactly the thing that trims.
TRIM_CONCOURSE = True
CONC_CLEAR = 0.35        # stand off the building face
MIN_CONC_HW = 3.0        # below this the concourse is not worth building on that side
# Same idea on the vault shell. Measured: trimming the concourse alone took mi=3 from
# 91.7% to 66.7% and the hall from 24.5% to 23.6% at ZERO triangle cost, where skipping
# whole segments cost 24% of the shed for nothing. The shell (mi=0, 41.7%) is the next
# biggest, and a shed that narrows where the site narrows is what a real one does.
# ...and it does NOT transfer. Measured, on top of the concourse trim:
#   hall 23.6% -> 29.6%, tris 368 -> 416, and mi=1 column intersection 10.4% -> 22.2%.
# The reason is structural: the columns stand at the vault's SPRINGING points, so narrowing
# the shell walks them inward - straight into the building volume the trim was avoiding.
# The concourse has no such coupling, which is why the same idea works there and not here.
TRIM_SHELL = False
MIN_SHELL_HW = 4.0


def mat(name, base, rough, metal=0.0, emis=None, es=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
    o = nt.nodes.new('ShaderNodeOutputMaterial'); o.location = (400, 0)
    b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (150, 0)
    b.inputs['Base Color'].default_value = (*base, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emis:
        b.inputs['Emission Color'].default_value = (*emis, 1)
        b.inputs['Emission Strength'].default_value = es
    nt.links.new(b.outputs['BSDF'], o.inputs['Surface'])
    return m


def wbb(ob):
    M = ob.matrix_world
    pts = [M @ v.co for v in ob.data.vertices]
    return ([min(p[i] for p in pts) for i in range(3)],
            [max(p[i] for p in pts) for i in range(3)])


def ss_box(pad=BLOCK_PAD):
    """Scramble Square's exclusion box, derived from the object rather than hand-copied."""
    for nm in ("LM_ScrambleSquare_A", "LM_ScrambleSquare_PLATEAU_orig"):
        ob = bpy.data.objects.get(nm)
        if ob is None or ob.type != 'MESH' or not ob.data.vertices:
            continue
        # matrix_world is stale right after .location is set, and place_landmarks sets it
        bpy.context.view_layer.update()
        mn, mx = wbb(ob)
        box = (mn[0]-pad, mx[0]+pad, mn[1]-pad, mx[1]+pad)
        print("  SS_EXCL derived from %s: (%.1f, %.1f, %.1f, %.1f)" % (nm, *box))
        return box
    print("  !! no scramble-square object found - falling back to the hard-coded SS_EXCL "
          "%s. Run place_landmarks.py first." % (SS_EXCL,))
    return SS_EXCL


def nearby_bvh(zone, margin=22.0):
    """BVH of EVERY building near the corridor, with no height filter.

    The concourse trim needs all of them: a 12 m block is far too short to qualify as a
    shell blocker but sits squarely across the 23 m-wide concourse. Height-filtering here
    is what made the first concourse attempt useless."""
    z = (zone[0]-margin, zone[1]+margin, zone[2]-margin, zone[3]+margin)
    objs = []
    for ob in SPL.buildings(include_retired=False):
        mn, mx = wbb(ob)
        if mx[0] < z[0] or mn[0] > z[1] or mx[1] < z[2] or mn[1] > z[3]:
            continue
        if (mx[0]-mn[0]) < MIN_BLOCK_FOOTPRINT or (mx[1]-mn[1]) < MIN_BLOCK_FOOTPRINT:
            continue
        objs.append(ob)
    if not objs:
        return None, 0
    bvh, ntri = SPL.make_bvh(objs)
    return bvh, len(objs)


def blocker_bvh(zone, min_top):
    """BVH of the solid buildings the shed could run into, plus their names.

    AABB containment is NOT good enough here and the first attempt proved it: Scramble
    Square's own box is 94 x 89 m, so testing "is the ring centre inside a blocker's AABB"
    blocked every single ring and produced an EMPTY hall (0 verts). The corridor is only
    100 x 115 m - one large footprint swallows it.

    So the AABB is used only as a cheap pre-filter for WHICH buildings to load, and the
    actual test is SPL.in_building against their real geometry at the relevant height."""
    objs = []
    for ob in SPL.buildings(include_retired=False):
        mn, mx = wbb(ob)
        if mx[0] < zone[0] or mn[0] > zone[1] or mx[1] < zone[2] or mn[1] > zone[3]:
            continue
        if (mx[0]-mn[0]) < MIN_BLOCK_FOOTPRINT or (mx[1]-mn[1]) < MIN_BLOCK_FOOTPRINT:
            continue                       # a billboard is not a blocker
        if mx[2] < min_top:
            continue
        objs.append(ob)
    if not objs:
        return None, []
    bvh, _ = SPL.make_bvh(objs)
    return bvh, [o.name for o in objs]


def run():
    ns = {}
    exec(compile(open(os.path.join(SHIB, "osm", "fetch_poi.py"),
                      encoding="utf-8").read().split("if __name__")[0], "f", "exec"), ns)
    to_local = ns["to_local"]
    d = json.load(open(os.path.join(SHIB, "osm", "shibuya_overpass.json"), encoding="utf-8"))

    jr, ginza = [], []
    for e in d["elements"]:
        if e.get("type") != "way" or "geometry" not in e: continue
        t = e.get("tags", {})
        lv = SPL.level_of(t)[0]
        pts = [to_local(g["lat"], g["lon"]) for g in e["geometry"]]
        pts = [p for p in pts if abs(p[0]) < 340 and abs(p[1]) < 340]
        if len(pts) < 2: continue
        if t.get("railway") == "rail" and lv == 2:
            jr += [p for p in pts
                   if JR_ZONE[0] <= p[0] <= JR_ZONE[1] and JR_ZONE[2] <= p[1] <= JR_ZONE[3]]
        elif t.get("railway") == "platform" and lv >= 3:
            ginza += pts

    # fail-closed: the old `return 0.0` on a ray miss would have dropped a vault segment
    # 15 m below the valley floor without a word in the log.
    G = SPL.GroundSampler()
    gz = G.z

    m_shell = mat("M_SH_Shell",   (0.55, 0.56, 0.57), 0.46, 0.25)
    m_rib   = mat("M_SH_Rib",     (0.44, 0.45, 0.47), 0.34, 0.65)
    m_glass = mat("M_SH_Glass",   (0.050, 0.070, 0.100), 0.12, 0.55,
                  (0.55, 0.62, 0.72), 0.30)
    m_conc  = mat("M_SH_Concrete",(0.34, 0.34, 0.33), 0.72)

    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")

    def quad(p0, p1, p2, p3, mi):
        f = bm.faces.new([bm.verts.new(p) for p in (p0, p1, p2, p3)])
        f.material_index = mi
        for l, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))): l[uvl].uv = uv

    def vault(pts, springing, half_w, rise, mi_shell, mi_rib, columns=True, concourse=None,
              excl=None, excl_conc=None, bvh_conc=None):
        """barrel vault along the principal axis of a point cloud"""
        if len(pts) < 4: return 0
        ax, ay, cx, cy = SPL.pca(pts)
        nx, ny = -ay, ax
        proj = [(x-cx)*ax + (y-cy)*ay for x, y in pts]
        t0, t1 = min(proj), max(proj)
        L = t1 - t0
        if L < 20: return 0
        nseg = max(6, int(L/12))
        arcs = [math.pi*k/ARC_SEG for k in range(ARC_SEG+1)]

        def fit_hw(px, py, z, sgn, want, clear):
            """largest half-width on this side of the axis that clears the buildings"""
            if bvh_conc is None:
                return want
            d = Vector((nx*sgn, ny*sgn, 0.0))
            h = bvh_conc.ray_cast(Vector((px, py, z)), d, want + 0.5)
            if h[0] is None:
                return want
            return max(0.0, (h[0] - Vector((px, py, z))).length - clear)

        ring = []
        nogz = set()
        n_narrow = 0
        for i in range(nseg+1):
            t = t0 + L*i/nseg
            px, py = cx+ax*t, cy+ay*t
            g0 = gz(px, py)
            if g0 is None:
                # fail-closed. The old sampler returned 0.0, which would have dropped a
                # 41 m vault segment 15 m under the valley floor with no log entry.
                nogz.add(i)
                g0 = 0.0
            g = g0 + springing
            # The vault used one constant half-width for its whole length, so where the
            # corridor narrows the shell simply went through the wall. Fit each side.
            hwL = hwR = half_w
            if TRIM_SHELL and bvh_conc is not None:
                zp = g + rise*0.45           # widest part of the arc
                hwL = fit_hw(px, py, zp, -1, half_w, CONC_CLEAR)
                hwR = fit_hw(px, py, zp, +1, half_w, CONC_CLEAR)
                if min(hwL, hwR) < half_w - 0.01:
                    n_narrow += 1
                if hwL + hwR < 2*MIN_SHELL_HW:
                    nogz.add(i)              # pinched shut: nothing can be built here
                    hwL = hwR = half_w
            mid = (hwR - hwL)*0.5
            span = (hwR + hwL)*0.5
            ring.append([(px + nx*(mid - math.cos(a)*span),
                          py + ny*(mid - math.cos(a)*span),
                          g + math.sin(a)*rise) for a in arcs])
        if TRIM_SHELL and bvh_conc is not None:
            print("      shell: %d/%d rings narrowed from the full %.1f m half-width"
                  % (n_narrow, nseg+1, half_w))
        # `excl` and `excl_conc` are LISTS of boxes now, and they are different lists on
        # purpose. The shell crown sits at springing+rise while the concourse is a solid
        # block from ground to ground+top, ~7 m lower - so one shared height threshold
        # let every 3-to-5-storey building fail the shell test and keep having the
        # concourse driven straight through it (mi=3 was 11/12 = 91.7% intersecting).
        def _hit(i, spec):
            """spec = (bvh_or_None, probe_z_offset_above_springing, fallback_box)"""
            if i in nogz: return True
            if spec is None: return False
            bvh_b, dz, fbox = spec
            x = (ring[i][0][0] + ring[i][ARC_SEG][0])/2
            y = (ring[i][0][1] + ring[i][ARC_SEG][1])/2
            if fbox and fbox[0] <= x <= fbox[1] and fbox[2] <= y <= fbox[3]:
                return True                # the scramble-square seed box, always honoured
            if bvh_b is None:
                return False
            z = ring[i][0][2] + dz
            return SPL.in_building(bvh_b, x, y, z)

        def blocked(i):
            return _hit(i, excl)

        def blocked_conc(i):
            return _hit(i, excl_conc if excl_conc is not None else excl)

        # Safety valve. If the blocker test kills nearly everything, something is wrong with
        # the test and an empty hall is a far worse outcome than an intersecting one - so
        # fall back to the seed box alone and SAY SO. The first version had no valve and
        # shipped 0 verts.
        surv = sum(1 for i in range(nseg) if not (blocked(i) or blocked(i+1)))
        if surv < max(3, int(0.25*nseg)):
            print("      !! auto-block left only %d/%d shell segments - REVERTING to the "
                  "scramble-square box alone" % (surv, nseg))
            excl = (None, 0.0, excl[2] if excl else None)
            excl_conc = (None, 0.0, excl_conc[2] if excl_conc else None)
            surv = sum(1 for i in range(nseg) if not (blocked(i) or blocked(i+1)))
        surv_c = sum(1 for i in range(nseg) if not (blocked_conc(i) or blocked_conc(i+1)))
        if surv_c < max(3, int(0.25*nseg)):
            print("      !! auto-block left only %d/%d concourse segments - REVERTING"
                  % (surv_c, nseg))
            excl_conc = (None, 0.0, excl_conc[2] if excl_conc else None)
            surv_c = sum(1 for i in range(nseg) if not (blocked_conc(i) or blocked_conc(i+1)))
        print("      segments surviving: shell %d/%d | concourse %d/%d"
              % (surv, nseg, surv_c, nseg))

        for i in range(nseg):
            if blocked(i) or blocked(i+1): continue
            for k in range(ARC_SEG):
                quad(ring[i][k], ring[i+1][k], ring[i+1][k+1], ring[i][k+1], mi_shell)
        # The gable loop used to bypass blocked() entirely, so both end walls were built
        # even when their ring was inside a building - part of the measured 24.5%.
        for i in (0, nseg):                                   # gable ends, glazed
            if blocked(i): continue
            for k in range(ARC_SEG):
                base_z = ring[i][0][2]
                quad(ring[i][k], ring[i][k+1],
                     (ring[i][k+1][0], ring[i][k+1][1], base_z),
                     (ring[i][k][0], ring[i][k][1], base_z), 2)
        n_col = 0
        if columns:
            step = max(1, int(COL_STEP/(L/nseg)))
            for i in range(0, nseg+1, step):
                # Columns are gated on the SHELL box only, and DROP_ORPHAN_COLUMNS is off
                # by default: tightening this further removes station columns, which the
                # standing decision says stay (and which audit_map whitelists as mi=1).
                if blocked(i): continue
                if DROP_ORPHAN_COLUMNS and (blocked(max(0, i-1)) and blocked(min(nseg, i+1))):
                    continue
                for side in (0, ARC_SEG):
                    x, y, z = ring[i][side]
                    g = gz(x, y)
                    if g is None: continue          # no ground -> no column
                    for k in range(6):
                        a0 = 2*math.pi*k/6; a1 = 2*math.pi*(k+1)/6
                        r = 0.55
                        quad((x+r*math.cos(a0), y+r*math.sin(a0), g-0.5),
                             (x+r*math.cos(a1), y+r*math.sin(a1), g-0.5),
                             (x+r*math.cos(a1), y+r*math.sin(a1), z),
                             (x+r*math.cos(a0), y+r*math.sin(a0), z), mi_rib)
                    n_col += 1
        if concourse:
            top, inset = concourse
            hw = half_w - inset

            def free_hw(px, py, g, sgn):
                """Largest half-width on this side that clears the buildings.

                Probes at three heights through the concourse band, because a building can
                encroach at street level and set back higher up (or the reverse, under an
                overhang). The narrowest of the three is the one the slab has to respect."""
                if bvh_conc is None:
                    return hw
                d = Vector((nx*sgn, ny*sgn, 0.0))
                best = hw
                for zf in (0.15, 0.55, 0.92):
                    o = Vector((px, py, g + top*zf))
                    h = bvh_conc.ray_cast(o, d, hw + 0.5)
                    if h[0] is not None:
                        best = min(best, (h[0] - o).length - CONC_CLEAR)
                return max(0.0, best)

            n_trim = 0
            for i in range(nseg):
                if blocked_conc(i) or blocked_conc(i+1): continue
                t_a = t0 + L*i/nseg; t_b = t0 + L*(i+1)/nseg
                ax0, ay0 = cx+ax*t_a, cy+ay*t_a
                ax1, ay1 = cx+ax*t_b, cy+ay*t_b
                g0, g1 = gz(ax0, ay0), gz(ax1, ay1)
                if g0 is None or g1 is None: continue
                # per-END, per-SIDE fitted half-width. The old code used one constant hw for
                # all four corners, which is what drove a 23 m slab through everything.
                w = {}
                for sgn in (1, -1):
                    if TRIM_CONCOURSE:
                        w[(0, sgn)] = free_hw(ax0, ay0, g0, sgn)
                        w[(1, sgn)] = free_hw(ax1, ay1, g1, sgn)
                    else:
                        w[(0, sgn)] = w[(1, sgn)] = hw
                if max(w.values()) < MIN_CONC_HW:
                    continue                       # no room for a concourse here at all
                for sgn in (1, -1):
                    wa, wb = w[(0, sgn)], w[(1, sgn)]
                    if max(wa, wb) < MIN_CONC_HW:
                        continue                   # this side is pinched shut
                    if min(wa, wb) < hw - 0.01:
                        n_trim += 1
                    quad((ax0+nx*wa*sgn, ay0+ny*wa*sgn, g0),
                         (ax1+nx*wb*sgn, ay1+ny*wb*sgn, g1),
                         (ax1+nx*wb*sgn, ay1+ny*wb*sgn, g1+top),
                         (ax0+nx*wa*sgn, ay0+ny*wa*sgn, g0+top), 2)
                # roof spans between the two fitted sides, so it is a trapezoid now
                wl0, wl1 = w[(0, -1)], w[(1, -1)]
                wr0, wr1 = w[(0, 1)], w[(1, 1)]
                quad((ax0-nx*wl0, ay0-ny*wl0, g0+top), (ax0+nx*wr0, ay0+ny*wr0, g0+top),
                     (ax1+nx*wr1, ay1+ny*wr1, g1+top), (ax1-nx*wl1, ay1-ny*wl1, g1+top), 3)
            if TRIM_CONCOURSE:
                print("      concourse: %d side wall(s) trimmed off the full %.1f m"
                      % (n_trim, hw))
        return n_col

    # Two box lists, because the shell and the concourse occupy different z bands. A rough
    # ground level for the corridor is enough to set the thresholds - the shell crown sits
    # at springing + rise above it, the concourse roof at `top`.
    springing = 2*FLOOR_H + 1.0
    rise = 6.0
    top = 2*FLOOR_H
    g_ref = None
    if jr:
        gs = [z for z in (gz(x, y) for x, y in jr[:40]) if z is not None]
        g_ref = sum(gs)/len(gs) if gs else None
    if g_ref is None:
        g_ref = 15.0
    ss = ss_box()
    if AUTO_BLOCK:
        bvh_s, names_s = blocker_bvh(JR_ZONE, g_ref + springing + rise)
        bvh_c, names_c = blocker_bvh(JR_ZONE, g_ref + top)
        print("  blockers: shell %d building(s) over %.1f m | concourse %d over %.1f m"
              % (len(names_s), g_ref + springing + rise, len(names_c), g_ref + top))
        print("      shell:     %s" % (names_s[:6],))
        print("      concourse: %s" % (names_c[:6],))
    else:
        bvh_s = bvh_c = None
        print("  AUTO_BLOCK off (measured: it cost 24%% of the shed and moved the "
              "intersection rate 24.5%% -> 25.0%%). Scramble-square box only.")
    # (bvh, probe height above the ring springing, seed box always honoured)
    excl_shell = (bvh_s, rise*0.5, ss)
    excl_conc = (bvh_c, -(springing - top*0.5), ss)
    bvh_near, n_near = nearby_bvh(JR_ZONE)
    print("  concourse trim: %s (%d nearby buildings, no height filter)"
          % ("ON" if TRIM_CONCOURSE else "OFF", n_near))
    c1 = vault(jr, springing=springing, half_w=14.0, rise=rise,
               mi_shell=0, mi_rib=1, concourse=(top, 2.5),
               excl=excl_shell, excl_conc=excl_conc, bvh_conc=bvh_near)
    # The Ginza shell is dropped: its platform is the only data there, so the arch ends up
    # floating over Meiji-dori on columns planted in the roadway with nothing to attach to.
    c2 = 0

    me = bpy.data.meshes.new("SHIBUYA_STATION_HALL")
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.0005)
    bm.normal_update(); bm.to_mesh(me); bm.free()
    for m in (m_shell, m_rib, m_glass, m_conc): me.materials.append(m)
    me.shade_flat()   # smooth turned a 9-segment vault into a white balloon
    col = bpy.data.collections.get("MAP_SHIBUYA_STATION")
    if col is None:
        col = bpy.data.collections.new("MAP_SHIBUYA_STATION")
        bpy.context.scene.collection.children.link(col)
    old = bpy.data.objects.get("SHIBUYA_STATION_HALL")
    if old: bpy.data.objects.remove(old, do_unlink=True)
    ob = bpy.data.objects.new("SHIBUYA_STATION_HALL", me)
    col.objects.link(ob)
    vs = me.vertices
    print("SHIBUYA_STATION_HALL  jr_pts=%d ginza_pts=%d cols=%d  verts=%s tris=%s  z %.1f..%.1f" % (
        len(jr), len(ginza), c1+c2, format(len(vs), ','),
        format(sum(len(p.vertices)-2 for p in me.polygons), ','),
        min(v.co.z for v in vs), max(v.co.z for v in vs)), flush=True)
    G.report("hall")
    return ob
