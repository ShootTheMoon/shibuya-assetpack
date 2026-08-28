"""S6: render the missing asset previews.

04_Previews held 18 images for 72 assets. The manifest is now 91 assets, so per-asset
renders alone would mean 91 files, most of them of a 24-triangle module that means nothing
in isolation.

So: one 3-angle set per HERO asset (the things a reviewer actually judges), and one contact
sheet per kit family for the parts. The ZK kit is 57 assets of 24-142 triangles - a contact
sheet is the honest way to show them, and it also shows them together, which is how they
are used.

Driven per-.blend by the shell loop; see the S6 report for the invocation.
"""
import bpy
import os
import sys
import math
from mathutils import Vector

PACK = r"C:\Work\blender\ShibuyaAssetPack"
PREV = os.path.join(PACK, "04_Previews")

# assets that get their own 3-angle set; everything else lands on a contact sheet
HERO = ("UP_UtilityPole_A", "UP_CableSpan_A", "SF_VendingMachine_A", "SF_TrafficSignal_A",
        "SF_StreetLamp_A", "VH_TaxiCrown_A", "VH_SedanWhite_A", "VH_SedanSilver_A",
        "VH_SedanBlue_A", "VG_StreetTree_A", "LM_Shibuya109_A", "LM_Hachiko_A",
        "LM_Aogaeru_A", "LM_ScrambleSquare_A", "GR_TactilePaving_Dot_A",
        "GR_TactilePaving_Bar_A")


def setup(res=(720, 540)):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    try:
        sh = sc.display.shading
        sh.light = 'STUDIO'
        sh.color_type = 'TEXTURE'          # show the S5 textures, not flat grey
        sh.show_cavity = True
    except AttributeError:
        pass
    cam = bpy.data.objects.get("PREVCAM")
    if cam is None:
        cam = bpy.data.objects.new("PREVCAM", bpy.data.cameras.new("PREVCAM"))
        sc.collection.objects.link(cam)
    cam.data.clip_end = 2000.0
    sc.camera = cam
    return sc, cam


def shoot(ob, cam, sc, outdir, angles=(("front", 20, 8), ("side", 105, 6),
                                       ("aerial", 55, 34))):
    hidden = []
    for o in bpy.data.objects:
        if o.type == 'MESH' and o is not ob and not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    M = ob.matrix_world
    pts = [M @ v.co for v in ob.data.vertices]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    ctr = (lo+hi)*0.5
    rad = max((hi-lo).x, (hi-lo).y, (hi-lo).z) * 2.1
    out = []
    for tag, az, el in angles:
        a, e = math.radians(az), math.radians(el)
        cam.location = ctr + Vector((math.cos(a)*math.cos(e), math.sin(a)*math.cos(e),
                                     math.sin(e))) * rad
        cam.rotation_euler = (ctr - cam.location).to_track_quat('-Z', 'Y').to_euler()
        p = os.path.join(outdir, "%s_%s.png" % (ob.name, tag))
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        out.append(p)
    for o in hidden:
        o.hide_render = False
    return out


def contact_sheet(objs, name, cam, sc, outdir, cols=6):
    """lay the kit parts out on a grid and take one shot of the lot"""
    saved = [(o, o.location.copy(), o.hide_render) for o in objs]
    hidden = []
    for o in bpy.data.objects:
        if o.type == 'MESH' and o not in objs and not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    pitch = 4.2
    for i, o in enumerate(objs):
        o.hide_render = False
        o.location = ((i % cols)*pitch, -(i // cols)*pitch, 0.0)
    bpy.context.view_layer.update()
    rows = (len(objs)+cols-1)//cols
    cx, cy = (cols-1)*pitch/2, -(rows-1)*pitch/2
    span = max(cols, rows)*pitch
    cam.location = Vector((cx - span*0.05, cy - span*0.75, span*0.95))
    cam.rotation_euler = (Vector((cx, cy, 1.4)) - cam.location).to_track_quat(
        '-Z', 'Y').to_euler()
    sc.render.resolution_x, sc.render.resolution_y = 1600, max(600, 260*rows)
    p = os.path.join(outdir, "%s_contact_sheet.png" % name)
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    for o, loc, hr in saved:
        o.location = loc
        o.hide_render = hr
    for o in hidden:
        o.hide_render = False
    return p


def run(category):
    outdir = os.path.join(PREV, category)
    os.makedirs(outdir, exist_ok=True)
    sc, cam = setup()
    objs = [o for o in bpy.data.objects
            if o.type == 'MESH' and o.data.polygons and not o.name.startswith("REF_")]
    heroes = [o for o in objs if o.name in HERO]
    rest = [o for o in objs if o.name not in HERO]
    n = 0
    for o in heroes:
        shoot(o, cam, sc, outdir)
        n += 3
        print("      %s x3" % o.name, flush=True)
    if rest:
        rest.sort(key=lambda o: o.name)
        p = contact_sheet(rest, category, cam, sc, outdir)
        n += 1
        print("      contact sheet: %d parts -> %s" % (len(rest), os.path.basename(p)))
    print("  %s: %d preview image(s)" % (category, n))
    return n


if __name__ != "never":
    run(sys.argv[-1])
    print("PREVIEWS DONE")
