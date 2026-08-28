"""Make building facades read as buildings instead of black slabs. ZERO triangles.

Facades are 28.0% of an eye-level frame - the second largest category after the ground, and
the measured cause of the "objects floating in mid-air" complaint: the sign stacks are not
floating (286 of ~44,000 instances are genuinely detached, 0.65%), the facades BEHIND them
are dark enough to read as sky.

Why they are dark, measured earlier: PLATEAU LOD2 carries daylight aerial-oblique photos at
mean brightness 0.304 and median 512 px for a whole facade. Nothing recovers detail that is
not in the photo. But two cues that make a real facade legible are missing entirely, and
both can be derived from the photo that is already there:

  * ROUGHNESS is uniform, so no window ever reflects anything. Real glazing reads because it
    mirrors the sky. Dark pixels in a facade photo are overwhelmingly glass, light pixels
    concrete - so the photo's own luminance is a usable glass mask.
  * NORMAL is unconnected, so the facade is a perfectly flat plane. Driving a small bump off
    the same luminance recesses the windows and gives the sun something to catch.

This pairs with the raytracing that setup_lighting.py switched on: screen-traced reflections
had nothing to show while every surface was equally rough.

EXPORT NOTE - honest limit. `shibuya_export_v2.export_material` rebuilds each material as a
bare TEX_IMAGE -> Base Color, so the roughness, the bump and the base-colour lift are
BLENDER ONLY. They do not reach OVERDARE. Carrying them would mean baking new facade images,
which is a separate job. The graph traversal at export_material:131-141 walks Base Color
recursively and treats any non-usable TEX_IMAGE as a dead end, so inserting nodes in that
path does not change which image is picked - verified rather than assumed, because this
picker has produced three separate regressions already.
"""
import bpy

DETAIL = "BLDG_DETAIL"          # must match apply_facade_detail / shibuya_export_v2
COLL = "MAP_SHIBUYA_BUILDINGS"

# dark pixel -> glass -> glossy; light pixel -> concrete -> rough
# Iteration 3, from a raycast rather than an opinion: 84.6% of the station-ironwork region
# resolves to the building material `shib0004` with roughness LINKED to this map. At
# ROUGH_LO 0.16 every dark pixel became a near-mirror, so shadowed CONCRETE turned to
# chrome along with the glazing. Only genuinely black pixels are glass, and even glass at
# this distance is not a perfect mirror in a screen-traced renderer.
ROUGH_LO, ROUGH_HI = 0.34, 0.80
LUM_LO, LUM_HI = 0.03, 0.50
BUMP_STRENGTH = 0.30
BUMP_DISTANCE = 0.045
# Iteration 2: BRIGHT 0.045 lifted the dark facades +42% but cost 10% of the eye-level
# LOCAL detail - a flat lift raises the floor without widening the spread. Trade it for
# contrast, which widens the spread around the midpoint instead.
BRIGHT = 0.015
CONTRAST = 0.34


def photo_node(nt):
    """the facade photo - the detail overlay is not it"""
    for n in nt.nodes:
        if (n.type == 'TEX_IMAGE' and n.image
                and n.name != DETAIL and n.label != DETAIL
                and DETAIL not in n.image.name):
            return n
    return None


def run():
    c = bpy.data.collections.get(COLL)
    if c is None:
        print("  !! %s not found" % COLL)
        return 0
    mats = []
    seen = set()
    for o in c.objects:
        if o.type != 'MESH':
            continue
        for m in o.data.materials:
            # M_FAC_* are the generated tileable facades from apply_facade_swap.py. They
            # already carry a per-variant roughness ramp and bump built for their own map;
            # re-deriving here would overwrite a tuned curve with a generic one. This is
            # what makes the finishing pass order-independent enough to re-run.
            if (m is not None and m.use_nodes and m.name not in seen
                    and not m.name.startswith("M_FAC_")):
                seen.add(m.name)
                mats.append(m)
    n_ok = n_skip = n_lift = 0
    for m in mats:
        nt = m.node_tree
        bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        ph = photo_node(nt)
        if bsdf is None or ph is None:
            n_skip += 1
            continue

        # ---- luminance of the facade photo, reused by both derived maps ----
        bw = nt.nodes.get("FCD_bw")
        if bw is None:
            bw = nt.nodes.new('ShaderNodeRGBToBW')
            bw.name = bw.label = "FCD_bw"
            bw.location = (ph.location[0] + 220, ph.location[1] - 320)
        nt.links.new(ph.outputs["Color"], bw.inputs["Color"])

        # ---- roughness: the glass mask ----
        mr = nt.nodes.get("FCD_rough")
        if mr is None:
            mr = nt.nodes.new('ShaderNodeMapRange')
            mr.name = mr.label = "FCD_rough"
            mr.location = (bw.location[0] + 200, bw.location[1])
        mr.clamp = True
        mr.inputs[1].default_value = LUM_LO
        mr.inputs[2].default_value = LUM_HI
        mr.inputs[3].default_value = ROUGH_LO
        mr.inputs[4].default_value = ROUGH_HI
        nt.links.new(bw.outputs["Val"], mr.inputs[0])
        nt.links.new(mr.outputs["Result"], bsdf.inputs["Roughness"])

        # ---- normal: recess the windows ----
        bp = nt.nodes.get("FCD_bump")
        if bp is None:
            bp = nt.nodes.new('ShaderNodeBump')
            bp.name = bp.label = "FCD_bump"
            bp.location = (bw.location[0] + 200, bw.location[1] - 220)
        bp.inputs["Strength"].default_value = BUMP_STRENGTH
        bp.inputs["Distance"].default_value = BUMP_DISTANCE
        bp.invert = False        # bright concrete proud, dark glazing recessed
        nt.links.new(bw.outputs["Val"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])

        # ---- base colour: a small lift with contrast, inserted in place ----
        # Only where the photo already drives something; never create a new Base Color link,
        # because a material whose Base Color is deliberately flat is not a facade.
        outs = [l for l in ph.outputs["Color"].links
                if l.to_node.name not in ("FCD_bw",)]
        if outs:
            bc = nt.nodes.get("FCD_bc")
            if bc is None:
                bc = nt.nodes.new('ShaderNodeBrightContrast')
                bc.name = bc.label = "FCD_bc"
                bc.location = (ph.location[0] + 220, ph.location[1])
            bc.inputs["Bright"].default_value = BRIGHT
            bc.inputs["Contrast"].default_value = CONTRAST
            for l in outs:
                if l.to_node is bc:
                    continue
                to_sock = l.to_socket
                nt.links.remove(l)
                nt.links.new(bc.outputs["Color"], to_sock)
            nt.links.new(ph.outputs["Color"], bc.inputs["Color"])
            n_lift += 1
        n_ok += 1

    print("  facades: %d materials enhanced, %d skipped (no photo / no BSDF), %d base-colour lifts"
          % (n_ok, n_skip, n_lift))
    print("     roughness  lum %.2f..%.2f -> %.2f..%.2f  (dark = glass = glossy)"
          % (LUM_LO, LUM_HI, ROUGH_LO, ROUGH_HI))
    print("     bump       strength %.2f distance %.3f  (Normal input was unconnected)"
          % (BUMP_STRENGTH, BUMP_DISTANCE))
    print("     base       bright %+.3f contrast %+.2f   (BLENDER ONLY - not in the FBX)"
          % (BRIGHT, CONTRAST))
    return n_ok


if globals().get("__name__") == "__main__":
    run()
    print("FACADES ENHANCED")
