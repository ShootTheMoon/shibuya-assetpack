"""Shared geometry validation for every Shibuya placement/builder script.

Why this file exists
--------------------
The zakkyo pass was re-run five times chasing "floating in the air" and "overlapping"
reports. Only two of those rounds were real placer bugs; the rest were defects in the
CHECKING code, and they were only possible because the same helper existed three or four
times with different behaviour:

  * `inside` / `_inside`      three copies (build_viaduct, audit_placement, build_station)
  * `pca` / `long_axis`       three copies with different names
  * `family`                  two copies
  * `level_of`                two copies, one of which lost the underground exclusion
  * ground probing            four silent fallbacks (`15.0` once, `0.0` three times)

So the rule here is: ONE implementation, and probes that MISS return `None` rather than
inventing a height. A silent `0.0` puts a prop 15 m under the valley floor; a silent
`15.0` puts it 15 m in the air over the outskirts. Both read as "floating object" and
neither leaves a trace in a log.

Two signatures are deliberately awkward, because making them convenient is what caused
real bugs:

  * `roof_min(bvh, ...)` takes its BVH as a positional argument with NO default. Callers
    need the building being dressed, not the combined one - probed against every
    building, a low block with a tower behind it reports the TOWER's roof (at
    (264.4, -21.2) all four probes hit Hikarie at 199 m while the roof there is 35 m).
  * `level_of()` returns `(level, underground)` instead of `None` for underground. The
    station builder must drop subway ways; the hall builder compares `lv == 2`/`lv >= 3`
    and would raise on a `None`.

NOT moved here on purpose: `split_turns` / `plen` from `Shibuya\bake\rasterise_ground.py`.
That script runs in SYSTEM Python (PIL + numpy, no bpy), the two functions have no second
copy anywhere, and importing this module would break the 8192 ground bake.

Import with (alias SPL, never L - `L` is a local edge/segment length in four of the
callers, and a local assignment anywhere in a function shadows the module for the whole
function body, so `import ... as L` raises UnboundLocalError on the first lib call):

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import shibuya_placement_lib as SPL
"""
import math
import collections

try:
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    HAVE_BPY = True
except ImportError:                     # importable from system Python for the pure maths
    HAVE_BPY = False

BLDG_PREFIX = ("SHIBUYA_BLDG__", "LM_")

# CR_Pedestrians.blend ships 18 variants. compute_crowd_vehicles.py (system Python) picked a
# variant with a hardcoded randrange(12) while place_crowd_vehicles.py (Blender) indexed an
# 18-long list, so CR_Pedestrian_12..17 were exported in the pack and never once placed.
# The roster lives here because it is pure data and both sides can import it - the compute
# pass has no bpy, so it cannot import the placer.
PEDESTRIANS = ["CR_Pedestrian_%02d" % i for i in range(18)]


# --------------------------------------------------------------------------- pure maths
def inside(pts, x, y):
    """point-in-polygon, odd crossings along +X. From build_viaduct.py:45-51; the two
    other copies (audit_placement._inside, and the inline test in build_station) were
    identical and are deleted."""
    c = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i][0], pts[i][1]
        x2, y2 = pts[(i+1) % n][0], pts[(i+1) % n][1]
        if (y1 > y) != (y2 > y) and x < x1 + (y-y1)/(y2-y1)*(x2-x1):
            c = not c
    return c


def pca(pts):
    """principal axis of a 2D point cloud -> (ax, ay, cx, cy), unit direction + centroid.
    Was `pca` in build_station_hall.py:59-66 and `long_axis` in build_viaduct.py:35-42 -
    same maths, two names."""
    cx = sum(p[0] for p in pts)/len(pts)
    cy = sum(p[1] for p in pts)/len(pts)
    sxx = syy = sxy = 0.0
    for p in pts:
        dx, dy = p[0]-cx, p[1]-cy
        sxx += dx*dx; syy += dy*dy; sxy += dx*dy
    th = 0.5*math.atan2(2*sxy, sxx-syy)
    return math.cos(th), math.sin(th), cx, cy


def level_of(t):
    """OSM level/layer -> (storey, underground).

    Shibuya's JR platforms are level=2 (elevated on a viaduct) and the four subway lines
    are level -3..-5; draping everything at grade put platform slabs across streets, so
    this is not cosmetic. build_station.py returned None for underground and
    build_station_hall.py did not - returning the pair keeps both callers honest."""
    for k in ("level", "layer"):
        v = t.get(k)
        if v is None:
            continue
        try:
            n = float(str(v).split(';')[0])
        except ValueError:
            continue
        return n, (n < 0)
    return 0.0, False


FAMILY = (("ZK_SignboardStack", "SIGN"), ("ZK_ShopFront", "SHOP"))


def family(mod):
    """Dedup key for zakkyo modules. Keying on the module NAME let two different
    signboard variants share one cell - 7,339 surplus instances (25.3%) got through that
    way. Storefront+ShopFront and SignRail+SignboardStack are different families and are
    meant to coexist, so they still can."""
    for pre, fam in FAMILY:
        if mod.startswith(pre):
            return fam
    return mod


class Occupancy:
    """Cell-bucketed radius rejection. `cell` defaults to `radius`, which is what makes
    the 3x3 neighbourhood scan complete - a smaller cell than the radius would miss
    neighbours two cells away. Replaces the free/mark pair in place_phase1a.py:85-93 and
    the free2/occ2 pair at :193-197."""

    def __init__(self, radius, cell=None):
        self.r2 = float(radius)*float(radius)
        self.cell = float(cell) if cell else max(float(radius), 1e-6)
        self.b = {}

    def free(self, x, y):
        kx, ky = int(x//self.cell), int(y//self.cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for (px, py) in self.b.get((kx+dx, ky+dy), ()):
                    if (px-x)**2 + (py-y)**2 < self.r2:
                        return False
        return True

    def mark(self, x, y):
        self.b.setdefault((int(x//self.cell), int(y//self.cell)), []).append((x, y))

    def try_mark(self, x, y):
        if not self.free(x, y):
            return False
        self.mark(x, y)
        return True

    def __len__(self):
        return sum(len(v) for v in self.b.values())


# ------------------------------------------------------------------ scene / BVH helpers
def buildings(require_faces=True, include_retired=True):
    """The canonical building list. Four scripts each rebuilt this filter inline.

    `include_retired` defaults to True to match what those four inline filters did: they
    matched on the LM_ prefix alone, so the superseded PLATEAU boxes parked in
    MAP_SHIBUYA_LM_ORIG (109, Hachiko, Scramble Square) went into the wall BVH too. That
    is almost certainly wrong - it puts a second solid at the same coordinates as the
    hand-modelled replacement - but flipping it changes placement output, so it is an
    explicit opt-out rather than a silent improvement here."""
    out = []
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or not ob.data.vertices:
            continue
        if require_faces and not ob.data.polygons:
            continue
        if not ob.name.startswith(BLDG_PREFIX):
            continue
        if not include_retired and any(c.name == "MAP_SHIBUYA_LM_ORIG"
                                       for c in ob.users_collection):
            continue
        out.append(ob)
    return out


def tri_soup(objs):
    """World-space triangle soup -> (verts, tris, mat_index_per_tri).

    BVHTree.FromObject fails on these meshes in this build, so the triangles are
    assembled by hand (place_zakkyo.py:76-87). The per-triangle material index is what
    lets the audit bucket intersections - the user's call was that station columns and
    viaduct piers legitimately share walls with buildings, so those material indices are
    whitelisted while deck/ribbon/slab indices stay hard failures."""
    vv = []
    pp = []
    mm = []
    for ob in objs:
        Mw = ob.matrix_world
        base = len(vv)
        vv.extend([Mw @ v.co for v in ob.data.vertices])
        for pl in ob.data.polygons:
            idx = [base + k for k in pl.vertices]
            for k in range(1, len(idx)-1):
                pp.append((idx[0], idx[k], idx[k+1]))
                mm.append(pl.material_index)
    return vv, pp, mm


def make_bvh(objs):
    """-> (BVHTree, n_tris). Same signature the existing call sites already use."""
    vv, pp, _ = tri_soup(objs)
    return BVHTree.FromPolygons(vv, pp), len(pp)


def overlap_tris(a_objs, b_objs):
    """Exact triangle intersection of A against B, bucketed by A's material index.

    BVHTree.overlap() is a real intersection test, unlike the odd-crossing parity check
    which overcounts by 5.7x. Returns per-material hit/total so a whitelist can be
    applied to piers and columns without hiding a regression in the deck."""
    av, at, am = tri_soup(a_objs)
    bv, bt, _ = tri_soup(b_objs)
    if not at or not bt:
        return dict(total=len(at), hit=0, per_mat={}, tot_per_mat={})
    A = BVHTree.FromPolygons(av, at)
    B = BVHTree.FromPolygons(bv, bt)
    hit = set(i for i, _ in A.overlap(B))
    return dict(total=len(at), hit=len(hit),
                per_mat=dict(collections.Counter(am[i] for i in hit)),
                tot_per_mat=dict(collections.Counter(am)))


class GroundSampler:
    """SHIBUYA_GROUND height probe that returns None on a miss and counts the misses.

    The four silent fallbacks this replaces were invisible in every log:
      place_phase1a.py:46      -> 15.0   (prop hangs 15 m up over the outskirts)
      place_landmarks.py:51    -> 0.0    (landmark 15 m under the valley floor)
      build_station_hall.py:94 -> 0.0
      build_viaduct.py:63      -> 0.0
    Call report() at the end of every run: 0 is the expected miss count, and anything
    else is an xy worth looking at rather than a number to shrug at."""

    def __init__(self, name="SHIBUYA_GROUND", top=500.0):
        g = bpy.data.objects.get(name)
        if g is None:
            raise KeyError("%s not in the scene" % name)
        # FromObject works for the single ground mesh; it is only the multi-object
        # building soup that it fails on.
        self.tree = BVHTree.FromObject(g, bpy.context.evaluated_depsgraph_get())
        self.top = float(top)
        self.hit = 0
        self.miss = 0
        self.misses = []

    def z(self, x, y):
        h = self.tree.ray_cast(Vector((x, y, self.top)), Vector((0, 0, -1)))
        if h[0] is None:
            self.miss += 1
            if len(self.misses) < 20:
                self.misses.append((round(x, 1), round(y, 1)))
            return None
        self.hit += 1
        return h[0].z

    def report(self, label=""):
        print("  ground probe %-18s %d hit / %d MISS%s"
              % (label, self.hit, self.miss,
                 ("  first: " + repr(self.misses)) if self.miss else ""))
        return self.miss


# ------------------------------------------------------------- building surface queries
def roof_at(bvh, x, y, top=500.0):
    """Height of the first surface directly above (x, y), or None."""
    h = bvh.ray_cast(Vector((x, y, top)), Vector((0, 0, -1)))
    return h[0].z if h[0] else None


def roof_min(bvh, x, y, nx, ny, offs=(0.3, 0.6, 1.2, 2.0)):
    """Lowest roof over several probes stepped INWARD from the wall - the minimum, not
    one sample.

    A single probe 0.6 m inside overshoots where the facade leans in or the upper floors
    step back: it lands on the tall part while the wall being dressed stops much lower.
    That left 323 modules up to 26.9 m above their own roof.

    `bvh` is positional with no default on purpose. It MUST be the building being
    dressed. Probed against the combined soup, a low block with a tower pressed against
    its back wall reports the tower's roof - at (264.4, -21.2) all four probes hit
    Hikarie at 199 m while the actual roof is 35 m, and the parapet went 165 m up."""
    vals = [roof_at(bvh, x - nx*d, y - ny*d) for d in offs]
    vals = [v for v in vals if v is not None]
    return min(vals) if vals else None


def roof_max(bvh, x, y, ix, iy, offs=(0.0, 1.0, 2.0, 3.0)):
    """Highest roof over inward probes - the AUDIT counterpart of roof_min.

    Auditing straight up from the instance hits whatever projects furthest out, and
    PLATEAU bundles low canopies with tall main blocks in one object: at (35.5, 107.7)
    the probe found a 20.3 m canopy lip while the wall 2 m behind rises to 46.9 m, so a
    sign correctly hung at 45.9 m was reported 25.6 m above its roof (124 false
    positives). Placement wants the conservative minimum, auditing wants the maximum."""
    best = None
    for d in offs:
        z = roof_at(bvh, x + ix*d, y + iy*d)
        if z is not None and (best is None or z > best):
            best = z
    return best


def wall_at(bvh, x, y, z, nx, ny, reach=2.2):
    """Cast inward from 1 m outside the point; a real wall answers within `reach`.

    A footprint edge is not proof of a wall: LOD2 carries decks, canopies and overhangs
    near the ground and adjacent buildings each own the shared party wall, so
    edge-following alone put 2,701 modules in open space, up to 29.6 m from anything."""
    o = Vector((x + nx*1.0, y + ny*1.0, z))
    return bvh.ray_cast(o, Vector((-nx, -ny, 0.0)), reach)[0] is not None


def in_building(bvh, x, y, z, casts=12, reach=400.0):
    """Odd number of crossings along +X means the point is inside a solid.

    Necessary but NOT sufficient - see enclosed(). On its own this reports 17% of zakkyo
    modules as buried when the real figure is 3.0%."""
    n = 0
    ox = x
    for _ in range(casts):
        h = bvh.ray_cast(Vector((ox, y, z)), Vector((1.0, 0.0, 0.0)), reach)
        if h[0] is None:
            break
        n += 1
        ox = h[0].x + 0.01
    return n % 2 == 1


def enclosed(bvh, x, y, z, clearance=1.0, dirs=12, reach=8.0):
    """Really walled in: inside by parity AND no horizontal escape.

    Parity alone flagged 17% of the zakkyo instances. Casting outward showed that of a
    421-instance sample only 74 (3.0% of the map) are actually trapped; the rest have an
    open frontage with a median 1.22 m of clearance - they are shopfronts sitting in the
    facade recess, which is correct. Requiring BOTH is what stops a containment fix from
    deleting good geometry."""
    if not in_building(bvh, x, y, z, reach=reach*50):
        return False
    o = Vector((x, y, z))
    for k in range(dirs):
        a = 2*math.pi*k/dirs
        h = bvh.ray_cast(o, Vector((math.cos(a), math.sin(a), 0.0)), reach)
        if h[0] is None:
            return False                              # this ray escapes
        if (h[0] - o).length > clearance:
            return False                              # open space in this direction
    return True
