"""S5-3: put real geometry on the two zakkyo modules the camera gets closest to.

ZK_ShopFront_* is 46 triangles on a 2.92 x 2.70 m lit storefront - 5.6 tris/m2, the lowest
density in the pack - and it is the surface a 1.7 m camera stands right in front of at
night. ZK_Parapet_Module_A is 24 triangles of flat coping read against the sky.

What is added is silhouette, not texture detail: an awning with a fascia, a doorway sill,
and glazing mullions on the shopfront; a coping overhang with a drip edge on the parapet.
Those are the parts that catch a light and break a flat rectangle.

Deliberately NOT raised (instance counts from the current build - these multiply):
    ZK_SignRail_Module_A    48 tris x 8,926   ZK_Window_Module_A     36 x 2,095
    ZK_Storefront_Module_A  72 tris x 1,657   ZK_SignboardStack_*    60 x ~5,000
"""
import bpy
import bmesh


def box(bm, uvl, mi, cx, cy, cz, sx, sy, sz):
    """axis-aligned box centred at (cx,cy,cz) with full sizes (sx,sy,sz) -> 12 tris"""
    r = bmesh.ops.create_cube(bm, size=1.0)
    vs = r["verts"]
    for v in vs:
        v.co.x = v.co.x*sx + cx
        v.co.y = v.co.y*sy + cy
        v.co.z = v.co.z*sz + cz
    for f in bm.faces:
        if all(v in vs for v in f.verts):
            f.material_index = mi
            for l in f.loops:
                l[uvl].uv = (0.001, 0.999)
    return vs


def bounds(me):
    vs = me.vertices
    return ([min(v.co[i] for v in vs) for i in range(3)],
            [max(v.co[i] for v in vs) for i in range(3)])


def frame_slot(me, want=("M_ZK_Frame", "M_ZK_Metal", "M_ZK_Concrete")):
    for w in want:
        for i, m in enumerate(me.materials):
            if m and m.name == w:
                return i
    return 0


def detail_shopfront(ob):
    me = ob.data
    mn, mx = bounds(me)
    W = mx[0]-mn[0]
    H = mx[2]-mn[2]
    yo = mx[1]                     # outward face: modules are yawed so local +Y is outward
    mi = frame_slot(me)
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.verify()
    cx = (mn[0]+mx[0])/2

    # awning: a slab projecting over the entrance, plus a fascia board hanging off its lip
    az = mn[2] + H*0.80
    box(bm, uvl, mi, cx, yo+0.22, az,             W*0.96, 0.44, 0.07)   # canopy slab
    box(bm, uvl, mi, cx, yo+0.43, az-0.13,        W*0.96, 0.05, 0.26)   # fascia
    box(bm, uvl, mi, cx-W*0.46, yo+0.22, az-0.10, 0.05,   0.44, 0.20)   # end cheeks
    box(bm, uvl, mi, cx+W*0.46, yo+0.22, az-0.10, 0.05,   0.44, 0.20)
    # sill / step at the threshold
    box(bm, uvl, mi, cx, yo+0.06, mn[2]+0.045,    W*0.98, 0.20, 0.09)
    # glazing mullions
    for f in (-0.30, 0.0, 0.30):
        box(bm, uvl, mi, cx + W*f, yo+0.02, mn[2]+H*0.42, 0.055, 0.05, H*0.62)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    return me


def detail_parapet(ob):
    me = ob.data
    mn, mx = bounds(me)
    W = mx[0]-mn[0]
    D = mx[1]-mn[1]
    mi = frame_slot(me, ("M_ZK_Concrete", "M_ZK_Frame"))
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.verify()
    cx = (mn[0]+mx[0])/2
    cy = (mn[1]+mx[1])/2
    # coping cap that oversails both faces, then a drip edge under the outer lip
    box(bm, uvl, mi, cx, cy, mx[2]+0.035, W*1.01, D*1.35, 0.07)
    box(bm, uvl, mi, cx, cy + D*0.62, mx[2]-0.035, W*1.01, 0.045, 0.05)
    box(bm, uvl, mi, cx, cy - D*0.62, mx[2]-0.035, W*1.01, 0.045, 0.05)
    # a recessed band so the face is not one flat rectangle
    box(bm, uvl, mi, cx, cy + D*0.50, mn[2]+(mx[2]-mn[2])*0.35, W*0.97, 0.03, 0.10)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    return me


def run():
    done = []
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or not ob.data.polygons:
            continue
        before = sum(len(p.vertices)-2 for p in ob.data.polygons)
        if ob.name.startswith("ZK_ShopFront_"):
            if before > 120:
                print("      %s already detailed (%d tris)" % (ob.name, before)); continue
            detail_shopfront(ob)
        elif ob.name == "ZK_Parapet_Module_A":
            if before > 60:
                print("      %s already detailed (%d tris)" % (ob.name, before)); continue
            detail_parapet(ob)
        else:
            continue
        after = sum(len(p.vertices)-2 for p in ob.data.polygons)
        done.append((ob.name, before, after))
        print("      %-24s %4d -> %4d tris" % (ob.name, before, after))
    print("  detailed %d module(s)" % len(done))
    return done


if globals().get("__name__") == "__main__":
    run()
    bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath, compress=True)
    print("S5 DETAIL MODULES DONE")
