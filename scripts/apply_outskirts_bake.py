"""Point SHIBUYA_GROUND's radial fade at the outskirts bake instead of at asphalt.

Measured problem: SHIBUYA_GROUND runs to +-929 m but the surveyed bake covers only the
+-320 m crop, so 3,080,100 m2 - 88.1% of the ground - falls outside UV 0..1 on an EXTEND
sampler. The material already had a radial fade to hand over out there, but its target was
`aerial_asphalt_01_Diffuse` tiled at 0.021, i.e. the city sat in a 900 m plain of grey
tarmac. rasterise_outskirts.py now produces a proper 4096 map over the full extent.

Nothing here is new machinery. The existing graph already has everything:

    FADE_tc.Object -> FADE_sep -> abs(X), abs(Y) -> FADE_max        (Chebyshev radius)
    FADE_max -> FADE_range (318..430 -> 0..1) -> FADE_mix.Factor
                                              -> FADE_rough.Factor
    FADE_tc.Object -> FADE_map(scale 0.021) -> FADE_tex -> FADE_dark -> FADE_mix.B
    DET_mix.Result (inner bake) -> FADE_mix.A

So this only ever RETARGETS: swap the image, fix the mapping so the bake lands 1:1 over the
ground instead of tiling, move the handover inward, and connect the roughness B input -
which was never linked at all, so past the fade the ground took FADE_rough's default value
rather than any measured roughness.

Handover moves 318..430 -> 300..380 on purpose: it has to complete INSIDE the surveyed
crop's outer margin, where there is almost no real content to lose, rather than out at 430
where the inner bake has nothing left to show but clamped edge texels.
"""
import bpy
import os

BAKE = r"C:\Work\blender\Shibuya\bake"
ALB = os.path.join(BAKE, "outskirts_albedo.png")
RGH = os.path.join(BAKE, "outskirts_rough.png")
HALF = 930.0                      # must match rasterise_outskirts.HALF
FADE_LO, FADE_HI = 300.0, 380.0
MAT = "M_SHIBUYA_GROUNDBAKE"


def run():
    m = bpy.data.materials.get(MAT)
    if m is None or not m.use_nodes:
        print("  !! %s not found" % MAT)
        return 0
    nt = m.node_tree
    for p in (ALB, RGH):
        if not os.path.exists(p):
            print("  !! %s missing - run Shibuya/bake/rasterise_outskirts.py first" % p)
            return 0
    alb = bpy.data.images.load(ALB, check_existing=True)
    rgh = bpy.data.images.load(RGH, check_existing=True)
    try:
        rgh.colorspace_settings.name = 'Non-Color'
    except Exception:
        pass

    n = {x.name: x for x in nt.nodes}
    need = ("FADE_map", "FADE_tex", "FADE_range", "FADE_mix", "FADE_rough", "FADE_dark")
    missing = [k for k in need if k not in n]
    if missing:
        print("  !! the fade chain is not the expected shape, missing %s" % missing)
        return 0

    # ---- 1. map Object coords so the bake lands 1:1 over the ground ----
    # Object coords ARE world metres here (the anchor offset is baked into the mesh and the
    # object sits at the origin). Mapping is scale-then-location, so -930 -> -0.5 -> 0.0
    # and +930 -> +0.5 -> 1.0.
    mp = n["FADE_map"]
    mp.inputs["Scale"].default_value = (1.0/(2*HALF), 1.0/(2*HALF), 1.0)
    mp.inputs["Location"].default_value = (0.5, 0.5, 0.0)

    # ---- 2. retarget the albedo ----
    t = n["FADE_tex"]
    old = t.image.name if t.image else "-"
    t.image = alb
    t.extension = 'EXTEND'      # it already covers the whole ground; REPEAT would wrap at +-930
    t.interpolation = 'Cubic'

    # ---- 3. FADE_dark was tinting the asphalt down. The new map is already tone-matched
    # to the inner bake (mean 74.9 vs 72.0, luminance p90 136 vs 136), so any extra tint
    # would reintroduce the very ring this is meant to remove.
    fd = n["FADE_dark"]
    if "Factor" in fd.inputs:
        fd.inputs["Factor"].default_value = 0.0

    # ---- 4. move the handover inward ----
    fr = n["FADE_range"]
    lo_was = fr.inputs[1].default_value
    hi_was = fr.inputs[2].default_value
    fr.inputs[1].default_value = FADE_LO
    fr.inputs[2].default_value = FADE_HI

    # ---- 5. roughness: B was never connected ----
    rt = nt.nodes.get("FADE_rough_tex")
    if rt is None:
        rt = nt.nodes.new('ShaderNodeTexImage')
        rt.name = rt.label = "FADE_rough_tex"
        rt.location = (-900, -320)
    rt.image = rgh
    rt.extension = 'EXTEND'
    rt.interpolation = 'Cubic'
    try:
        rt.image.colorspace_settings.name = 'Non-Color'
    except Exception:
        pass
    nt.links.new(mp.outputs["Vector"], rt.inputs["Vector"])
    frn = n["FADE_rough"]
    b_in = frn.inputs[7] if len(frn.inputs) > 7 else frn.inputs["B"]
    nt.links.new(rt.outputs["Color"], b_in)

    print("  %s retargeted:" % MAT)
    print("     albedo   %s -> %s (%dx%d, EXTEND)" % (old, alb.name, alb.size[0], alb.size[1]))
    print("     rough    (B was UNLINKED) -> %s" % rgh.name)
    print("     mapping  scale -> %.6f, location 0.5  (world +-%.0f m -> UV 0..1)"
          % (1.0/(2*HALF), HALF))
    print("     fade     %.0f..%.0f -> %.0f..%.0f m" % (lo_was, hi_was, FADE_LO, FADE_HI))
    print("     FADE_dark factor -> 0.0 (the new map is already tone-matched)")
    return 1


if globals().get("__name__") == "__main__":
    run()
    print("OUTSKIRTS BAKE APPLIED")
