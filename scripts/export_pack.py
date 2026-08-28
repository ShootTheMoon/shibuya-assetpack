"""Export every ShibuyaAssetPack asset to FBX + GLB at the paths the manifest promises.

The manifest listed 72 rows but only 17 FBX actually existed - the sign variants,
shopfronts, pedestrians, taxi and landmarks were never written out. This walks
00_Source_Blender, exports each named object, and reports what it could not find.

Headless: blender --background --python export_pack.py
"""
import bpy, os, sys, csv

PACK = r"C:\Work\blender\ShibuyaAssetPack"
SRC  = os.path.join(PACK, "00_Source_Blender")
FBX  = os.path.join(PACK, "01_Exports_FBX")
GLB  = os.path.join(PACK, "02_Exports_GLB")


# Pre-made 1024 copies on disk. Downscaling inside Blender crashed the FBX exporter
# (EXCEPTION_ACCESS_VIOLATION, deterministic at the same address): image data is loaded
# LAZILY, so img.copy()+scale() on a not-yet-loaded disk image operates on a null buffer.
# has_data is NOT a usable guard either - it reads False for perfectly good disk images.
SMALL = {
    "ZK_SignAtlas_albedo": "ZK_Zakkyo_Facade_Kit/ZK_SignAtlas_albedo_1024.png",
    "ZK_SignAtlas_emit":   "ZK_Zakkyo_Facade_Kit/ZK_SignAtlas_emit_1024.png",
    "ZK_ShopAtlas_albedo": "ZK_Zakkyo_Facade_Kit/ZK_ShopAtlas_albedo_1024.png",
    "ZK_ShopAtlas_emit":   "ZK_Zakkyo_Facade_Kit/ZK_ShopAtlas_emit_1024.png",
    # the Aogaeru ships one PACKED 8192 texture; embedding it made a 20k-tri prop a
    # 26.9 MB FBX. 8192 also exceeds what the OVERDARE importer tolerates.
    "deha5001_u1_v1_baseColor": "LM_Landmarks/LM_Aogaeru_baseColor_1024.png",
}
_tex, _mat = {}, {}


def small_of(img):
    key = img.name.split('.')[0]
    rel = SMALL.get(key)
    if not rel:
        return img
    if key in _tex:
        return _tex[key]
    path = os.path.join(PACK, "03_Textures", *rel.split('/'))
    if not os.path.exists(path):
        return img
    ni = bpy.data.images.load(path, check_existing=True)
    ni.colorspace_settings.name = img.colorspace_settings.name
    _tex[key] = ni
    return ni


def base_color_image(m):
    """the image feeding Base Color, however many nodes deep, and whether it is direct"""
    if not m or not m.use_nodes:
        return None, True
    b = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not b:
        return None, False
    link = b.inputs['Base Color'].links
    if not link:
        return None, True
    if link[0].from_node.type == 'TEX_IMAGE':
        return link[0].from_node.image, True          # already exports fine
    seen, stack = set(), [b.inputs['Base Color']]
    while stack:
        s = stack.pop()
        for l in s.links:
            fn = l.from_node
            if fn in seen:
                continue
            seen.add(fn)
            if fn.type == 'TEX_IMAGE' and fn.image:
                return fn.image, False
            stack.extend(fn.inputs)
    return None, False


def fix_material(m):
    """Only rewire what FBX would otherwise drop. Assets whose Base Color is already a
    direct TEX_IMAGE (crowd, taxi, tree, signal, vending) are left completely alone -
    they exported correctly before and rebuilding them is what caused the crash."""
    if m is None:
        return None
    if m.name in _mat:
        return _mat[m.name]
    img, direct = base_color_image(m)
    if direct:
        if img is not None and img.name.split('.')[0] in SMALL:
            for n in m.node_tree.nodes:
                if n.type == 'TEX_IMAGE' and n.image:
                    n.image = small_of(n.image)
        _mat[m.name] = m
        return m
    nm = bpy.data.materials.new("EXP_" + m.name[:54])
    nm.use_nodes = True
    nt = nm.node_tree
    nt.nodes.clear()
    o = nt.nodes.new('ShaderNodeOutputMaterial'); o.location = (400, 0)
    bs = nt.nodes.new('ShaderNodeBsdfPrincipled'); bs.location = (150, 0)
    if img is not None:
        t = nt.nodes.new('ShaderNodeTexImage'); t.location = (-250, 0)
        t.image = small_of(img)
        nt.links.new(t.outputs['Color'], bs.inputs['Base Color'])
    nt.links.new(bs.outputs['BSDF'], o.inputs['Surface'])
    _mat[m.name] = nm
    return nm


def export_one(ob, cat, name):
    for d in (os.path.join(FBX, cat), os.path.join(GLB, cat)):
        os.makedirs(d, exist_ok=True)
    for s in list(bpy.context.selected_objects): s.select_set(False)
    ob.hide_render = False; ob.hide_viewport = False
    for i, m in enumerate(ob.data.materials):
        ob.data.materials[i] = fix_material(m)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    fp = os.path.join(FBX, cat, name + ".fbx")
    bpy.ops.export_scene.fbx(filepath=fp, use_selection=True, object_types={'MESH'},
        embed_textures=True, path_mode='COPY', mesh_smooth_type='FACE',
        use_mesh_modifiers=True, bake_space_transform=False,
        axis_forward='-Y', axis_up='Z', global_scale=1.0)
    gp = os.path.join(GLB, cat, name + ".glb")
    bpy.ops.export_scene.gltf(filepath=gp, export_format='GLB',
        use_selection=True, export_apply=True)
    ob.select_set(False)
    return os.path.getsize(fp), os.path.getsize(gp)


def run():
    rows = list(csv.DictReader(open(os.path.join(PACK, "05_Documentation",
                                                 "asset_manifest.csv"), encoding="utf-8")))
    # asset_name -> (category, source .blend)
    want = {}
    for r in rows:
        want[r["asset_name"]] = r["category"]

    blends = []
    for root, _, files in os.walk(SRC):
        for f in files:
            if f.endswith(".blend"): blends.append(os.path.join(root, f))

    done = {}; missing = []
    for bl in sorted(blends):
        cat = os.path.basename(os.path.dirname(bl))
        bpy.ops.wm.open_mainfile(filepath=bl)
        # open_mainfile frees every datablock of the previous file. Caches that outlive
        # it hold dangling Material/Image pointers, and the next touch is an
        # EXCEPTION_ACCESS_VIOLATION - which is what killed the taxi twice.
        _mat.clear(); _tex.clear()
        objs = [o for o in bpy.data.objects if o.type == 'MESH' and o.data.polygons]
        for o in objs:
            nm = o.name
            if nm not in want:            # only export what the manifest promises
                continue
            if nm in done:
                continue
            try:
                fs, gs = export_one(o, want[nm], nm)
                done[nm] = (fs, gs)
                print("  %-26s %-24s %6.2f MB fbx / %6.2f MB glb" % (
                    nm, want[nm], fs/1e6, gs/1e6), flush=True)
            except Exception as e:
                print("  !! %-24s EXPORT FAILED: %s" % (nm, e), flush=True)
                missing.append((nm, "EXPORT FAILED: %s" % e))
    for nm in want:
        if nm not in done and not nm.startswith("LM_QFrontScreen"):
            missing.append((nm, "no source object found"))
    print("\nexported %d / %d manifest assets" % (len(done), len(want)), flush=True)
    if missing:
        print("NOT exported:", flush=True)
        for nm, why in missing: print("  %-26s %s" % (nm, why), flush=True)
    return done, missing


if __name__ == "__main__":
    run()
