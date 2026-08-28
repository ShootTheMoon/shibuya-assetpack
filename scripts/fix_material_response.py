"""Correct the surface response of the untextured materials. ZERO triangles.

Switching raytracing on in setup_lighting.py made an existing error visible rather than
creating one: 626,328 m2 of the map carries no image at all, and much of it was authored
with a FRACTIONAL metallic value. Metallic is not a shininess dial - it is a choice between
two different BRDFs, and a value in between is physically meaningless. A surface at
metallic 0.75 takes its colour from reflections instead of its albedo, so:

    M_ZK_Frame   323,970 m2   metallic 0.75, roughness 0.42, base (0.10, 0.105, 0.11)

renders as a near-black mirror. That is the largest untextured surface on the map by a
factor of 1.6 over everything else combined, it is the structural frame the zakkyo signs
are mounted on, and it is the "black slab" the signs appear to float in front of.

The station ironwork reading as chrome is the same error at M_ST_Canopy 0.35 and
M_ST_Column 0.55.

What is deliberately NOT changed:
  * M_ST_Rail metallic 0.85 - rail heads really are polished steel, and they are the one
    place on this map where a mirror is correct.
  * base colours - this pass fixes RESPONSE only, so the change is attributable. Albedo is
    a separate argument and the frame's darkness may well be intentional.
  * anything that already resolves to an image; those are handled by enhance_facades.py.
"""
import bpy

# name -> (metallic, roughness, why)
FIX = {
    "M_ZK_Frame":     (0.0, 0.72, "painted/rendered structural frame, not metal"),
    "M_ZK_Concrete":  (0.0, 0.90, "concrete"),
    "M_ZK_Shutter":   (0.0, 0.58, "painted roller shutter - steel, but painted"),
    "M_ST_Canopy":    (0.0, 0.62, "painted steel canopy"),
    "M_ST_Column":    (0.0, 0.58, "painted steel column"),
    "M_ST_Platform":  (0.0, 0.72, "concrete platform"),
    "M_ST_Ballast":   (0.0, 0.94, "track ballast"),
    "M_SH_Shell":     (0.0, 0.60, "painted hall shell"),
    "M_VD_Deck":      (0.0, 0.82, "concrete viaduct deck"),
    "M_VD_Barrier":   (0.0, 0.78, "concrete barrier"),
    "M_VD_Pier":      (0.0, 0.84, "concrete pier"),
    "M_BLDG_PARAPET": (0.0, 0.90, "concrete parapet"),
    "M_SHIBUYA_KERB": (0.0, 0.86, "concrete kerb"),
    "M_FRN_FENCE":    (0.0, 0.55, "galvanised but painted; 0.7 metallic made it mirror"),
    "M_UP_Wire":      (0.0, 0.68, "weathered overhead cable"),
    # the T2 landmark materials carry the same fractional-metallic error; the raycast
    # found M_LMSS_Podium at metallic 0.45 / roughness 0.20 in the ironwork region
    "M_LMSS_Podium":  (0.0, 0.42, "dark glazed retail base - dielectric"),
    "M_LMSS_Glass":   (0.0, 0.18, "curtain wall glazing - genuinely glossy, still dielectric"),
    "M_LMSS_Mullion": (0.0, 0.38, "anodised aluminium, painted"),
    "M_LMSS_Deck":    (0.0, 0.86, "roof concrete"),
    "M_LM109_Clad":   (0.0, 0.62, "painted ribbed cladding"),
    "M_LM109_Glass":  (0.0, 0.20, "glazing"),
    "M_LM109_Base":   (0.0, 0.72, "dark stone base"),
}
KEEP = {"M_ST_Rail": "polished rail head - metallic 0.85 is correct here"}


def run():
    n = 0
    for name, (met, rgh, why) in FIX.items():
        m = bpy.data.materials.get(name)
        if m is None or not m.use_nodes:
            continue
        b = next((x for x in m.node_tree.nodes if x.type == 'BSDF_PRINCIPLED'), None)
        if b is None:
            continue
        om = b.inputs["Metallic"].default_value
        orh = b.inputs["Roughness"].default_value
        if b.inputs["Metallic"].links or b.inputs["Roughness"].links:
            print("     %-18s SKIPPED - already driven by nodes" % name)
            continue
        b.inputs["Metallic"].default_value = met
        b.inputs["Roughness"].default_value = rgh
        print("     %-18s metal %.2f->%.2f  rough %.2f->%.2f   %s"
              % (name, om, met, orh, rgh, why))
        n += 1
    for name, why in KEEP.items():
        if bpy.data.materials.get(name):
            print("     %-18s LEFT ALONE - %s" % (name, why))
    print("  material response corrected on %d materials" % n)
    return n


if globals().get("__name__") == "__main__":
    run()
    print("MATERIAL RESPONSE FIXED")
