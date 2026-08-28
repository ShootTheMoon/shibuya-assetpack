"""Phase 1d: swap the PLATEAU boxes for the hand-modelled / imported landmarks.

- LM_Shibuya109   -> LM_Shibuya109_A  (hand-modelled tapered wedge tower + 109 sign drum)
- LM_Hachiko      -> LM_Hachiko_A     (CC-BY statue, snapped onto the plaza)
- Scramble Square -> LM_ScrambleSquare_A  (hand-modelled 230.7 m superellipse tower)
- Aogaeru                              (CC-BY-NC deha5001 carriage on the Hachiko plaza)
- QFRONT screen                        (emissive media screen on the Scramble-facing wall)

Originals are moved to MAP_SHIBUYA_LM_ORIG and hidden, never deleted.
"""
import bpy, os, sys, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree

_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)             # every script here is exec()'d, so __file__ may not exist
import shibuya_placement_lib as SPL

PACK = r"C:\Work\blender\ShibuyaAssetPack"
SRC  = os.path.join(PACK, "00_Source_Blender", "LM_Landmarks")
TEX  = os.path.join(PACK, "03_Textures", "LM_Landmarks")


def link_obj(path, name):
    if name not in bpy.data.objects:
        with bpy.data.libraries.load(path, link=False) as (df, dt):
            dt.objects = [n for n in df.objects if n == name]
    o = bpy.data.objects.get(name)
    if o and not o.users_collection:
        bpy.context.scene.collection.objects.link(o)
    return o


def bounds(o):
    vs = o.data.vertices
    mn = [min(v.co[i] for v in vs) for i in range(3)]
    mx = [max(v.co[i] for v in vs) for i in range(3)]
    return mn, mx


def wbounds(o):
    """World-space AABB. PLATEAU objects carry an identity transform (the anchor offset
    is baked into mesh data), so this equals bounds() for them - but the scramble-square
    host is found by geometry, so it must not assume that."""
    M = o.matrix_world
    pts = [M @ v.co for v in o.data.vertices]
    mn = [min(p[i] for p in pts) for i in range(3)]
    mx = [max(p[i] for p in pts) for i in range(3)]
    return mn, mx


def retire(o, orig):
    for c in list(o.users_collection): c.objects.unlink(o)
    orig.objects.link(o)
    o.hide_render = True; o.hide_viewport = True


def run():
    sc = bpy.context.scene
    orig = bpy.data.collections.get("MAP_SHIBUYA_LM_ORIG")
    if orig is None:
        orig = bpy.data.collections.new("MAP_SHIBUYA_LM_ORIG"); sc.collection.children.link(orig)
    lm = bpy.data.collections.get("MAP_SHIBUYA_LANDMARKS") or sc.collection
    # a landmark dropped to z=0.0 by a missed ray would sit ~15 m under the valley floor,
    # so a miss now skips the placement and shows up in the log.
    G = SPL.GroundSampler(top=400.0)
    gz = G.z

    done = []

    # ---------------- 109 ----------------
    old = bpy.data.objects.get("LM_Shibuya109")
    new = link_obj(os.path.join(SRC, "LM_Shibuya109_A.blend"), "LM_Shibuya109_A")
    if old and new:
        mn, mx = bounds(old)
        cx, cy = (mn[0]+mx[0])/2, (mn[1]+mx[1])/2
        new.location = (cx, cy, mn[2] - 0.4)      # sit slightly into the ground, no float
        new.hide_render = False; new.hide_viewport = False
        for c in list(new.users_collection): c.objects.unlink(new)
        lm.objects.link(new)
        retire(old, orig)
        done.append(("109", cx, cy, mn[2]))

    # ---------------- Hachiko ----------------
    old = bpy.data.objects.get("LM_Hachiko")
    new = link_obj(os.path.join(SRC, "LM_Hachiko_A.blend"), "LM_Hachiko_A")
    if old and new:
        mn, mx = bounds(old)
        cx, cy = (mn[0]+mx[0])/2, (mn[1]+mx[1])/2
        hz = gz(cx, cy)
        if hz is not None:
            new.location = (cx, cy, hz)
            new.rotation_euler = (0, 0, math.radians(-120))   # faces the Scramble
            new.hide_render = False; new.hide_viewport = False
            for c in list(new.users_collection): c.objects.unlink(new)
            lm.objects.link(new)
            retire(old, orig)
            done.append(("hachiko", cx, cy, hz))

    # ---------------- Aogaeru (deha5001) on the Hachiko plaza ----------------
    new = link_obj(os.path.join(SRC, "LM_Aogaeru_A.blend"), "LM_Aogaeru_A")
    if new:
        ax, ay = 14.5, -36.0          # plaza edge, clear of the statue - placed by eye,
                                      # there is no geometric anchor for a plaza prop.
                                      # v027 S3: the user's call is that this is NOT a
                                      # defect. Do not "fix" it into a raycast - there is
                                      # no wall or footprint for a plaza prop to snap to.
        az = gz(ax, ay)
        if az is not None:
            new.location = (ax, ay, az)
            new.rotation_euler = (0, 0, math.radians(28))
            new.hide_render = False; new.hide_viewport = False
            for c in list(new.users_collection): c.objects.unlink(new)
            lm.objects.link(new)
            done.append(("aogaeru", ax, ay, az))

    # ---------------- Shibuya Scramble Square ----------------
    # PLATEAU ships the 230.7 m tower as an unnamed flat-topped box, so the host is
    # found by GEOMETRY, not by name: SHIBUYA_BLDG__53393596.033 is the id in the
    # current import but a re-import renumbers the loose parts. The footprint below is
    # measured, and the >200 m height test makes it unambiguous - nothing else in the
    # crop comes close (next tallest in this box is 34.1 m).
    host = bpy.data.objects.get("LM_ScrambleSquare_PLATEAU_orig")
    if host is None:
        SSBOX = (96.0, 192.0, -170.5, -80.0)
        for o in bpy.data.objects:
            if o.type != 'MESH' or not o.data.vertices or o.name.startswith("LM_Scramble"):
                continue
            mn, mx = wbounds(o)
            cx, cy = (mn[0]+mx[0])/2, (mn[1]+mx[1])/2
            if (SSBOX[0] <= cx <= SSBOX[1] and SSBOX[2] <= cy <= SSBOX[3]
                    and mx[2]-mn[2] > 200.0):
                host = o; host.name = "LM_ScrambleSquare_PLATEAU_orig"; break
    new = link_obj(os.path.join(SRC, "LM_ScrambleSquare_A.blend"), "LM_ScrambleSquare_A")
    if host and new:
        mn, mx = wbounds(host)
        cx, cy = (mn[0]+mx[0])/2, (mn[1]+mx[1])/2
        new.location = (cx, cy, mn[2] - 0.3)      # seat into the podium, no float
        new.rotation_euler = (0, 0, 0)
        new.hide_render = False; new.hide_viewport = False
        for c in list(new.users_collection): c.objects.unlink(new)
        lm.objects.link(new)
        if "MAP_SHIBUYA_LM_ORIG" not in [c.name for c in host.users_collection]:
            retire(host, orig)
        done.append(("scramble", cx, cy, mn[2] - 0.3))

    # ---------------- Q-FRONT media screen ----------------
    # The host is resolved by GEOMETRY, never by name. "SHIBUYA_BLDG__53393596.060" was a
    # Blender duplicate-name suffix, NOT a PLATEAU gml_id: the tile OBJ
    # Shibuya\obj\53393596\53393596_bldg_6677.obj carries zero `o`/`g` records - one mesh
    # with 668 usemtl groups - so every .NNN index came out of separate(type='LOOSE'), and a
    # re-import renumbers all of them (_state.json already has holes at .014 and .042). The
    # old lookup also failed silently: a stale id just leaves `host` None and the screen
    # disappears with nothing in the log.
    #
    # Anchor = OSM node 2637854588, addr:housename=QFRONT (1F), lat 35.6597918 lon
    # 139.7004106, projected with Shibuya\geo\shibuya_geo.py:jprect_zone9 against the pinned
    # Scramble anchor 35.6594821 / 139.7005723 -> local (-14.6, 34.4).
    QF_ANCHOR = (-14.6, 34.4)
    # The anchor node is amenity=cafe / addr:floor=1F - a shop INSIDE Q-FRONT, not a
    # footprint or entrance node - so any single step-out distance is a guess, and if it is
    # too short the probe starts inside the solid and find_nearest locks onto the wrong
    # (interior) face. Step outward until the probe is provably in open air instead.
    QF_STEPS  = (6.0, 9.0, 12.0, 15.0, 18.0)
    QF_UP     = 20.0     # search at screen height; below ~10 m LOD2 carries entrance canopies
    QF_REACH  = 14.0     # doubles as the sanity gate: no facade within this -> skip
    QF_STAND  = 0.35     # stand proud of the wall (the vending machines use 0.42)
    QF_MINH   = 8.0      # under this the anchor is on the wrong wall - skip, do not fake it
    QF_TOPGAP = 1.0      # leave the parapet clear
    QF_FLOOR  = 4.0      # never slide the screen bottom below base + this

    # "LM_QFrontScreen" starts with "LM_", so it IS in SPL.buildings(): on a re-run
    # find_nearest would lock onto the previous run's own quad at distance 0 and the screen
    # would walk further into the street every time. Excluding it by name solves that
    # WITHOUT deleting it first - deleting first means every one of the eight skip paths
    # below destroys the existing screen and builds nothing, which is a worse scene than the
    # mispositioned quad this is meant to repair. The removal now happens only on success.

    def qfront_wall():
        """Raycast the real Scramble-facing facade.

        -> (px, py, nrm, z0, W, Hh) in WORLD space, or None. Every failure path prints and
        returns None rather than substituting a number - see the SPL module docstring."""
        u = Vector((-QF_ANCHOR[0], -QF_ANCHOR[1], 0.0))
        if u.length < 1e-6:
            print("  qfront SKIP: anchor is at the origin"); return None
        u.normalize()                            # anchor -> Scramble, i.e. the street side
        # exclude our own previous screen from the soup rather than deleting it up front
        bld = [b for b in SPL.buildings(include_retired=False)
               if b.name != "LM_QFrontScreen"]
        bvh_all, _ = SPL.make_bvh(bld)           # FromObject fails on the multi-object soup
        qx = qy = qg = None
        for off in QF_STEPS:
            tx, ty = QF_ANCHOR[0] + u.x*off, QF_ANCHOR[1] + u.y*off
            tg = gz(tx, ty)
            if tg is None:                       # fail closed: never substitute 0.0 or 15.0
                continue
            if SPL.in_building(bvh_all, tx, ty, tg + QF_UP):
                continue                         # still inside the solid - step further out
            qx, qy, qg = tx, ty, tg
            break
        if qx is None:
            print("  qfront SKIP: no probe origin in open air at %s m out from the anchor"
                  % (QF_STEPS,)); return None
        hit = bvh_all.find_nearest(Vector((qx, qy, qg + QF_UP)), QF_REACH)
        if hit is None or hit[0] is None:
            print("  qfront SKIP: no facade within %.1f m of (%.1f, %.1f, %.1f)"
                  % (QF_REACH, qx, qy, qg + QF_UP)); return None
        loc, hn, _fi, dist = hit
        nn = Vector((hn.x, hn.y, 0.0))           # flatten to horizontal, as place_phase1a does
        if nn.length < 1e-4:
            print("  qfront SKIP: nearest face is horizontal (slab/canopy) at %.2f m" % dist)
            return None
        nn.normalize()
        # FromPolygons normals follow the source winding, so force the normal back toward
        # the probe instead of trusting PLATEAU's winding.
        if nn.dot(Vector((qx - loc.x, qy - loc.y, 0.0))) < 0.0:
            nn = -nn
        if nn.dot(u) < 0.2:
            print("  qfront SKIP: that wall faces away from the Scramble (n.u = %.2f)"
                  % nn.dot(u)); return None
        # Which building owns that face? The smallest world AABB containing the hit point.
        host = None; vol = None
        for ob in bld:
            bmn, bmx = wbounds(ob)
            if not (bmn[0]-0.5 <= loc.x <= bmx[0]+0.5 and bmn[1]-0.5 <= loc.y <= bmx[1]+0.5
                    and bmn[2]-0.5 <= loc.z <= bmx[2]+0.5):
                continue
            v = (bmx[0]-bmn[0])*(bmx[1]-bmn[1])*(bmx[2]-bmn[2])
            if vol is None or v < vol:
                host, vol = ob, v
        if host is None:
            print("  qfront SKIP: no building AABB contains (%.1f, %.1f, %.1f)"
                  % (loc.x, loc.y, loc.z)); return None
        bmn, bmx = wbounds(host)
        if bmx[2] - bmn[2] < 12.0:               # a 22 m screen does not go on a 3 m shed
            print("  qfront SKIP: host %s is only %.1f m tall"
                  % (host.name, bmx[2]-bmn[2])); return None
        px, py = loc.x + nn.x*QF_STAND, loc.y + nn.y*QF_STAND
        # Roof over THIS building only - probed against the combined soup a low block
        # reports the tower pressed against its back wall (see SPL.roof_min).
        bvh_h, _ = SPL.make_bvh([host])
        rmin = SPL.roof_min(bvh_h, px, py, nn.x, nn.y)
        rmax = SPL.roof_max(bvh_h, px, py, -nn.x, -nn.y)
        if rmin is None:
            print("  qfront SKIP: roof probe missed over (%.1f, %.1f)" % (px, py)); return None
        base = bmn[2]
        W, Hh = 15.0, 22.0
        z0 = base + 14.0
        if z0 + Hh > rmin - QF_TOPGAP:                        # slide down before shrinking
            z0 = max(base + QF_FLOOR, rmin - QF_TOPGAP - Hh)
            if z0 + Hh > rmin - QF_TOPGAP:
                Hh = rmin - QF_TOPGAP - z0
                W = Hh * (15.0/22.0)                          # keep aspect, do not stretch
        print("  qfront host=%s d=%.2f n=(%.2f,%.2f) base=%.1f roof min=%.1f max=%s"
              % (host.name, dist, nn.x, nn.y, base, rmin,
                 ("%.1f" % rmax) if rmax is not None else "-"))
        if Hh < QF_MINH:
            print("  qfront SKIP: only %.1f m of usable wall between %.1f and %.1f"
                  % (max(Hh, 0.0), base + QF_FLOOR, rmin - QF_TOPGAP)); return None
        if Hh < 22.0:
            print("  qfront resized to %.1f x %.1f m at z0=%.1f" % (W, Hh, z0))
        return px, py, nn, z0, W, Hh

    qf = qfront_wall()
    if qf:
        px, py, nrm, z0, W, Hh = qf
        # only now that a replacement is guaranteed
        old_scr = bpy.data.objects.get("LM_QFrontScreen")
        if old_scr:
            bpy.data.objects.remove(old_scr, do_unlink=True)
        img = bpy.data.images.load(os.path.join(TEX, "LM_QFront_screen.png"), check_existing=True)
        m = bpy.data.materials.get("M_LM_QFrontScreen") or bpy.data.materials.new("M_LM_QFrontScreen")
        m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (500, 0)
        b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (250, 0)
        t = nt.nodes.new('ShaderNodeTexImage'); t.image = img; t.location = (-300, 0)
        nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
        nt.links.new(t.outputs['Color'], b.inputs['Emission Color'])
        b.inputs['Emission Strength'].default_value = 6.0
        nt.links.new(b.outputs['BSDF'], out.inputs['Surface'])

        # tg = (-n.y, n.x) makes the Newell normal of [BL, BR, TR, TL] come out exactly
        # +nrm, so the flip guard below should never fire - which matters, because
        # MeshPolygon.flip() reverses the loop order and would mirror the UVs assigned two
        # lines under it, printing the screen content backwards.
        tg = Vector((-nrm.y, nrm.x, 0))
        V = [(px - tg.x*W/2, py - tg.y*W/2, z0),
             (px + tg.x*W/2, py + tg.y*W/2, z0),
             (px + tg.x*W/2, py + tg.y*W/2, z0 + Hh),
             (px - tg.x*W/2, py - tg.y*W/2, z0 + Hh)]
        me = bpy.data.meshes.new("LM_QFrontScreen")
        me.from_pydata(V, [], [(0, 1, 2, 3)]); me.update()
        me.materials.append(m)
        uvl = me.uv_layers.new(name="UVMap")
        uvl.uv.foreach_set("vector", [0, 0, 1, 0, 1, 1, 0, 1])
        # The quad's normal must point at the street, not into the wall. Re-keyed onto the
        # surface normal so the guard stays meaningful now that px/py/tg no longer derive
        # from the AABB direction. As before, tg = (-n.y, n.x) makes the Newell normal come
        # out exactly +nrm, so this remains a no-op and the UVs are never mirrored - the old
        # guard was internally consistent too, it just measured against a direction that was
        # itself several metres off on a facade that is not axis-aligned.
        if me.polygons[0].normal.dot(nrm) < 0:
            me.polygons[0].flip()
            print("  qfront NOTE: winding guard fired - the UVs are now mirrored")
        o = bpy.data.objects.new("LM_QFrontScreen", me)
        lm.objects.link(o)
        done.append(("qfront", px, py, z0))

    for n, x, y, z in done:
        print("  %-9s at (%.1f, %.1f, %.1f)" % (n, x, y, z))
    G.report("landmarks")
    return done
