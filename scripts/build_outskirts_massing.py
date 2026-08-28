"""Give the outskirts a silhouette. Beyond +-320 m the map is a painted plan with no mass.

T1 replaced 3.08 million m2 of grey asphalt with a synthetic aerial bake, and the seam is
invisible - but the final aerial still reads as "a model standing on a printed map", because
everything past the crop boundary is perfectly flat. The bake draws blocks and streets; this
puts buildings on the blocks.

REGISTRATION IS THE WHOLE PROBLEM. A box that lands on a painted road looks worse than no
box at all, so the street grid is not re-invented here - `grid_lines` and `jitter` are
imported from rasterise_outskirts.py and called with the SAME spacings and the SAME seed.
The block a mass sits in is the block the texture painted.

    local streets   58.0 m (x, SEED)      62.0 m (y, SEED+1)
    collectors     165.0 m (SEED+2)      180.0 m (SEED+3)
    arterials      430.0 m (SEED+4)      470.0 m (SEED+5)

Nothing here claims to be real Tokyo. It is massing for a horizon, documented as synthetic
in the same terms T1 was.

Cost is negligible: a mass is a 12-triangle box, so even 2,500 of them is 30,000 triangles
against a 4.24 M scene. Meshes are chunked to stay under the 30,000/mesh OVERDARE cap.
"""
import bpy
import bmesh
import math
import os
import sys

from mathutils import Vector
from mathutils.bvhtree import BVHTree

BAKE = r"C:\Work\blender\Shibuya\bake"
if BAKE not in sys.path:
    sys.path.insert(0, BAKE)

COLL = "MAP_SHIBUYA_OUTSKIRTS"
CORE = 335.0            # Chebyshev half-extent of the real, surveyed city - never build inside
EDGE = 900.0            # stop short of the ground's +-929 m rim so nothing overhangs
ROAD_CLEAR = 7.0        # inset from a block edge, so a wall never sits on painted tarmac
MIN_FOOT = 14.0         # a block too thin to hold this after the inset is left open
EMPTY_RATE = 0.22       # blocks left as parks / yards / car parks
MAX_TRIS_PER_MESH = 24000


def _rnd(i, j, salt):
    """deterministic 0..1 - the whole layout must survive a rebuild unchanged"""
    h = (i * 73856093) ^ (j * 19349663) ^ (salt * 83492791)
    h &= 0x7FFFFFFF
    h = (h ^ (h >> 13)) * 1274126177
    return ((h ^ (h >> 16)) & 0xFFFFFF) / float(0xFFFFFF)


def _height(i, j, r):
    """Tokyo away from a hub: mostly low-rise, a scatter of mid-rise, rare towers.

    Tapered with distance so the horizon sits down rather than walling the shot in - which
    is also what a real city does around a station district.
    """
    t = _rnd(i, j, 5)
    far = min(1.0, max(0.0, (r - CORE) / (EDGE - CORE)))
    if t > 0.975:
        h = 62.0 + 48.0 * _rnd(i, j, 6)
    elif t > 0.88:
        h = 30.0 + 26.0 * _rnd(i, j, 7)
    elif t > 0.55:
        h = 16.0 + 13.0 * _rnd(i, j, 8)
    else:
        h = 8.0 + 8.0 * _rnd(i, j, 9)
    return h * (1.0 - 0.42 * far)


def _ground_bvh():
    g = bpy.data.objects.get("SHIBUYA_GROUND")
    if g is None:
        return None
    M = g.matrix_world
    vs = [M @ v.co for v in g.data.vertices]
    tris = []
    for p in g.data.polygons:
        idx = list(p.vertices)
        for k in range(1, len(idx) - 1):
            tris.append((idx[0], idx[k], idx[k + 1]))
    return BVHTree.FromPolygons([tuple(v) for v in vs], tris)


def _far_materials():
    """M_OUT_* - the M_FAC_* graphs pointed at the darker *_far.png images.

    Measured: at the authored tone the massing rendered 1.35x brighter than the photo core
    (band means 0.441 vs 0.328) and read as a styrofoam model ringing a photographed city.
    The correction lives in the image, not in a shader tint, because export_material rebuilds
    every material as a bare TEX_IMAGE -> Base Color - a tint would look right here and ship
    wrong. Copying the material keeps the roughness ramp and bump that apply_facade_swap
    tuned per variant.
    """
    out = []
    for key in ("M_FAC_C", "M_FAC_B", "M_FAC_A", "M_FAC_D"):
        src = bpy.data.materials.get(key)
        if src is None:
            continue
        name = key.replace("M_FAC_", "M_OUT_")
        m = bpy.data.materials.get(name)
        if m is None:
            m = src.copy()
            m.name = name
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image and "_far" not in n.image.name:
                p = bpy.path.abspath(n.image.filepath)
                far = p.replace(".png", "_far.png")
                if os.path.exists(far):
                    n.image = bpy.data.images.load(far, check_existing=True)
                    n.extension = 'REPEAT'
        out.append(m)
    return out


def run():
    # outskirts_grid.py, not rasterise_outskirts.py: the rasteriser imports numpy and
    # PIL at module level and Blender's Python has neither. Both read the same file.
    from outskirts_grid import grid_lines, SEED

    bvh = _ground_bvh()
    if bvh is None:
        print("  !! SHIBUYA_GROUND missing - cannot sit the massing on the ground")
        return 0

    def gz(x, y):
        r = bvh.ray_cast(Vector((x, y, 600.0)), Vector((0.0, 0.0, -1.0)), 1200.0)
        return r[0].z if r[0] else None

    xs = sorted(grid_lines(58.0, 12.0, SEED))
    ys = sorted(grid_lines(62.0, 12.0, SEED + 1))

    col = bpy.data.collections.get(COLL)
    if col is None:
        col = bpy.data.collections.new(COLL)
        bpy.context.scene.collection.children.link(col)
    for o in list(col.objects):
        bpy.data.objects.remove(o, do_unlink=True)

    mats = _far_materials()
    if not mats:
        print("  !! no M_FAC_* materials - run apply_facade_swap.py first")
        return 0
    roof_i = len(mats) - 1

    chunks = []
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.verify()
    n_box = n_open = n_miss = 0
    tris = 0

    def flush():
        # bmesh.new() invalidates the previous layer handle, so uvl has to be re-verified
        # here rather than once at the top - a stale handle writes into freed memory.
        nonlocal bm, tris, uvl
        if not bm.faces:
            bm.free()
            bm = bmesh.new()
            uvl = bm.loops.layers.uv.verify()
            return
        me = bpy.data.meshes.new("OUTSKIRTS_%02d" % len(chunks))
        bm.normal_update()
        bm.to_mesh(me)
        bm.free()
        for m in mats:
            me.materials.append(m)
        me.shade_flat()
        ob = bpy.data.objects.new(me.name, me)
        col.objects.link(ob)
        chunks.append(ob)
        bm = bmesh.new()
        uvl = bm.loops.layers.uv.verify()
        tris = 0

    def box(x0, y0, x1, y1, z0, z1, wall_mi):
        """axis-aligned mass, world-scale box UV at 12 m so M_FAC_* tiles correctly"""
        nonlocal tris
        c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for k in range(4):
            ax, ay = c[k]
            bx, by = c[(k + 1) % 4]
            f = bm.faces.new([bm.verts.new(p) for p in
                              ((ax, ay, z0), (bx, by, z0), (bx, by, z1), (ax, ay, z1))])
            f.material_index = wall_mi
            horiz = math.hypot(bx - ax, by - ay)
            for lp, (u, v) in zip(f.loops, ((0.0, z0), (horiz, z0), (horiz, z1), (0.0, z1))):
                lp[uvl].uv = (u / 12.0, v / 12.0)
            tris += 2
        f = bm.faces.new([bm.verts.new((p[0], p[1], z1)) for p in c])
        f.material_index = roof_i
        for lp, p in zip(f.loops, c):
            lp[uvl].uv = (p[0] / 12.0, p[1] / 12.0)
        tris += 2

    for i in range(len(xs) - 1):
        bx0, bx1 = xs[i], xs[i + 1]
        for j in range(len(ys) - 1):
            by0, by1 = ys[j], ys[j + 1]
            cx, cy = (bx0 + bx1) * 0.5, (by0 + by1) * 0.5
            r = max(abs(cx), abs(cy))
            if r < CORE or r > EDGE:
                continue
            if _rnd(i, j, 1) < EMPTY_RATE:
                n_open += 1
                continue
            x0, x1 = bx0 + ROAD_CLEAR, bx1 - ROAD_CLEAR
            y0, y1 = by0 + ROAD_CLEAR, by1 - ROAD_CLEAR
            if x1 - x0 < MIN_FOOT or y1 - y0 < MIN_FOOT:
                n_open += 1
                continue
            # split the block into 1, 2 or 4 plots so the footprints are not all identical
            nx = 2 if (x1 - x0) > 34.0 and _rnd(i, j, 2) > 0.45 else 1
            ny = 2 if (y1 - y0) > 34.0 and _rnd(i, j, 3) > 0.45 else 1
            for a in range(nx):
                for b in range(ny):
                    px0 = x0 + (x1 - x0) * a / nx
                    px1 = x0 + (x1 - x0) * (a + 1) / nx
                    py0 = y0 + (y1 - y0) * b / ny
                    py1 = y0 + (y1 - y0) * (b + 1) / ny
                    if nx > 1:
                        px0 += 1.2
                        px1 -= 1.2
                    if ny > 1:
                        py0 += 1.2
                        py1 -= 1.2
                    if px1 - px0 < 8.0 or py1 - py0 < 8.0:
                        continue
                    salt = 40 + a * 3 + b
                    z = gz((px0 + px1) * 0.5, (py0 + py1) * 0.5)
                    if z is None:
                        n_miss += 1
                        continue
                    h = _height(i * 7 + a, j * 7 + b, r)
                    wall = 2 if h >= 45.0 else (1 if h >= 18.0 else 0)
                    wall = min(wall, len(mats) - 1)
                    box(px0, py0, px1, py1, z - 0.5, z + h, wall)
                    n_box += 1
                    if tris >= MAX_TRIS_PER_MESH:
                        flush()
    flush()

    total = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in chunks)
    print("  outskirts massing: %d masses in %d meshes, %s tris"
          % (n_box, len(chunks), format(total, ',')))
    print("     blocks left open %d | ground probe misses %d (expected 0)" % (n_open, n_miss))
    print("     grid reused from rasterise_outskirts: local 58.0/62.0 m, seed %d" % SEED)
    print("     ring %.0f..%.0f m, road inset %.1f m" % (CORE, EDGE, ROAD_CLEAR))
    return n_box


if globals().get("__name__") == "__main__":
    run()
    print("OUTSKIRTS MASSING BUILT")
