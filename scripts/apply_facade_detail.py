"""Multiply the tileable facade detail over every building material.

Insert, per material:

    TexCoord.Object -> Mapping(scale 1/TILE_M) -> ImageTexture(BOX projection) --.
                                                                                 MixRGB
    existing photo TEX_IMAGE ----------------------------------------------------'  (Multiply)
                                                                                    |
                                                                            Base Color

BOX projection is the point: the detail has to repeat in WORLD METRES, not in UV space. In
UV space it would be stretched by exactly the same factor that ruined the photo - a facade
smeared over 50 m would get its detail smeared over 50 m too, which is no help at all.
PLATEAU objects carry an identity transform with the anchor offset baked into the mesh, so
Object coordinates ARE world metres here.

Strength is scaled by how badly the material needs it: a facade already at 20 texels/m gets
a whisper, one at 2.4 gets the full effect. Nothing is applied uniformly, because the 85% of
buildings that are fine should not be touched.

HONEST LIMIT: this improves BLENDER renders only. shibuya_export_v2 rewires any material
whose Base Color is not a direct TEX_IMAGE back to its single source image (the workaround
for the M_ZK_SignAtlas trap), so the FBX still ships the bare photo. Fixing that for
OVERDARE would need a bake, and this Blender build exposes only BLENDER_EEVEE, so
bpy.ops.object.bake is not available.
"""
import bpy
import math
import os
import sys

_HERE = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else r"C:\Work\blender\ShibuyaAssetPack\06_Placement")
sys.path.insert(0, _HERE)

TEX = r"C:\Work\blender\ShibuyaAssetPack\03_Textures\BLDG_FacadeDetail.png"
TILE_M = 6.8
DETAIL_NODE = "BLDG_DETAIL"
# First pass wired only 44 of 402 materials and the A/B was barely visible. Two reasons,
# both measured: DENSITY_NONE at 14.0 excluded 357 materials when the map median is 14.2,
# and the density is computed per MATERIAL over all the geometry using it - a photo shared
# between a 50 m tower and its low neighbours averages out and never looks blurry by that
# statistic even though the tower plainly is.
#
# So: wire everything, and floor the strength. The map is normalised to mean 1.0, so on an
# already-sharp facade it adds fine structure without darkening or muddying anything.
DENSITY_FULL = 3.0        # at or under this many texels/m, full strength
DENSITY_NONE = 30.0       # at or above this, still applied, but at STRENGTH_MIN
STRENGTH_MIN = 0.45
STRENGTH_MAX = 1.00


def photo_node(nt):
    for n in nt.nodes:
        if n.type == 'TEX_IMAGE' and n.image and n.name != DETAIL_NODE:
            return n
    return None


def material_density(mat, area_by_mat, uvarea_by_mat):
    """texels per metre for this material, from the geometry that actually uses it"""
    a = area_by_mat.get(mat.name, 0.0)
    au = uvarea_by_mat.get(mat.name, 0.0)
    if a <= 0 or au <= 0:
        return None
    im = photo_node(mat.node_tree)
    if im is None:
        return None
    return math.sqrt(au/a) * (max(im.image.size) or 1)


def survey(coll="MAP_SHIBUYA_BUILDINGS"):
    """world area and UV area per material name, over the real building geometry"""
    area = {}
    uvarea = {}
    c = bpy.data.collections.get(coll)
    for ob in (c.objects if c else []):
        if ob.type != 'MESH' or not ob.data.polygons or not ob.data.uv_layers:
            continue
        me = ob.data
        uvl = me.uv_layers[0].uv
        for p in me.polygons:
            if p.material_index >= len(me.materials):
                continue
            m = me.materials[p.material_index]
            if m is None:
                continue
            uv = [uvl[k].vector for k in p.loop_indices]
            au = 0.0
            for k in range(len(uv)):
                x1, y1 = uv[k]
                x2, y2 = uv[(k+1) % len(uv)]
                au += x1*y2 - x2*y1
            area[m.name] = area.get(m.name, 0.0) + p.area
            uvarea[m.name] = uvarea.get(m.name, 0.0) + abs(au)*0.5
    return area, uvarea


def wire(mat, img, strength):
    nt = mat.node_tree
    if nt.nodes.get(DETAIL_NODE):
        return False                      # already wired
    ph = photo_node(nt)
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if ph is None or bsdf is None:
        return False
    base = bsdf.inputs['Base Color']
    if not base.is_linked:
        return False

    tc = nt.nodes.new('ShaderNodeTexCoord'); tc.location = (-1100, -320)
    mp = nt.nodes.new('ShaderNodeMapping'); mp.location = (-900, -320)
    mp.inputs['Scale'].default_value = (1.0/TILE_M, 1.0/TILE_M, 1.0/TILE_M)
    dt = nt.nodes.new('ShaderNodeTexImage'); dt.name = DETAIL_NODE
    dt.label = DETAIL_NODE
    dt.image = img
    dt.projection = 'BOX'                 # world-space triplanar; UV space would re-stretch
    dt.projection_blend = 0.35
    dt.extension = 'REPEAT'
    dt.interpolation = 'Cubic'
    dt.location = (-680, -320)
    try:
        dt.image.colorspace_settings.name = 'Non-Color'
    except Exception:
        pass

    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.clamp_result = True
    mix.location = (-420, -60)
    mix.inputs['Factor'].default_value = strength

    src = base.links[0].from_socket
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    nt.links.new(mp.outputs['Vector'], dt.inputs['Vector'])
    nt.links.new(src, mix.inputs[6])          # A
    nt.links.new(dt.outputs['Color'], mix.inputs[7])   # B
    nt.links.new(mix.outputs[2], base)
    return True


def run(coll="MAP_SHIBUYA_BUILDINGS"):
    if not os.path.exists(TEX):
        print("  !! %s missing - run 03_Textures/make_facade_detail.py first" % TEX)
        return 0
    img = bpy.data.images.load(TEX, check_existing=True)
    area, uvarea = survey(coll)
    print("  materials carrying building geometry: %d" % len(area))

    mats = {}
    c = bpy.data.collections.get(coll)
    for ob in (c.objects if c else []):
        if ob.type != 'MESH':
            continue
        for m in ob.data.materials:
            if m is not None and m.use_nodes:
                mats[m.name] = m

    n = 0
    skipped_ok = 0
    buckets = {}
    for name, m in sorted(mats.items()):
        d = material_density(m, area, uvarea)
        if d is None:
            skipped_ok += 1
            continue
        # full strength at DENSITY_FULL, easing to STRENGTH_MIN at DENSITY_NONE
        t = (DENSITY_NONE - d) / (DENSITY_NONE - DENSITY_FULL)
        t = max(0.0, min(1.0, t))
        s = STRENGTH_MIN + (STRENGTH_MAX - STRENGTH_MIN)*t
        if wire(m, img, s):
            n += 1
            b = int(min(d, 28.0)//4)*4
            buckets[b] = buckets.get(b, 0) + 1
    print("  wired detail into %d material(s); %d had no measurable density"
          % (n, skipped_ok))
    for b in sorted(buckets):
        print("      %2d-%2d texels/m : %d material(s)" % (b, b+4, buckets[b]))
    return n


if globals().get("__name__") == "__main__":
    run()
    print("FACADE DETAIL APPLIED")
