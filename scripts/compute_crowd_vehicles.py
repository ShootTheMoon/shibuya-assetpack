"""Phase 1c pass 1 (system Python, no Blender): compute crowd + vehicle transforms
from the surveyed PLATEAU `tran` polygons, write 06_Placement/transforms/*.json.

Crowd  - Poisson-disk 0.75 m inside intersection polygons (fn 1020, the Scramble)
         and 1.5 m on sidewalks (fn 2000). Yaw aligned to the local crossing axis
         +/-22 deg: the directional flow is what makes a crowd read as a crowd.
Vehicles - lane centres offset (i - (n-1)/2) * 3.25 m along each roadway polygon's
         long axis, 13-19 m stochastic spacing, rejected inside intersections so
         nothing parks in the middle of the Scramble.
"""
import json, math, os, sys, random

# shibuya_placement_lib guards its bpy import, so this system-Python script can share the
# one copy of inside() / pca() instead of carrying its own (they had drifted apart in
# formatting but not behaviour - verified identical before deleting the local copies).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shibuya_placement_lib import inside, pca as long_axis, PEDESTRIANS as PEDS

SHIB = r"C:\Work\blender\Shibuya"
OUT  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transforms")
os.makedirs(OUT, exist_ok=True)
# Poisson radii tuned by measurement, not by the "0.7 m / 1.4 m" figure in the plan:
# 0.75/1.50 produced 16,647 people (~1 per 0.9 m2 = a crush). 3.4/5.2 gives ~600 in
# the Scramble and ~350 on the sidewalks, which is a busy-but-readable street.
R_CROSS, R_WALK, LANE = 3.40, 5.20, 3.25


def poly_bbox(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def poisson(pts, radius, rnd, tries=18):
    """dart-throwing inside one polygon, on a grid-accelerated occupancy set"""
    x0, y0, x1, y1 = poly_bbox(pts)
    area = max(1.0, (x1 - x0) * (y1 - y0))
    target = int(area / (radius * radius * 1.6))
    cell = radius / math.sqrt(2)
    grid = {}
    out = []
    for _ in range(target * tries):
        if len(out) >= target: break
        x = rnd.uniform(x0, x1); y = rnd.uniform(y0, y1)
        if not inside(pts, x, y): continue
        gx, gy = int(x / cell), int(y / cell)
        ok = True
        for a in range(gx - 2, gx + 3):
            for b in range(gy - 2, gy + 3):
                for px, py in grid.get((a, b), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < radius * radius:
                        ok = False; break
                if not ok: break
            if not ok: break
        if ok:
            grid.setdefault((gx, gy), []).append((x, y)); out.append((x, y))
    return out


def run(radius=200.0):
    rnd = random.Random(90210)
    T = json.load(open(os.path.join(SHIB, "tran", "tran_local.json"), encoding="utf-8"))
    polys = [p for p in T["polys"] if not p.get("elevated")]
    def near(pts):
        cx = sum(q[0] for q in pts) / len(pts); cy = sum(q[1] for q in pts) / len(pts)
        return math.hypot(cx, cy) < radius

    cross = [p for p in polys if p["kind"] == "TA" and p["fn"] == "1020" and near(p["pts"])]
    walk  = [p for p in polys if p["kind"] == "TA" and p["fn"] == "2000" and near(p["pts"])]
    road  = [p for p in polys if p["kind"] == "TA" and p["fn"] == "1000" and near(p["pts"])]

    # ---------------- crowd ----------------
    crowd = []
    for src, rad, tag in ((cross, R_CROSS, "cross"), (walk, R_WALK, "walk")):
        for p in src:
            pts = [(q[0], q[1]) for q in p["pts"]]
            if len(pts) < 3: continue
            ax, ay, _, _ = long_axis(pts)
            base = math.atan2(ay, ax)
            for (x, y) in poisson(pts, rad, rnd):
                yaw = base + rnd.choice((0.0, math.pi)) + rnd.uniform(-0.38, 0.38)
                crowd.append({"x": round(x, 3), "y": round(y, 3),
                              "yaw": round(yaw, 4), "zone": tag,
                              # randrange(12) was hardcoded while CR_Pedestrians.blend
                              # ships 18 variants, so CR_Pedestrian_12..17 were exported
                              # but never placed. place_crowd_vehicles indexes PEDS with
                              # this value, so the bound has to be the real list length.
                              "v": rnd.randrange(len(PEDS))})
    # ---------------- vehicles ----------------
    veh = []
    for p in road:
        pts = [(q[0], q[1]) for q in p["pts"]]
        if len(pts) < 3: continue
        ax, ay, cx, cy = long_axis(pts)
        nx, ny = -ay, ax
        proj = [(q[0] - cx) * ax + (q[1] - cy) * ay for q in pts]
        wid  = [(q[0] - cx) * nx + (q[1] - cy) * ny for q in pts]
        L = max(proj) - min(proj); Wd = max(wid) - min(wid)
        if L < 16.0 or Wd < 5.5: continue
        lanes = max(1, min(4, int(Wd / LANE)))
        t = min(proj) + rnd.uniform(4.0, 12.0)
        while t < max(proj) - 4.0:
            i = rnd.randrange(lanes)
            off = (i - (lanes - 1) / 2.0) * LANE
            x = cx + ax * t + nx * off
            y = cy + ay * t + ny * off
            if inside(pts, x, y) and not any(inside([(q[0], q[1]) for q in c["pts"]], x, y) for c in cross):
                yaw = math.atan2(ay, ax) + (0.0 if off >= 0 else math.pi)
                veh.append({"x": round(x, 3), "y": round(y, 3), "yaw": round(yaw, 4),
                            "lane": i, "v": rnd.randrange(4)})
            t += rnd.uniform(13.0, 19.0)

    json.dump({"crowd": crowd}, open(os.path.join(OUT, "crowd.json"), "w"), indent=0)
    json.dump({"veh": veh},     open(os.path.join(OUT, "vehicles.json"), "w"), indent=0)
    nc = sum(1 for c in crowd if c["zone"] == "cross")
    print("polygons in %d m: cross=%d walk=%d road=%d" % (radius, len(cross), len(walk), len(road)))
    print("crowd  = %d  (%d in intersections / %d on sidewalks)" % (len(crowd), nc, len(crowd) - nc))
    print("vehicles = %d" % len(veh))
    return crowd, veh


if __name__ == "__main__":
    run()
