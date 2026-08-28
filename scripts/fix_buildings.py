"""Repair the mechanical building defects the audit classified.

Four fixes, all measured before and after by audit_buildings.py:

  [N] inverted normals   flip faces whose outward step lands INSIDE the solid. The test is
                         the strict one - the cheap "normal points at the centroid" version
                         overstated this 4.0x (10.9% vs 2.7%) because on an L-shaped or
                         courtyard building plenty of correct faces point back at the
                         centroid.
  [Z] degenerate faces   delete zero-area faces; they only ever produce shading artefacts.
  [U] degenerate UVs     box-project the faces whose UV area collapses to a point. Those
                         faces sample a single texel and render as a flat smear. Reuses the
                         world-space box projection written for the utility pole.
  [S] slivers            a 3-triangle, 2.7 x 3.3 x 13.8 m "building" is import debris, not
                         a building. Removed, and any other object under 4 faces with it.

Roofless buildings are REPORTED, not patched: capping an open top needs a real boundary
loop, and 5 of 598 that are only visible from the air is not worth a fragile auto-cap.
"""
import bpy
import bmesh
import math
import os
import sys

from mathutils import Vector

_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)
import shibuya_placement_lib as SPL

# The normal flip is OFF by default, and this is a measured verdict.
#
# It was added on the theory that inverted normals are why some buildings read black. That
# theory is WRONG: EEVEE renders both sides of a face, so an A/B of the same building before
# and after flipping 3,197 faces is pixel-identical. The dark buildings are dark because
# their PLATEAU photo is dark - an aerial shot of a glass tower - not because of winding.
#
# And the test cannot be trusted here anyway. in_building() uses odd-crossing parity, which
# assumes a closed solid, but strip_building_floors.py deleted every building's bottom face
# to stop it showing through the ground. On an open mesh parity is unreliable, which is why
# this flagged 339 of 598 buildings when the strict area measurement found 15.
#
# So: no visual benefit, an unvalidated test, and a real downside - a wrongly flipped face
# disappears in any engine that backface-culls, which OVERDARE may. Off unless someone
# validates it with a test that does not assume closure.
FLIP_NORMALS = False

EPS = 0.06
AREA_MIN = 1e-5
UV_DEGEN = 1e-7
BOX_TILE = 6.0        # metres per UV unit for the re-projected faces
MIN_FACES = 4


def box_uv_faces(me, faces, tile=BOX_TILE):
    """world-space box projection for selected faces only"""
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uvl = me.uv_layers[0].uv
    for p in faces:
        n = p.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            if ax == 0:
                u, w = co.y, co.z
            elif ax == 1:
                u, w = co.x, co.z
            else:
                u, w = co.x, co.y
            uvl[li].vector = ((u/tile) % 1.0, (w/tile) % 1.0)


def uv_area(me, p):
    uvl = me.uv_layers[0].uv
    li = list(p.loop_indices)
    uv = [uvl[k].vector for k in li]
    a = 0.0
    for k in range(len(uv)):
        x1, y1 = uv[k]
        x2, y2 = uv[(k+1) % len(uv)]
        a += x1*y2 - x2*y1
    return abs(a)*0.5


def run(coll="MAP_SHIBUYA_BUILDINGS"):
    c = bpy.data.collections.get(coll)
    if c is None:
        print("no collection", coll); return
    objs = [o for o in c.objects if o.type == 'MESH' and o.data.polygons]
    n_flip = n_flip_ob = 0
    n_zero = n_zero_ob = 0
    n_uv = n_uv_ob = 0
    removed = []
    roofless = []

    for ob in list(objs):
        me = ob.data
        # ---- [S] import debris ----
        if len(me.polygons) < MIN_FACES:
            removed.append((ob.name, len(me.polygons)))
            bpy.data.objects.remove(ob, do_unlink=True)
            continue

        # ---- [N] flip genuinely inverted faces (default OFF - see FLIP_NORMALS) ----
        bad = []
        if FLIP_NORMALS:
            bvh, _ = SPL.make_bvh([ob])
            for p in me.polygons:
                if p.area < AREA_MIN:
                    continue
                q = p.center + p.normal*EPS
                if SPL.in_building(bvh, q.x, q.y, q.z):
                    bad.append(p.index)
        if bad:
            bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
            sel = [bm.faces[i] for i in bad if i < len(bm.faces)]
            bmesh.ops.reverse_faces(bm, faces=sel)
            bm.to_mesh(me); bm.free()
            n_flip += len(bad); n_flip_ob += 1

        # ---- [Z] zero-area faces ----
        bm = bmesh.new(); bm.from_mesh(me)
        kill = [f for f in bm.faces if f.calc_area() < AREA_MIN]
        if kill:
            bmesh.ops.delete(bm, geom=kill, context='FACES')
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces],
                             context='VERTS')
            bm.to_mesh(me)
            n_zero += len(kill); n_zero_ob += 1
        bm.free()

        # ---- [U] faces whose UVs collapse ----
        if me.uv_layers:
            degen = [p for p in me.polygons
                     if p.area >= AREA_MIN and uv_area(me, p) < UV_DEGEN]
            if degen:
                box_uv_faces(me, degen)
                n_uv += len(degen); n_uv_ob += 1

        # ---- [R] report only ----
        vs = me.vertices
        if vs:
            zmax = max(v.co.z for v in vs); zmin = min(v.co.z for v in vs)
            band = zmax - (zmax-zmin)*0.15
            if not any(p.normal.z > 0.55 and p.center.z >= band for p in me.polygons):
                roofless.append(ob.name)

    print("  [N] flipped %s face(s) on %d building(s)%s"
          % (format(n_flip, ','), n_flip_ob,
             "" if FLIP_NORMALS else "   (FLIP_NORMALS is off - no visual effect, "
                                     "and the parity test is invalid on open meshes)"))
    print("  [Z] deleted %s zero-area face(s) on %d building(s)"
          % (format(n_zero, ','), n_zero_ob))
    print("  [U] re-projected %s face(s) on %d building(s)" % (format(n_uv, ','), n_uv_ob))
    print("  [S] removed %d import-debris object(s): %s" % (len(removed), removed))
    print("  [R] roofless (reported, NOT patched - see the docstring): %d %s"
          % (len(roofless), roofless[:6]))
    return dict(flip=n_flip, zero=n_zero, uv=n_uv, removed=removed, roofless=roofless)


if globals().get("__name__") == "__main__":
    run()
    print("FIX BUILDINGS DONE")
