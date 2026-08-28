"""Re-project the facades whose texture is stretched past legibility. ZERO triangles.

Measured, after two wrong attributions for the same symptom: the "chrome ironwork" in the
mid-distance render is not a reflection and not a roughness error. It is a facade photo
smeared across a surface far too large for it.

    shib0004   214,119 m2   texel density p50 0.00002 uv2/m2   anisotropy p50 2.1, max 7970

At 512 px that density is 5.2 texels per SQUARE METRE - one texel every 0.44 m. Nothing
survives that; the photo becomes vertical streaks, and streaks of a bright sky read as
polished metal. The largest single consumer is LM_Stream at 50,127 m2.

The fix trades a correctly-placed but unreadable photo for a tiled but legible one: faces
below the threshold get a world-space box projection at TILE_M metres per repeat, and the
texture node is switched to REPEAT so it tiles instead of clamping.

This one DOES reach OVERDARE, unlike the roughness and bump in enhance_facades.py - UVs
travel with the mesh and the image is unchanged, so the delivered FBX gets the same gain.

Deliberately conservative: only faces measurably below the threshold move. A facade whose
photo is correctly registered at a usable density is left exactly as it is, because tiling
would destroy real placement to fix nothing.
"""
import bpy
import math

from mathutils import Vector

MIN_TEXELS_PER_M2 = 40.0     # below this a 512 px photo is mush; 40 -> 0.16 m per texel
TILE_M = 12.0                # metres per UV repeat after re-projection
COLLS = ("MAP_SHIBUYA_BUILDINGS", "MAP_SHIBUYA_LANDMARKS")


def tex_of(mat):
    if not mat or not mat.use_nodes:
        return None
    best = None
    for n in mat.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image and "FacadeDetail" not in n.image.name:
            if best is None or max(n.image.size) > max(best.image.size):
                best = n
    return best


def face_area(o, p):
    M = o.matrix_world
    vs = [M @ o.data.vertices[i].co for i in p.vertices]
    a = 0.0
    for k in range(1, len(vs)-1):
        a += (vs[k]-vs[0]).cross(vs[k+1]-vs[0]).length * 0.5
    return a, vs


def uv_area(uvl, p):
    uv = [Vector(uvl[li].uv) for li in p.loop_indices]
    a = 0.0
    for k in range(1, len(uv)-1):
        a += abs((uv[k]-uv[0]).cross(uv[k+1]-uv[0])) * 0.5
    return a


def run():
    n_obj = n_face = 0
    moved_area = kept_area = 0.0
    touched_tex = set()
    for cn in COLLS:
        c = bpy.data.collections.get(cn)
        if c is None:
            continue
        for o in c.objects:
            if o.type != 'MESH' or not o.data.polygons or not o.data.uv_layers:
                continue
            me = o.data
            uvl = me.uv_layers[0].data
            mats = list(me.materials)
            px = {}
            for i, m in enumerate(mats):
                t = tex_of(m)
                px[i] = (max(t.image.size) if t else 0, t)
            hit = False
            for p in me.polygons:
                size, tnode = px.get(p.material_index, (0, None))
                if not size:
                    continue
                aw, vs = face_area(o, p)
                if aw < 1e-6:
                    continue
                au = uv_area(uvl, p)
                texels = (size * size) * (au / aw)
                if texels >= MIN_TEXELS_PER_M2:
                    kept_area += aw
                    continue
                # ---- world box projection, dominant axis of the face normal ----
                nrm = p.normal.copy()
                nrm.rotate(o.matrix_world.to_quaternion())
                ax, ay, az = abs(nrm.x), abs(nrm.y), abs(nrm.z)
                for li, vi in zip(p.loop_indices, p.vertices):
                    w = o.matrix_world @ me.vertices[vi].co
                    if az >= ax and az >= ay:
                        u, v = w.x, w.y          # roof: plan projection
                    elif ax >= ay:
                        u, v = w.y, w.z          # wall facing X
                    else:
                        u, v = w.x, w.z          # wall facing Y
                    uvl[li].uv = (u / TILE_M, v / TILE_M)
                if tnode is not None:
                    tnode.extension = 'REPEAT'
                    touched_tex.add(tnode.image.name)
                moved_area += aw
                n_face += 1
                hit = True
            if hit:
                n_obj += 1
    tot = moved_area + kept_area
    print("  UV density: re-projected %d faces on %d objects" % (n_face, n_obj))
    print("     area moved  %s m2 (%.1f%% of textured facade area)"
          % (format(int(moved_area), ','), 100.0*moved_area/max(tot, 1.0)))
    print("     area kept   %s m2 - already at or above %.0f texels/m2"
          % (format(int(kept_area), ','), MIN_TEXELS_PER_M2))
    print("     tile %.1f m per repeat; %d textures switched to REPEAT" % (TILE_M, len(touched_tex)))
    return n_face


if globals().get("__name__") == "__main__":
    run()
    print("FACADE UV DENSITY FIXED")
