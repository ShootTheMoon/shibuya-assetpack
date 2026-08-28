"""Re-run the scene builders against an open .blend, then save.

This is the S3 build driver, promoted out of the session scratchpad. It lived there while
v027 was assembled, which is the exact reproducibility defect this pass keeps finding -
`shibuya_geo.py`, `fetch_poi.py`'s exec() host, `build_ground.py`, the four script-less
collections. A driver that only exists in a temp folder cannot rebuild the map it built.

    blender --background <in.blend> --python rebuild_scene.py

Environment:
    SHIBUYA_REBUILD_STEPS  comma-separated script names, default = all seven
    SHIBUYA_REBUILD_OUT    output path, default = save over the input
    SHIBUYA_REBUILD_ARGS   JSON {"place_zakkyo.py": {"radius": 240.0, "limit": 280}}

build_station_hall.py runs with its repairs behind default-off flags: the proposed
segment filter deleted station columns (mi=1, 192 -> 96..168), which contradicts the
standing decision that piers and columns stay.
"""
import bpy
import json
import os
import re
import sys
import time
import traceback

PL = r"C:\Work\blender\ShibuyaAssetPack\06_Placement"
sys.path.insert(0, PL)

ALL_STEPS = ["build_viaduct.py", "build_station.py", "build_station_hall.py",
             "place_phase1a.py", "place_landmarks.py", "place_crowd_vehicles.py",
             "place_zakkyo.py"]

# ---- the finishing pass: everything that decides how the map LOOKS -------------------
# Geometry alone is not the deliverable. These eight scripts carry the appearance work and
# every one of them was applied by hand while it was being developed, which means a rebuild
# from the geometry builders alone would silently ship the old grey city. That is the same
# reproducibility defect this pass keeps finding (shibuya_geo.py, fetch_poi.py's exec host,
# build_ground.py, the four script-less collections, s3_build.py, s7_texscan.py).
#
# ORDER IS LOAD-BEARING and each dependency is real, not stylistic:
#   outskirts before ground_detail  - ground_detail inserts DET2 ahead of the FADE chain
#                                     that apply_outskirts_bake retargets
#   uv_density before facade_swap   - the swap finds its faces by the UV values the
#                                     re-projection writes (|uv| > 1.25)
#   facade_swap before enhance      - enhance skips M_FAC_* so the swap must exist first
#   massing after facade_swap       - M_OUT_* are copies of M_FAC_*, so those must exist
#   retile_ground near the end      - it DELETES SHIBUYA_GROUND and replaces it with 68
#                                     tiles, so anything that looks that object up by name
#                                     (build_outskirts_massing's ground probe, the infra
#                                     pass) has to have run already
#   lighting last                   - it repairs the compositor, and a broken compositor
#                                     renders black no matter what the materials do
FINISH = ["apply_landmark_textures.py",
          "apply_outskirts_bake.py",
          "apply_ground_detail.py",
          "fix_facade_uv_density.py",
          "apply_facade_swap.py",
          # massing after the swap: it copies M_FAC_* into the darker M_OUT_* variants
          "build_outskirts_massing.py",
          "enhance_facades.py",
          "fix_material_response.py",
          # texture_infrastructure before retile_ground: it reads SHIBUYA_GROUND's
          # collection membership, and the retiler replaces that object with 68 tiles
          "texture_infrastructure.py",
          "retile_ground.py",
          "setup_lighting.py"]

STEPS = [s.strip() for s in os.environ.get("SHIBUYA_REBUILD_STEPS", "").split(",") if s.strip()]
STEPS = STEPS or ALL_STEPS
# SHIBUYA_REBUILD_FINISH: "0" skips it, "only" runs it without the geometry builders
_fin = os.environ.get("SHIBUYA_REBUILD_FINISH", "1")
if _fin == "only":
    STEPS = []
DO_FINISH = (_fin != "0")
OUT = os.environ.get("SHIBUYA_REBUILD_OUT") or bpy.data.filepath
ARGS = json.loads(os.environ.get("SHIBUYA_REBUILD_ARGS") or "{}")

# ---- force the reduced / re-detailed masters to be re-imported ----------------------
# append_masters() (place_phase1a), link_from() (place_crowd_vehicles), load_kit()
# (place_zakkyo) and link_obj() (place_landmarks) all short-circuit on
# `if name in bpy.data.objects`, so a scene that already carries a master keeps the OLD
# mesh and the new authoring never lands. The first S4 rebuild silently reused v026's
# 16,378-tri vending machine and 32,445-tri taxi for exactly this reason. Drop the stale
# master objects and their mesh datablocks so the next append reads them off disk.
# Keyed by the script that re-imports each master. Dropping a master whose importer is not
# in STEPS would simply delete it - running only place_zakkyo.py with a flat list took both
# hero landmarks out of the scene with nothing left to put them back.
STALE_BY_STEP = {
    "place_phase1a.py": ["UP_UtilityPole_A", "SF_VendingMachine_A", "SF_TrafficSignal_A",
                         "GR_TactilePaving_Dot_A", "GR_TactilePaving_Bar_A"],
    "place_crowd_vehicles.py": ["VH_TaxiCrown_A", "VH_SedanWhite_A", "VH_SedanSilver_A",
                                "VH_SedanBlue_A"],
    "place_landmarks.py": ["LM_Shibuya109_A", "LM_ScrambleSquare_A"],
    "place_zakkyo.py": (["ZK_Storefront_Module_A", "ZK_RollerShutter_Module_A",
                         "ZK_Window_Module_A", "ZK_SignRail_Module_A",
                         "ZK_Parapet_Module_A", "ZK_Drainpipe_Module_A",
                         "ZK_ACUnit_A", "ZK_WaterTank_A", "ZK_ExternalStair_A"]
                        + ["ZK_SignboardStack_%02d" % i for i in range(40)]
                        + ["ZK_ShopFront_%d" % i for i in range(8)]),
}
STALE = tuple(n for s in STEPS for n in STALE_BY_STEP.get(s, ()))


def drop_stale():
    n = 0
    for name in STALE:
        o = bpy.data.objects.get(name)
        if o is not None:
            print("  dropping stale master object %s (mesh %r)" % (name, o.data.name))
            bpy.data.objects.remove(o, do_unlink=True)
            n += 1
    for me in list(bpy.data.meshes):
        if me.users == 0 and any(me.name == s or me.name.startswith(s + ".") for s in STALE):
            bpy.data.meshes.remove(me)
    return n


def purge_and_normalise():
    """orphan meshes left by the master swap would ship in the .blend"""
    purged = 0
    for _ in range(4):
        gone = [me for me in bpy.data.meshes if me.users == 0]
        if not gone:
            break
        for me in gone:
            bpy.data.meshes.remove(me)
            purged += 1
    # Strip .NNN suffixes now the stale datablocks are gone. The old mesh still had users
    # when its master object was dropped, so the fresh append collided and landed as
    # UP_UtilityPole_A.002 - and shibuya_export_v2.classify() buckets on o.data.name, so a
    # suffix mis-sorts the asset in the delivered pack.
    renamed = 0
    for me in sorted(bpy.data.meshes, key=lambda m: m.name):
        m = re.match(r"^(.*)\.\d{3}$", me.name)
        if m and m.group(1) not in bpy.data.meshes:
            print("  renaming mesh %s -> %s" % (me.name, m.group(1)))
            me.name = m.group(1)
            renamed += 1
    print("\npurged %d orphan meshes, normalised %d names" % (purged, renamed))


def main():
    print("=== rebuild: %s" % ", ".join(STEPS))
    print("  dropped %d stale masters" % drop_stale())
    raised = []
    for scr in STEPS:
        t0 = time.time()
        print("\n===== %s =====" % scr, flush=True)
        ns = {}
        try:
            exec(compile(open(os.path.join(PL, scr), encoding="utf-8").read(), scr, "exec"), ns)
            ns["run"](**ARGS.get(scr, {}))
        except Exception as ex:
            traceback.print_exc()
            raised.append("%s:%s" % (scr, type(ex).__name__))
        print("  (%.0fs)" % (time.time()-t0), flush=True)
    if raised:
        print("\n!! RAISED: %s  -- NOT SAVING" % ", ".join(raised))
        raise SystemExit(1)

    if DO_FINISH:
        print("\n===== finishing pass (%d scripts) =====" % len(FINISH))
        for scr in FINISH:
            t0 = time.time()
            print("\n--- %s" % scr, flush=True)
            ns = {}
            try:
                exec(compile(open(os.path.join(PL, scr), encoding="utf-8").read(),
                             scr, "exec"), ns)
                ns["run"](**ARGS.get(scr, {}))
            except Exception as ex:
                traceback.print_exc()
                raised.append("%s:%s" % (scr, type(ex).__name__))
            print("  (%.0fs)" % (time.time()-t0), flush=True)
        if raised:
            print("\n!! RAISED in finishing pass: %s  -- NOT SAVING" % ", ".join(raised))
            raise SystemExit(1)
        # A compositor whose Group Output is unconnected renders every frame black, and it
        # got saved into a .blend that way once already. Check the delivered state, not the
        # intent - setup_lighting repairs it, so reaching here with it still broken means
        # the repair itself regressed.
        g = getattr(bpy.context.scene, "compositing_node_group", None)
        if g is not None:
            out = next((n for n in g.nodes if n.type == 'GROUP_OUTPUT'), None)
            if out is not None and not out.inputs[0].links:
                print("\n!! compositor Group Output is UNCONNECTED - would render black. "
                      "NOT SAVING")
                raise SystemExit(1)
            print("  compositor output connected: OK")

    purge_and_normalise()
    bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=False)
    print("\nSAVED %s  %.1f MB" % (OUT, os.path.getsize(OUT)/1048576.0))
    print("REBUILD OK")


if __name__ == "__main__":
    main()
