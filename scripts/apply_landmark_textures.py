"""T2: texture the two hand-modelled hero landmarks. Costs ZERO triangles.

Measured: LM_ScrambleSquare_A 64,318 m2 and LM_Shibuya109_A 28,181 m2 are flat colour -
92,499 m2, a quarter of the map's untextured surface, on the two silhouettes that dominate
every aerial. Their photo-textured PLATEAU neighbours make them read as grey CG.

Reuses the recipe proven on the utility pole in s5_texture_props.py rather than restating
it: world-space BOX projection computed by hand (bpy.ops.uv.smart_project needs edit mode,
which spins forever under --background), and the image wired DIRECTLY into Base Color.

Direct is deliberate. shibuya_export_v2.export_material walks back from Base Color and
takes the first TEX_IMAGE it reaches, so this carries into the FBX and reaches OVERDARE.
The facade-detail overlay in apply_facade_detail.py cannot, because it sits behind a Mix.
"""
import bpy
import os
import sys

_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)
from s5_texture_props import box_uv, wire          # noqa: E402  - same recipe, one copy

TEX = r"C:\Work\blender\ShibuyaAssetPack\03_Textures\LM_Landmarks"

# material -> (texture file, tile size in metres)
# Tiles are chosen against the real geometry: build_scramble_square.py uses FLOOR = 4.20 m,
# so the glazing tile is one storey; the ribs on 109 are ~0.6 m, four to a 2.4 m tile.
WIRING = {
    "M_LMSS_Glass":   ("LM_ScrambleSquare_glass.png", 4.20),
    "M_LMSS_Mullion": ("LM_ScrambleSquare_mullion.png", 1.00),
    "M_LMSS_Podium":  ("LM_ScrambleSquare_podium.png", 3.40),
    "M_LMSS_Deck":    ("LM_ScrambleSquare_deck.png", 4.00),
    "M_LM109_Clad":   ("LM_109_clad.png", 2.40),
    "M_LM109_Glass":  ("LM_109_glass.png", 3.00),
    "M_LM109_Base":   ("LM_109_base.png", 2.50),
}
OBJECTS = ("LM_ScrambleSquare_A", "LM_Shibuya109_A")


def run():
    n_uv = n_tex = 0
    for name in OBJECTS:
        ob = bpy.data.objects.get(name)
        if ob is None or ob.type != 'MESH':
            print("  !! %s absent" % name)
            continue
        mats = [m.name for m in ob.data.materials if m]
        hit = [m for m in mats if m.split('.')[0] in WIRING]
        if not hit:
            print("  %s: no matching material (%s)" % (name, mats))
            continue
        # one UV layer per object; the tile is baked into the projection, so use the
        # largest of the object's tiles and let the per-material maps repeat within it
        tile = max(WIRING[m.split('.')[0]][1] for m in hit)
        box_uv(ob, tile)
        n_uv += 1
        print("  %-22s box UV at %.2f m/tile, %d material(s)" % (name, tile, len(mats)))
        for m in ob.data.materials:
            if m is None:
                continue
            key = m.name.split('.')[0]
            if key not in WIRING:
                print("      %-18s (left flat - not in WIRING)" % m.name)
                continue
            rel, _t = WIRING[key]
            if wire(m, os.path.join(TEX, rel), _t):
                print("      %-18s <- %s" % (m.name, rel))
                n_tex += 1
    print("  uv-mapped %d object(s), textured %d material(s)" % (n_uv, n_tex))
    return n_tex


if globals().get("__name__") == "__main__":
    run()
    print("LANDMARK TEXTURES APPLIED")
