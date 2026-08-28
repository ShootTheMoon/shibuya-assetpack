"""Give the re-projected facades a texture that was actually built to repeat.

Completes the chain: fix_facade_uv_density.py established a 12 m box projection over the
532,751 m2 whose PLATEAU photo ran at 5.2 texels/m2, and make_facade_textures.py built
tileable maps at that exact tile. This assigns them.

Finding the affected faces without re-deriving anything: the box projection wrote UV =
world / 12, so those faces carry UV values far outside 0..1, while an original photo UV sits
inside it. A single threshold separates them exactly, with no bookkeeping to go stale.

Variant is chosen from the building's own height, not at random, so a glass tower does not
end up wearing a low-rise panel frontage:

    >= 45 m   A curtain wall
    >= 18 m   B punched office
    <  18 m   C panel commercial
    roofs     D plain concrete   (|normal.z| > 0.7 regardless of height)

The new materials wire the image DIRECTLY into Base Color, so `export_material` picks it up
and OVERDARE gets it too - the same reason the landmark maps in T2 carry and the facade
roughness in enhance_facades.py does not. Roughness and bump are derived in-shader from the
map's own luminance, the recipe enhance_facades.py already uses.
"""
import bpy
import os

TEX = r"C:\Work\blender\ShibuyaAssetPack\03_Textures\BLDG_Facades"
COLLS = ("MAP_SHIBUYA_BUILDINGS", "MAP_SHIBUYA_LANDMARKS")
UV_OUTSIDE = 1.25            # UV magnitude that only the 12 m box projection produces
ROOF_NZ = 0.7

VARIANTS = [("A", "FAC_A_curtainwall.png", 0.20, 0.62),
            ("B", "FAC_B_office.png", 0.26, 0.72),
            ("C", "FAC_C_panel.png", 0.30, 0.76),
            ("D", "FAC_D_concrete.png", 0.55, 0.88)]


def make_mat(key, fname, r_lo, r_hi):
    name = "M_FAC_" + key
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (520, 0)
    b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (240, 0)
    t = nt.nodes.new('ShaderNodeTexImage'); t.location = (-320, 0)
    p = os.path.join(TEX, fname)
    if not os.path.exists(p):
        raise RuntimeError("%s missing - run 03_Textures/make_facade_textures.py first" % p)
    t.image = bpy.data.images.load(p, check_existing=True)
    t.extension = 'REPEAT'
    t.interpolation = 'Linear'
    # DIRECT to Base Color: export_material walks back from here and takes the first
    # TEX_IMAGE, so anything else would ship untextured.
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    bw = nt.nodes.new('ShaderNodeRGBToBW'); bw.location = (-80, -260)
    nt.links.new(t.outputs["Color"], bw.inputs["Color"])
    mr = nt.nodes.new('ShaderNodeMapRange'); mr.location = (100, -260)
    mr.clamp = True
    mr.inputs[1].default_value = 0.05
    mr.inputs[2].default_value = 0.55
    mr.inputs[3].default_value = r_lo
    mr.inputs[4].default_value = r_hi
    nt.links.new(bw.outputs["Val"], mr.inputs[0])
    nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    bp = nt.nodes.new('ShaderNodeBump'); bp.location = (100, -480)
    bp.inputs["Strength"].default_value = 0.35
    bp.inputs["Distance"].default_value = 0.04
    nt.links.new(bw.outputs["Val"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Metallic"].default_value = 0.0
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def run():
    mats = {k: make_mat(k, f, lo, hi) for k, f, lo, hi in VARIANTS}
    n_face = n_obj = 0
    per = {k: 0 for k in mats}
    for cn in COLLS:
        c = bpy.data.collections.get(cn)
        if c is None:
            continue
        for o in c.objects:
            if o.type != 'MESH' or not o.data.polygons or not o.data.uv_layers:
                continue
            me = o.data
            uvl = me.uv_layers[0].data
            zs = [ (o.matrix_world @ v.co).z for v in me.vertices ]
            h = max(zs) - min(zs)
            wall_key = "A" if h >= 45.0 else ("B" if h >= 18.0 else "C")
            slot = {}
            hit = False
            for p in me.polygons:
                mx = 0.0
                for li in p.loop_indices:
                    uv = uvl[li].uv
                    mx = max(mx, abs(uv[0]), abs(uv[1]))
                if mx <= UV_OUTSIDE:
                    continue                      # a real, well-registered photo UV
                nrm = p.normal.copy()
                nrm.rotate(o.matrix_world.to_quaternion())
                key = "D" if abs(nrm.z) > ROOF_NZ else wall_key
                if key not in slot:
                    me.materials.append(mats[key])
                    slot[key] = len(me.materials) - 1
                p.material_index = slot[key]
                per[key] += 1
                n_face += 1
                hit = True
            if hit:
                n_obj += 1
    print("  facade swap: %d faces on %d objects" % (n_face, n_obj))
    for k, f, lo, hi in VARIANTS:
        print("     %s %-22s %6d faces   rough %.2f..%.2f" % (k, f, per[k], lo, hi))
    return n_face


if globals().get("__name__") == "__main__":
    run()
    print("FACADE SWAP APPLIED")
