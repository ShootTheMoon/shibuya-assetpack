"""Wire the close-range asphalt detail into M_SHIBUYA_GROUNDBAKE.

Ground is 31.6% of an eye-level frame and 59.1% of an aerial - the largest category by a
wide margin. Two measured gaps, both fixed here for ZERO triangles:

  * the Principled `Normal` input was UNCONNECTED, so the road had no aggregate at all
  * the only albedo detail was an AERIAL asphalt photo on a 25 m repeat, which is a single
    tile across the whole visible road at eye level

The existing graph is retargeted, not rebuilt. It already carries:

    DET_uv -> DET_map(25.6) -> DET_tex -> DET_mix(OVERLAY 0.40) <- 8192 bake
    DET_mix -> FADE_mix.A -> Principled.Base Color
    8192 rough -> FADE_rough.A -> Principled.Roughness

so this inserts a second detail stage between DET_mix and FADE_mix, and connects a Normal
Map node that had no counterpart before.

Placement is deliberate: the grain goes on the INNER path (before FADE_mix), so the
outskirts bake keeps the tone it was matched to in T1. The normal is global - 4 m aggregate
is invisible at outskirts distance either way, and gating it would cost a node for nothing.
"""
import bpy
import os

TEX = r"C:\Work\blender\ShibuyaAssetPack\03_Textures\GR_Ground_Detail"
TILE_M = 4.0                # must match make_ground_detail.TILE_M
SPAN_M = 640.0              # the planar UV maps x,y in +-320 m onto 0..1
MAT = "M_SHIBUYA_GROUNDBAKE"
GRAIN_FAC = 0.55            # OVERLAY; the map is centred on 0.5 so the mean does not move
NORMAL_STR = 0.45
ROUGH_FAC = 0.40


def _img(nt, name, fname, non_color, uv_node, loc):
    n = nt.nodes.get(name)
    if n is None:
        n = nt.nodes.new('ShaderNodeTexImage')
        n.name = n.label = name
        n.location = loc
    p = os.path.join(TEX, fname)
    if not os.path.exists(p):
        raise RuntimeError("%s missing - run 03_Textures/make_ground_detail.py first" % p)
    n.image = bpy.data.images.load(p, check_existing=True)
    n.extension = 'REPEAT'
    n.interpolation = 'Linear'
    if non_color:
        n.image.colorspace_settings.name = 'Non-Color'
    nt.links.new(uv_node.outputs["Vector"], n.inputs["Vector"])
    return n


def run():
    m = bpy.data.materials.get(MAT)
    if m is None or not m.use_nodes:
        print("  !! %s not found" % MAT)
        return 0
    nt = m.node_tree
    n = {x.name: x for x in nt.nodes}
    need = ("DET_uv", "DET_mix", "FADE_mix", "FADE_rough")
    missing = [k for k in need if k not in n]
    if missing:
        print("  !! ground graph is not the expected shape, missing %s" % missing)
        return 0
    bsdf = next((x for x in nt.nodes if x.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        print("  !! no Principled BSDF")
        return 0

    reps = SPAN_M / TILE_M                     # 160 repeats across the planar UV
    mp = nt.nodes.get("DET2_map")
    if mp is None:
        mp = nt.nodes.new('ShaderNodeMapping')
        mp.name = mp.label = "DET2_map"
        mp.location = (-1100, -640)
    mp.inputs["Scale"].default_value = (reps, reps, 1.0)
    nt.links.new(n["DET_uv"].outputs["UV"], mp.inputs["Vector"])

    grain = _img(nt, "DET2_grain", "GR_Asphalt_grain.png", False, mp, (-880, -520))
    nrm_t = _img(nt, "DET2_normal", "GR_Asphalt_normal.png", True, mp, (-880, -760))
    rgh_t = _img(nt, "DET2_rough", "GR_Asphalt_rough.png", True, mp, (-880, -1000))

    # ---- 1. grain OVERLAY on the inner albedo, before the outskirts handover ----
    gm = nt.nodes.get("DET2_mix")
    if gm is None:
        gm = nt.nodes.new('ShaderNodeMix')
        gm.name = gm.label = "DET2_mix"
        gm.data_type = 'RGBA'
        gm.blend_type = 'OVERLAY'
        gm.location = (-560, -520)
    gm.inputs[0].default_value = GRAIN_FAC
    nt.links.new(n["DET_mix"].outputs["Result"], gm.inputs[6])   # A
    nt.links.new(grain.outputs["Color"], gm.inputs[7])           # B
    nt.links.new(gm.outputs["Result"], n["FADE_mix"].inputs[6])  # A of the fade

    # ---- 2. the Normal input, which had nothing on it ----
    nm = nt.nodes.get("DET2_normalmap")
    if nm is None:
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nm.name = nm.label = "DET2_normalmap"
        nm.location = (-560, -760)
    nm.uv_map = "UVMap" if "UVMap" in [uv.name for uv in
                                       (bpy.data.objects["SHIBUYA_GROUND"].data.uv_layers
                                        if bpy.data.objects.get("SHIBUYA_GROUND") else [])] else ""
    nm.inputs["Strength"].default_value = NORMAL_STR
    nt.links.new(nrm_t.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])

    # ---- 3. roughness variation so a low sun can glint off the wheel tracks ----
    rm = nt.nodes.get("DET2_roughmix")
    if rm is None:
        rm = nt.nodes.new('ShaderNodeMix')
        rm.name = rm.label = "DET2_roughmix"
        rm.data_type = 'RGBA'
        rm.blend_type = 'MULTIPLY'
        rm.location = (-560, -1000)
    rm.inputs[0].default_value = ROUGH_FAC
    src = n["FADE_rough"].inputs[6].links[0].from_socket if n["FADE_rough"].inputs[6].links else None
    if src is not None:
        nt.links.new(src, rm.inputs[6])
        nt.links.new(rgh_t.outputs["Color"], rm.inputs[7])
        nt.links.new(rm.outputs["Result"], n["FADE_rough"].inputs[6])

    print("  %s: close detail wired" % MAT)
    print("     grain   OVERLAY %.2f at %.0f repeats (%.1f m/tile)" % (GRAIN_FAC, reps, TILE_M))
    print("     NORMAL  strength %.2f  (this input was UNCONNECTED)" % NORMAL_STR)
    print("     rough   MULTIPLY %.2f into the inner roughness" % ROUGH_FAC)
    return 1


if globals().get("__name__") == "__main__":
    run()
    print("GROUND DETAIL APPLIED")
