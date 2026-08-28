"""S5-2: raise zakkyo sign variety from 24 stack meshes to 40. Costs ZERO screen triangles.

Correction to the plan, measured: the atlas is NOT under-used at the cell level - 53 of its
64 cells are already reached, only 11 are untouched. What is scarce is DISTINCT MESHES: 24
of them carry roughly 5,000 placed stacks, so one stack silhouette repeats ~208 times.

Adding meshes does not add instances - place_zakkyo puts a stack on 62% of upper floors
regardless of how many variants exist - so this is pure variety at a fixed screen cost. The
authored cost is 16 x 60 = 960 triangles in the library.

New stacks recombine cells, drawing the 11 unused ones first and then the least-reused, so
the added variants are genuinely new rather than reshuffles of the popular cells.
"""
import bpy
import collections

COLS, ROWS = 4, 16
N_NEW = 16
FIRST_NEW = 24


def cell_of(u, v):
    c = min(COLS-1, max(0, int(u*COLS)))
    r = min(ROWS-1, max(0, int((1.0-v)*ROWS)))
    return r*COLS + c


def cell_uv(k):
    """-> (u0, v0, u1, v1) of cell k, matching make_sign_atlas.py's layout"""
    c, r = k % COLS, k // COLS
    return (c/COLS, 1.0-(r+1)/ROWS, (c+1)/COLS, 1.0-r/ROWS)


def survey():
    use = collections.Counter()
    stacks = []
    for ob in bpy.data.objects:
        if not ob.name.startswith("ZK_SignboardStack_"):
            continue
        stacks.append(ob)
        me = ob.data
        atlas = {i for i, m in enumerate(me.materials) if m and "SignAtlas" in m.name}
        uv = me.uv_layers[0].uv
        for p in me.polygons:
            if p.material_index not in atlas:
                continue
            us = [uv[li].vector[0] for li in p.loop_indices]
            vs = [uv[li].vector[1] for li in p.loop_indices]
            use[cell_of(sum(us)/len(us), sum(vs)/len(vs))] += 1
    return stacks, use


def retarget(me, cells):
    """Rewrite every atlas-material face onto the given cells, preserving the quad's
    orientation (u increases left->right, v bottom->top within the cell)."""
    atlas = {i for i, m in enumerate(me.materials) if m and "SignAtlas" in m.name}
    uv = me.uv_layers[0].uv
    faces = [p for p in me.polygons if p.material_index in atlas]
    for j, p in enumerate(faces):
        u0, v0, u1, v1 = cell_uv(cells[j % len(cells)])
        # keep a 1-texel inset so bilinear filtering cannot bleed the neighbouring cell
        du, dv = (u1-u0)*0.002, (v1-v0)*0.008
        us = [uv[li].vector[0] for li in p.loop_indices]
        vs = [uv[li].vector[1] for li in p.loop_indices]
        umin, umax = min(us), max(us)
        vmin, vmax = min(vs), max(vs)
        for li in p.loop_indices:
            a = uv[li].vector
            fu = 0.0 if umax - umin < 1e-9 else (a[0]-umin)/(umax-umin)
            fv = 0.0 if vmax - vmin < 1e-9 else (a[1]-vmin)/(vmax-vmin)
            uv[li].vector = (u0+du + fu*((u1-du)-(u0+du)),
                             v0+dv + fv*((v1-dv)-(v0+dv)))


def run():
    stacks, use = survey()
    stacks.sort(key=lambda o: o.name)
    unused = [k for k in range(COLS*ROWS) if k not in use]
    ranked = unused + [k for k, _ in sorted(use.items(), key=lambda kv: kv[1])]
    print("  %d existing stacks | %d/%d cells reached | %d unused: %s"
          % (len(stacks), len(use), COLS*ROWS, len(unused), unused))

    col = stacks[0].users_collection[0] if stacks[0].users_collection else \
        bpy.context.scene.collection
    made = []
    ptr = 0
    for i in range(N_NEW):
        idx = FIRST_NEW + i
        name = "ZK_SignboardStack_%02d" % idx
        if name in bpy.data.objects:
            print("      %s already exists - skipped" % name); continue
        # cycle the three template meshes so the new variants inherit the same spread of
        # M_ZK_SignAtlas / _B / _C (they differ by hue shift, so this keeps colour variety)
        src = stacks[i % 3]
        me = src.data.copy()
        me.name = name
        cells = []
        while len(cells) < 5:
            c = ranked[ptr % len(ranked)]
            ptr += 1
            if c not in cells:
                cells.append(c)
        retarget(me, cells)
        ob = bpy.data.objects.new(name, me)
        col.objects.link(ob)
        ob.hide_render = True
        ob.hide_viewport = True
        made.append((name, src.name, cells))
        print("      %-24s from %-24s cells=%s" % (name, src.name, cells))
    print("  created %d new stack meshes (%d authored tris, 0 screen tris)"
          % (len(made), len(made)*60))
    return made


if globals().get("__name__") == "__main__":
    run()
    bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath, compress=True)
    print("S5 EXPAND KIT DONE")
