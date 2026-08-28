"""Build the 首都高速3号渋谷線 viaduct (MAP_SHIBUYA_VIADUCT).

The three `elevated` polygons have been sitting in tran_local.json unused since v003:
they were filtered OUT of the ground bake (otherwise the expressway paints itself across
rooftops) but never built as geometry. In reality it is one of the most conspicuous
structures in the crop, running above Meiji-dori right past the station.

PLATEAU LOD2 tran carries Z = 0 for everything here, so the deck height is synthesised.
It is NOT one number per polygon. Each elevated polygon is ~707 m long and the ground
under it falls ~20 m into the Shibuya valley (33 m at the Aoyama end, 13.6 m at the
floor, 18 m going out toward Ebisu - `dem_z` of the road polygons within 70 m of the
axis), so a single mean left the deck top 0.4 m above grade at one end and 23.1 m above
it at the other: one end buried, the other floating. A real expressway runs at a
constant GRADE, so the height is a least-squares line z(t) = zb + grade*(t - tb) over
the projection t onto the polygon's long axis (SPL.pca), evaluated per vertex, with
DECK_CLEARANCE above it.

That keeps every face planar: t is linear in (x, y), so z(t) is AFFINE in (x, y) and the
deck is one tilted plane rather than one horizontal one. The top n-gon does not become
non-planar, so it is left as an n-gon and shade_flat stays correct.

Deck slab + edge barriers + a pier every PIER_STEP metres down the polygon's long axis.
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree

_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)             # every script here is exec()'d, so __file__ may not exist
import shibuya_placement_lib as SPL

SHIB = r"C:\Work\blender\Shibuya"
DECK_CLEARANCE, DECK_T = 15.0, 1.7   # deck TOP above the fitted grade line; slab thickness
MIN_PIER_H = 4.5                     # deck_top - ground below which a pier is logged short
BARRIER = 1.15
PIER_STEP, PIER_R = 32.0, 1.5


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
    T = json.load(open(os.path.join(SHIB, "tran", "tran_local.json"), encoding="utf-8"))
    ev = [p for p in T["polys"] if p.get("elevated")]
    if not ev:
        print("no elevated polygons"); return None
    G = SPL.GroundSampler()
    gz = G.z

    m_deck = mat("M_VD_Deck",    (0.085, 0.085, 0.090), 0.72)
    m_bar  = mat("M_VD_Barrier", (0.42, 0.43, 0.44),   0.55, 0.10)
    m_pier = mat("M_VD_Pier",    (0.36, 0.36, 0.35),   0.68)

    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    n_pier = 0
    n_short = 0                        # piers whose deck_top - ground fell under MIN_PIER_H

    for p in ev:
        pts = [(q[0], q[1]) for q in p["pts"]]
        if len(pts) < 3: continue
        # ---- constant-grade fit: least squares z(t) = zb + grade*(t - tb) --------------
        # The mean of the whole polygon is not a deck, it is a shelf. `tv` is the old
        # `proj` from the pier block, hoisted so the fit and the piers share one axis -
        # a pier centre sits ON that axis, so its own projection IS the loop variable t.
        # The old code dropped the ground samples that missed BEFORE pairing them with a
        # position; the fit needs the pairs, so the filter now keeps (t, z) together.
        ax, ay, cx, cy = SPL.pca(pts)
        tv = [(x-cx)*ax + (y-cy)*ay for x, y in pts]
        fit = [(tv[i], z) for i, z in
               enumerate(gz(x, y) for x, y in pts) if z is not None]
        if not fit: continue                      # fail-closed: was `0.0` per missed ray
        tb = sum(t for t, _ in fit)/len(fit)
        zb = sum(z for _, z in fit)/len(fit)
        den = sum((t-tb)*(t-tb) for t, _ in fit)
        # den ~ 0 only for a polygon with no extent along its own principal axis; the
        # fallback grade of 0 reproduces exactly the old mean-height behaviour.
        grade = (sum((t-tb)*(z-zb) for t, z in fit)/den) if den > 1e-9 else 0.0
        # z(t) is affine in (x, y) -> one tilted plane -> the top n-gon stays planar.
        ztop = [zb + grade*(t-tb) + DECK_CLEARANCE for t in tv]
        print("  deck fit  n=%3d  ground z=%.2f%+.5f*(t-%.1f)  grade %+.2f%%"
              "  deck_top %.1f..%.1f" % (len(pts), zb, grade, tb, 100.0*grade,
                                         min(ztop), max(ztop)), flush=True)

        top = [bm.verts.new((x, y, ztop[i])) for i, (x, y) in enumerate(pts)]
        bot = [bm.verts.new((x, y, ztop[i] - DECK_T)) for i, (x, y) in enumerate(pts)]
        ft = bm.faces.new(top); ft.material_index = 0
        fb = bm.faces.new(list(reversed(bot))); fb.material_index = 0
        for f in (ft, fb):
            for l in f.loops: l[uvl].uv = (0.001, 0.999)
        n = len(pts)
        for i in range(n):                                     # slab edge
            j = (i+1) % n
            f = bm.faces.new((bot[i], bot[j], top[j], top[i])); f.material_index = 0
            for l in f.loops: l[uvl].uv = (0.001, 0.999)
        for i in range(n):                                     # barrier wall
            j = (i+1) % n
            # ztop[k] is read from the same list slot both times it is used, so the two
            # copies of each shared corner stay BITWISE identical and remove_doubles
            # below still collapses exactly n of them per polygon.
            a = bm.verts.new((pts[i][0], pts[i][1], ztop[i] + BARRIER))
            b = bm.verts.new((pts[j][0], pts[j][1], ztop[j] + BARRIER))
            f = bm.faces.new((top[i], top[j], b, a)); f.material_index = 1
            for l in f.loops: l[uvl].uv = (0.001, 0.999)

        # ---- piers down the long axis, only where the deck actually is ----
        # ax/ay/cx/cy and tv come from the grade fit above - same axis, same values.
        t = min(tv) + PIER_STEP*0.5
        while t < max(tv):
            px, py = cx + ax*t, cy + ay*t
            if SPL.inside(pts, px, py):
                g = gz(px, py)
                if g is None:
                    t += PIER_STEP; continue      # no ground -> no pier
                # the pier centre lies on the axis, so its projection is exactly t
                base_z = zb + grade*(t-tb) + DECK_CLEARANCE
                if base_z - g <= MIN_PIER_H:
                    n_short += 1
                    print("  WARN short pier at (%.1f, %.1f)  deck_top=%.2f ground=%.2f"
                          "  h=%.2f m (< %.1f) - deck is nearly on the terrain here"
                          % (px, py, base_z, g, base_z - g, MIN_PIER_H), flush=True)
                lo, hi = [], []
                for k in range(10):
                    a2 = 2*math.pi*k/10
                    ox, oy = PIER_R*math.cos(a2), PIER_R*math.sin(a2)
                    # Evaluate the grade at EACH rim vertex, not once at the pier axis.
                    # The slab underside is a tilted plane now; a flat rim on a 1.5 m radius
                    # at -2.7% is off by +/-0.04 m, so it pokes 4 cm into the slab uphill and
                    # leaves a 4 cm gap downhill - and the pier has no cap face, so that gap
                    # is an open hole into a tube. Costs no extra vertices or faces.
                    ht = (px+ox-cx)*ax + (py+oy-cy)*ay
                    lo.append(bm.verts.new((px+ox, py+oy, g - 0.5)))
                    hi.append(bm.verts.new((px+ox, py+oy,
                                            zb + grade*(ht-tb) + DECK_CLEARANCE - DECK_T)))
                for k in range(10):
                    l2 = (k+1) % 10
                    f = bm.faces.new((lo[k], lo[l2], hi[l2], hi[k])); f.material_index = 2
                    for l in f.loops: l[uvl].uv = (0.001, 0.999)
                n_pier += 1
            t += PIER_STEP

    me = bpy.data.meshes.new("SHIBUYA_VIADUCT")
    # (c) the one builder that was missing this. The barrier ring news 2 verts per edge,
    # so every polygon corner carries a bitwise-identical duplicate: 262 across the three
    # polygons, 1,388 -> 1,126 verts, 1,900 tris unchanged.
    # dist is 0.0001, NOT build_station's 0.001. The merges wanted here are exact
    # duplicates, which any dist > 0 catches, so a larger dist buys nothing - and 79
    # vertices are EXACTLY XY-coincident across two of the elevated polygons (the seam
    # between carriageways), kept apart only by the two polygons' deck heights. 0.0001
    # is also the value that was measured to produce 1,126, and it still leaves 540x
    # headroom under the smallest genuine feature (0.0539 m, poly 1's shortest edge).
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.0001)
    bm.normal_update(); bm.to_mesh(me); bm.free()
    for m in (m_deck, m_bar, m_pier): me.materials.append(m)
    me.shade_flat()
    col = bpy.data.collections.get("MAP_SHIBUYA_VIADUCT")
    if col is None:
        col = bpy.data.collections.new("MAP_SHIBUYA_VIADUCT")
        bpy.context.scene.collection.children.link(col)
    for o in list(col.objects): bpy.data.objects.remove(o, do_unlink=True)
    ob = bpy.data.objects.new("SHIBUYA_VIADUCT", me)
    col.objects.link(ob)
    vs = me.vertices
    print("SHIBUYA_VIADUCT  polys=%d piers=%d(short %d)  verts=%s tris=%s  z %.1f..%.1f"
          % (len(ev), n_pier, n_short, format(len(vs), ','),
             format(sum(len(f.vertices)-2 for f in me.polygons), ','),
             min(v.co.z for v in vs), max(v.co.z for v in vs)), flush=True)
    G.report("viaduct")
    return ob
