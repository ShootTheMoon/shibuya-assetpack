"""Point every atlasable face at its file's 4096 sheet and collapse those materials to one.

This is the step that actually removes the import blocker. OVERDARE counts import units per
MATERIAL and its importer leaks a transient world per published asset until unique-name
generation fails, so the 1,301-unit delivery needs 29-44 Studio restarts. Collapsing each
export file's 0..1-mapped materials to a single atlas material takes it to ~135.

Costs nothing in sharpness: the sheets were packed from the DELIVERED image sizes and the
worst file needed 11,337,728 px against a 4096 sheet's 16,777,216.

THE UV MAPPING, which is the only place this can go subtly wrong:

    PIL pastes at (x, y) with y measured from the TOP; Blender's v runs from the BOTTOM.

    u' = (x + u * w) / SHEET
    v' = 1 - (y + (1 - v) * h) / SHEET

Tiling materials are left untouched. `atlas_pack.py` classified them by measuring each
material's actual UV range, and a box-projected material whose UVs run to 40 would sample
its neighbours in the sheet. Those 36 are shared across the map anyway, so they cost 36
units total.

Grouping note: the plan was produced by shibuya_export_v2.pack_files, and pack_files is
deterministic on triangle counts. Assigning materials does not change any triangle count, so
re-running it at export time reproduces the same grouping. verify_atlas() checks that after
the fact rather than trusting it.
"""
import bpy
import json
import os

ATLAS = r"C:\Work\MeshTest\_ATLAS"
PLAN = os.path.join(ATLAS, "_atlas_plan.json")
SHEET = 4096
# same threshold atlas_pack.plan() uses to call a material tiling, so the per-face guard
# and the global classification cannot disagree
TOL = 0.05


def sheet_name(rec):
    return "ATLAS_%s_%02d.png" % (rec["folder"].split("_", 1)[-1], rec["index"])


def atlas_material(rec):
    """one material per export file: TEX_IMAGE straight into Base Color.

    Direct, because shibuya_export_v2.export_material walks back from Base Color and takes
    the first TEX_IMAGE - anything indirect ships untextured.
    """
    name = "M_ATL_%s_%02d" % (rec["folder"].split("_", 1)[-1], rec["index"])
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (420, 0)
    b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (160, 0)
    t = nt.nodes.new('ShaderNodeTexImage'); t.location = (-260, 0)
    p = os.path.join(ATLAS, sheet_name(rec))
    if not os.path.exists(p):
        raise RuntimeError("%s missing - run atlas_bake.py first" % p)
    t.image = bpy.data.images.load(p, check_existing=True)
    t.extension = 'CLIP'        # a UV outside the sheet is a bug, not something to wrap
    t.interpolation = 'Linear'
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.72
    b.inputs["Metallic"].default_value = 0.0
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def run():
    if not os.path.exists(PLAN):
        print("  !! %s missing - run MeshTest/atlas_pack.py first" % PLAN)
        return 0
    plan = json.load(open(PLAN, encoding="utf-8"))
    n_face = n_obj = n_file = n_skip = 0
    for rec in plan:
        rects = rec.get("rects") or {}
        if not rec.get("fits") or not rects:
            continue
        mat = atlas_material(rec)
        touched = False
        for oname in rec["objects"]:
            o = bpy.data.objects.get(oname)
            if o is None or o.type != 'MESH' or not o.data.uv_layers:
                continue
            me = o.data
            uvl = me.uv_layers[0].data
            names = [m.name if m else "" for m in me.materials]
            # the atlas material gets one slot on this mesh; tiling slots stay where they are
            if mat.name in names:
                slot = names.index(mat.name)
            else:
                me.materials.append(mat)
                names.append(mat.name)
                slot = len(me.materials) - 1
            hit = False
            for p in me.polygons:
                mn = names[p.material_index] if p.material_index < len(names) else ""
                r = rects.get(mn)
                if r is None:
                    continue                      # tiling, or already remapped
                # Per-face guard. The classification is global now, but a face whose UVs are
                # outside 0..1 must never be remapped anyway - it would land on a neighbour's
                # rect. This is what turns a classification mistake into a skipped face and a
                # printed count instead of 511 silently broken objects.
                #
                # TOL matches the threshold atlas_pack.plan() used to call a material tiling,
                # so the guard and the classification now agree. At a stricter 0.001 the guard
                # disagreed with the plan and rejected every border face of every ground tile:
                # retile_ground gives each tile a deliberate 0.8% bleed overlap (-0.008..1.008)
                # so neighbours blend without a seam, which is a margin, not tiling. 56 tile
                # materials survived into the delivery because of it - the guard was quietly
                # undoing the atlas on the single largest surface in the map.
                uvs = [tuple(uvl[li].uv) for li in p.loop_indices]
                if any(c < -TOL or c > 1.0 + TOL for uv in uvs for c in uv):
                    n_skip += 1
                    continue
                x, y, w, h = r
                for li, (u, v) in zip(p.loop_indices, uvs):
                    # Clamp inside the rect. Within TOL the overshoot is at most 5% of one
                    # rect; the gutter is 4 texels, so mapping it verbatim would sample the
                    # neighbour. Clamping repeats the rect's edge texel instead - which is
                    # what extension='CLIP' does anyway, and on a 106 m ground tile the
                    # clamped band is the part that already duplicates the adjacent tile.
                    u = 0.0 if u < 0.0 else (1.0 if u > 1.0 else u)
                    v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
                    uvl[li].uv = ((x + u * w) / SHEET,
                                  1.0 - (y + (1.0 - v) * h) / SHEET)
                p.material_index = slot
                n_face += 1
                hit = True
            if hit:
                n_obj += 1
                touched = True
        if touched:
            n_file += 1
        print("     %-26s %3d rects -> %s" % (sheet_name(rec), len(rects), mat.name))
    print("  atlas applied: %d files, %d objects, %s faces remapped, %d skipped by the "
          "UV guard" % (n_file, n_obj, format(n_face, ','), n_skip))
    return n_file


def prune_slots(me):
    """Drop material slots no polygon points at any more.

    Remapping sets every atlased face to the atlas slot, which leaves the original slots
    present but unused - and `shibuya_export_v2` walks `me.materials`, so an unused slot is
    still a delivered material and still an import unit. TERRAIN_07 shipped 21 materials for
    a single atlas because of this.

    Indices are captured BEFORE materials.clear(), because clear() resets every polygon's
    material_index to 0 - the same trap that collapsed the taxi to one slot in S4.
    """
    used = sorted({p.material_index for p in me.polygons})
    if len(used) >= len(me.materials):
        return 0
    keep = [me.materials[i] for i in used if i < len(me.materials)]
    remap = {old: new for new, old in enumerate(used)}
    idx = [remap.get(p.material_index, 0) for p in me.polygons]
    dropped = len(me.materials) - len(keep)
    me.materials.clear()
    for m in keep:
        me.materials.append(m)
    for p, i in zip(me.polygons, idx):
        p.material_index = i
    return dropped


def prune_all():
    n_me = n_slot = 0
    for me in bpy.data.meshes:
        if not me.polygons or not me.materials:
            continue
        d = prune_slots(me)
        if d:
            n_me += 1
            n_slot += d
    print("  pruned %d unused material slots across %d meshes" % (n_slot, n_me))
    return n_slot


def verify():
    """every remapped UV must land inside the sheet, and each object should now carry one
    atlas material at most"""
    bad_uv = bad_mat = 0
    checked = 0
    for o in bpy.data.objects:
        if o.type != 'MESH' or not o.data.uv_layers:
            continue
        atl = [m.name for m in o.data.materials if m and m.name.startswith("M_ATL_")]
        if not atl:
            continue
        checked += 1
        if len(atl) > 1:
            bad_mat += 1
            print("     !! %s carries %d atlas materials: %s" % (o.name, len(atl), atl))
        names = [m.name if m else "" for m in o.data.materials]
        uvl = o.data.uv_layers[0].data
        for p in o.data.polygons:
            if p.material_index >= len(names) or not names[p.material_index].startswith("M_ATL_"):
                continue
            for li in p.loop_indices:
                u, v = uvl[li].uv
                if u < -1e-4 or u > 1.0001 or v < -1e-4 or v > 1.0001:
                    bad_uv += 1
                    break
    print("  verify: %d objects with an atlas material | UV outside 0..1: %d | multi-atlas: %d"
          % (checked, bad_uv, bad_mat))
    return bad_uv == 0 and bad_mat == 0


if globals().get("__name__") == "__main__":
    run()
    verify()
    print("ATLAS APPLIED")
