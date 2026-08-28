"""S5-1: texture UP_UtilityPole_A and SF_StreetLamp_A. Costs ZERO triangles.

These two were the best value in the S5 budget: the pole is 274 instances x 1,836 tris =
503,064 triangles on screen - the largest single item left after S4 - and it rendered as
flat grey because it had four solid-colour materials and no UV layer at all.

UVs are a world-space BOX projection computed by hand. bpy.ops.uv.smart_project needs edit
mode, and bpy.ops.object.mode_set(mode='EDIT') spins forever under --background, so ops are
not an option here. Box projection is also the right choice on its own merits: the maps are
tileable and repeat in metres, so 274 poles do not all share one visible seam, and a pole is
mostly axis-aligned boxes and cylinders which box-project cleanly.

Run against each asset .blend; saves in place.
"""
import bpy
import os

TEX = r"C:\Work\blender\ShibuyaAssetPack\03_Textures"

# material -> (texture relative path, tile size in metres)
WIRING = {
    "M_UP_Concrete":    ("UP_Utility_Overhead/UP_UtilityPole_A_concrete.png", 2.0),
    "M_UP_Steel":       ("UP_Utility_Overhead/UP_UtilityPole_A_steel.png", 1.0),
    "M_UP_Insulator":   ("UP_Utility_Overhead/UP_UtilityPole_A_insulator.png", 0.35),
    "M_UP_Transformer": ("UP_Utility_Overhead/UP_UtilityPole_A_transformer.png", 0.9),
    "M_SF_LampPole":    ("SF_Street_Furniture/SF_StreetLamp_A_pole.png", 1.6),
    "M_SF_LampHead":    ("SF_Street_Furniture/SF_StreetLamp_A_head.png", 0.7),
}


def box_uv(ob, tile=2.0, layer="UVMap"):
    """World-space box projection: pick the face normal's dominant axis, project onto the
    other two. One UV unit = `tile` metres."""
    me = ob.data
    uvl = me.uv_layers.get(layer) or me.uv_layers.new(name=layer)
    M = ob.matrix_world
    for p in me.polygons:
        n = p.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in p.loop_indices:
            co = M @ me.vertices[me.loops[li].vertex_index].co
            if ax == 0:
                u, w = co.y, co.z
            elif ax == 1:
                u, w = co.x, co.z
            else:
                u, w = co.x, co.y
            uvl.uv[li].vector = (u/tile, w/tile)
    return uvl


def wire(mat, img_path, tile):
    """Insert TEX_IMAGE -> Base Color, keeping the existing roughness/metallic.

    The image goes into Base Color DIRECTLY, not through a mix or a colour node: FBX only
    carries a direct TEX_IMAGE, and shibuya_export_v2 had to grow a whole workaround the
    last time a material put something in between (M_ZK_SignAtlas exported untextured)."""
    if not os.path.exists(img_path):
        print("      !! missing %s" % img_path)
        return False
    img = bpy.data.images.load(img_path, check_existing=True)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        print("      !! %s has no Principled BSDF" % mat.name)
        return False
    for n in list(nt.nodes):
        if n.type in ('TEX_IMAGE', 'MAPPING', 'TEX_COORD'):
            nt.nodes.remove(n)
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = img
    t.interpolation = 'Cubic'
    t.extension = 'REPEAT'                 # the maps are tileable; CLIP would show a seam
    t.location = (-320, 0)
    nt.links.new(t.outputs['Color'], bsdf.inputs['Base Color'])
    return True


def run():
    n_uv = n_tex = 0
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or not ob.data.polygons or ob.name.startswith("REF_"):
            continue
        names = [m.name for m in ob.data.materials if m]
        if not any(nm in WIRING for nm in names):
            continue
        tile = max(WIRING[nm][1] for nm in names if nm in WIRING)
        box_uv(ob, tile)
        n_uv += 1
        print("  %-26s box UV at %.2f m/tile, %d materials"
              % (ob.name, tile, len(ob.data.materials)))
        for m in ob.data.materials:
            if m is None or m.name not in WIRING:
                continue
            rel, _ = WIRING[m.name]
            if wire(m, os.path.join(TEX, rel.replace("/", os.sep)), tile):
                print("      %-20s <- %s" % (m.name, os.path.basename(rel)))
                n_tex += 1
    print("  uv-mapped %d object(s), textured %d material(s)" % (n_uv, n_tex))
    return n_uv, n_tex


if globals().get("__name__") == "__main__":
    run()
    bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath, compress=True)
    print("S5 TEXTURE PROPS DONE")
