"""Split SHIBUYA_GROUND into tiles, each with its own cropped image. ZERO triangles.

The delivered terrain runs at 0.6 texels/m2 - one texel per 1.26 metres - across 3,501,247
m2. Buildings ship at 707, the instance masters at 92,043. It is the single worst number in
the delivery and it covers 31.6% of an eye-level frame and 59.1% of an aerial.

The cause is structural, not a missing texture. The ground carries ONE planar UV over the
whole 640 m survey square, and `prep_image` caps every delivered image at 512 px, so the
8192 bake that exists on disk arrives as 512 px spread over 640 m:

    512^2 / 640^2 = 0.64 texels/m2

No shader change reaches it - OVERDARE takes one image per MeshPart. The only lever is to
give each piece of ground its own image, so this cuts the ground into a grid and crops the
source bake per tile. A tile covering 107 m at 512 px carries 22.9 texels/m2; the same tile
whitelisted to 1024 carries 91.7.

Outside the +-320 m survey square the source is the outskirts bake at 0.454 m/px, so tiles
out there are made larger - there is no detail to recover, and a tile per 107 m would just
ship 36 copies of the same blur.

The crops are written by 03_Textures/make_ground_tiles.py (PIL, system Python) because
img.copy()+img.scale() inside Blender crashed this pipeline once and hung it for 1h48m once.
"""
import bpy
import bmesh
import os
import sys

from mathutils import Vector

TILES = r"C:\Work\blender\Shibuya\bake\ground_tiles"
BAKE = r"C:\Work\blender\Shibuya\bake"
if BAKE not in sys.path:
    sys.path.insert(0, BAKE)
SRC = "SHIBUYA_GROUND"


def run():
    src = bpy.data.objects.get(SRC)
    if src is None:
        print("  !! %s missing" % SRC)
        return 0
    if not os.path.isdir(TILES):
        print("  !! %s missing - run 03_Textures/make_ground_tiles.py first" % TILES)
        return 0

    # the lattice comes from ground_tiles_layout.py, the same module
    # make_ground_tiles.py cropped from. Recomputing it here is how a misregistered
    # ground would happen.
    from ground_tiles_layout import cells as _cells
    lookup = _cells()

    col = None
    for c in src.users_collection:
        col = c
        break
    if col is None:
        col = bpy.context.scene.collection

    # one bmesh per cell, faces assigned by centroid so no triangle is split or duplicated
    me = src.data
    M = src.matrix_world
    bms = {}
    mats = {}
    n_face = 0
    for cid in (c[4] for c in lookup):
        bms[cid] = bmesh.new()
    for p in me.polygons:
        vs = [M @ me.vertices[i].co for i in p.vertices]
        cx = sum(v.x for v in vs) / len(vs)
        cy = sum(v.y for v in vs) / len(vs)
        cid = None
        for x0, y0, x1, y1, k in lookup:
            if x0 <= cx < x1 and y0 <= cy < y1:
                cid = k
                break
        if cid is None:
            continue
        bm = bms[cid]
        uvl = bm.loops.layers.uv.verify()
        f = bm.faces.new([bm.verts.new(tuple(v)) for v in vs])
        # UV 0..1 over the tile's own crop - this is the whole point
        box = next(c for c in lookup if c[4] == cid)
        for lp, v in zip(f.loops, vs):
            lp[uvl].uv = ((v.x - box[0]) / (box[2] - box[0]),
                          (v.y - box[1]) / (box[3] - box[1]))
        n_face += 1

    made = 0
    for x0, y0, x1, y1, cid in lookup:
        bm = bms[cid]
        if not bm.faces:
            bm.free()
            continue
        png = os.path.join(TILES, "GT_%s.png" % cid)
        if not os.path.exists(png):
            bm.free()
            continue
        nme = bpy.data.meshes.new("GROUND_%s" % cid)
        bm.normal_update()
        bm.to_mesh(nme)
        bm.free()
        m = bpy.data.materials.get("M_GT_%s" % cid)
        if m is None:
            m = bpy.data.materials.new("M_GT_%s" % cid)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (400, 0)
        b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (150, 0)
        t = nt.nodes.new('ShaderNodeTexImage'); t.location = (-250, 0)
        t.image = bpy.data.images.load(png, check_existing=True)
        t.extension = 'EXTEND'
        t.interpolation = 'Cubic'
        nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.82
        b.inputs["Metallic"].default_value = 0.0
        nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
        nme.materials.append(m)
        nme.shade_flat()
        ob = bpy.data.objects.new(nme.name, nme)
        col.objects.link(ob)
        mats[cid] = m
        made += 1

    if made:
        bpy.data.objects.remove(src, do_unlink=True)
    print("  ground retiled: %d tiles from %d faces (lattice from ground_tiles_layout)"
          % (made, n_face))
    return made


if globals().get("__name__") == "__main__":
    run()
    print("GROUND RETILED")
