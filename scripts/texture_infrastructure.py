"""Put a base-colour image on the infrastructure that ships with none. ZERO triangles.

Measured on the delivered FBX rather than in the viewport, because OVERDARE gives each
MeshPart one image and that image IS the quality:

    09_VIADUCT   209,354 m2   0.0 texels/m2   no image at all
    03_ROADS      39,359 m2   0.6             1.31 m per texel
    11_STATION    36,599 m2   0.3             1.76 m per texel
    02_BUILDINGS               663
    masters                92,043

fix_material_response.py already corrected these materials' metallic and roughness, and that
work does not travel - `export_material` rebuilds every material as a bare TEX_IMAGE ->
Base Color, so the BSDF values are reset on the way out. An image is the only thing that
survives the trip, which is what this adds.

World-space BOX projection, computed by hand: `bpy.ops.uv.smart_project` needs edit mode and
that hangs indefinitely under --background. Same recipe as s5_texture_props.py and
apply_landmark_textures.py.

Tiles are chosen against the real object, not by taste: a 6 m concrete map on a viaduct pier
puts the form-panel joints at a plausible 3 m pitch, and ballast at 6 m reads as stone
rather than gravel-coloured mud.
"""
import bpy
import os

TEX = r"C:\Work\blender\ShibuyaAssetPack\03_Textures\INF_Infrastructure"

# material -> (image, tile metres, roughness low, roughness high)
WIRING = {
    "M_VD_Deck":      ("INF_Concrete.png", 7.0, 0.62, 0.88),
    "M_VD_Pier":      ("INF_Concrete.png", 5.0, 0.66, 0.90),
    "M_VD_Barrier":   ("INF_Concrete.png", 4.0, 0.60, 0.86),
    "M_ST_Platform":  ("INF_Concrete.png", 5.0, 0.58, 0.84),
    "M_ST_Column":    ("INF_Steel.png",    4.0, 0.42, 0.68),
    "M_ST_Canopy":    ("INF_Steel.png",    6.0, 0.44, 0.70),
    "M_ST_Ballast":   ("INF_Ballast.png",  6.0, 0.80, 0.96),
    "M_SH_Shell":     ("INF_Steel.png",    8.0, 0.44, 0.70),
    "M_SHIBUYA_KERB": ("INF_Concrete.png", 3.0, 0.66, 0.90),
    "M_ZK_Concrete":  ("INF_Concrete.png", 5.0, 0.68, 0.92),
    "M_BLDG_PARAPET": ("INF_Concrete.png", 4.0, 0.68, 0.92),
    # M_ZK_Frame is 323,970 m2 - the largest untextured surface on the map
    "M_ZK_Frame":     ("INF_Concrete.png", 6.0, 0.58, 0.84),
}
# objects whose UVs need the box projection; keyed by the collection they live in
COLLS = ("MAP_SHIBUYA_VIADUCT", "MAP_SHIBUYA_STATION", "MAP_SHIBUYA_ROADS",
         "MAP_SHIBUYA_BUILDINGS", "MAP_SHIBUYA_ZAKKYO")


def _img(path, non_color=False):
    im = bpy.data.images.load(path, check_existing=True)
    if non_color:
        try:
            im.colorspace_settings.name = 'Non-Color'
        except Exception:
            pass
    return im


def wire(mat, fname, tile, r_lo, r_hi):
    """TEX_IMAGE -> Base Color DIRECTLY, plus derived roughness/bump for the Blender view"""
    p = os.path.join(TEX, fname)
    if not os.path.exists(p):
        raise RuntimeError("%s missing - run 03_Textures/make_infra_textures.py first" % p)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        return False
    out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
    if out is None:
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    t = nt.nodes.get("INF_tex")
    if t is None:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.name = t.label = "INF_tex"
        t.location = (-620, 0)
    t.image = _img(p)
    t.extension = 'REPEAT'
    t.interpolation = 'Linear'

    mp = nt.nodes.get("INF_map")
    if mp is None:
        mp = nt.nodes.new('ShaderNodeMapping')
        mp.name = mp.label = "INF_map"
        mp.location = (-820, 0)
    mp.inputs["Scale"].default_value = (1.0/tile, 1.0/tile, 1.0/tile)
    tc = nt.nodes.get("INF_tc")
    if tc is None:
        tc = nt.nodes.new('ShaderNodeTexCoord')
        tc.name = tc.label = "INF_tc"
        tc.location = (-1020, 0)
    # Generated would rescale per object; Object coords are world metres here because the
    # anchor offset is baked into the mesh and these objects sit at the origin.
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])

    bw = nt.nodes.get("INF_bw")
    if bw is None:
        bw = nt.nodes.new('ShaderNodeRGBToBW')
        bw.name = bw.label = "INF_bw"
        bw.location = (-380, -260)
    nt.links.new(t.outputs["Color"], bw.inputs["Color"])
    mr = nt.nodes.get("INF_rough")
    if mr is None:
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.name = mr.label = "INF_rough"
        mr.location = (-180, -260)
    mr.clamp = True
    mr.inputs[1].default_value = 0.05
    mr.inputs[2].default_value = 0.55
    mr.inputs[3].default_value = r_hi          # dark aggregate voids are rougher
    mr.inputs[4].default_value = r_lo
    nt.links.new(bw.outputs["Val"], mr.inputs[0])
    nt.links.new(mr.outputs["Result"], bsdf.inputs["Roughness"])
    bp = nt.nodes.get("INF_bump")
    if bp is None:
        bp = nt.nodes.new('ShaderNodeBump')
        bp.name = bp.label = "INF_bump"
        bp.location = (-180, -480)
    bp.inputs["Strength"].default_value = 0.35
    bp.inputs["Distance"].default_value = 0.03
    nt.links.new(bw.outputs["Val"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Metallic"].default_value = 0.0
    return True


def run():
    n_mat = 0
    for name, (fname, tile, lo, hi) in WIRING.items():
        m = bpy.data.materials.get(name)
        if m is None:
            continue
        if wire(m, fname, tile, lo, hi):
            print("     %-18s <- %-18s tile %.1f m" % (name, fname, tile))
            n_mat += 1

    # UVs: the projection is done in the shader from Object coordinates, so no UV layer is
    # needed for the Blender view - but the FBX carries UVs, not a node graph, so the mesh
    # needs the same projection baked into a UV layer or OVERDARE gets a flat colour.
    n_obj = n_face = n_shared = 0
    done_shared = set()
    for cn in COLLS:
        c = bpy.data.collections.get(cn)
        if c is None:
            continue
        for o in c.objects:
            if o.type != 'MESH' or not o.data.polygons:
                continue
            me = o.data
            mats = [mm.name if mm else "" for mm in me.materials]
            if not any(mm in WIRING for mm in mats):
                continue
            uvl = me.uv_layers.active or me.uv_layers.new(name="UVMap")
            uvd = uvl.data
            # A shared mesh cannot hold a world-space projection: every instance would
            # rewrite the same UV layer from its own position and the last one seen would
            # win for all of them. 40,609 objects were writing into ~56 zakkyo meshes.
            # Instances get a LOCAL projection instead, which is identical for every copy
            # and correct for all of them because these maps tile.
            shared = me.users > 1
            M = o.matrix_world
            if shared and me.name in done_shared:
                continue
            touched = False
            for p in me.polygons:
                mn = mats[p.material_index] if p.material_index < len(mats) else ""
                if mn not in WIRING:
                    continue
                tile = WIRING[mn][1]
                nrm = p.normal.copy()
                if not shared:
                    nrm.rotate(M.to_quaternion())
                ax, ay, az = abs(nrm.x), abs(nrm.y), abs(nrm.z)
                for li, vi in zip(p.loop_indices, p.vertices):
                    w = me.vertices[vi].co if shared else (M @ me.vertices[vi].co)
                    if az >= ax and az >= ay:
                        u, v = w.x, w.y
                    elif ax >= ay:
                        u, v = w.y, w.z
                    else:
                        u, v = w.x, w.z
                    uvd[li].uv = (u/tile, v/tile)
                n_face += 1
                touched = True
            if touched:
                n_obj += 1
                if shared:
                    done_shared.add(me.name)
                    n_shared += 1
    print("  infrastructure: %d materials textured, %d faces re-projected on %d objects"
          % (n_mat, n_face, n_obj))
    print("     %d shared meshes projected in LOCAL space (instanced - a world projection "
          "would let the last instance overwrite every copy)" % n_shared)
    return n_mat


if globals().get("__name__") == "__main__":
    run()
    print("INFRASTRUCTURE TEXTURED")
