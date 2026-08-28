"""S6: pack deliverable cleanup. System Python - no Blender needed.

Every action here is justified by a measurement, and two of them CONTRADICT the plan:

1. The plan said to delete the "truncated" filename of each md5-identical pair. Measured
   the other way round: SF_VendingMachine_A.blend references
   SF_VendingMachine_A_JIHANKI_ATLAS_GLAS.png and ..._EMISSION_e.png - the SHORT names -
   so it is the LONG ones (..._GLASS_.png, ..._EMISSION_emi.png) that nothing points at.
   Deleting by the plan's rule would have broken the material.

2. The plan said to bring 03_Textures to <=512. Two problems with that:
   - ZK_SignAtlas / ZK_ShopAtlas are LINKED, not packed (verified), so rewriting them on
     disk changes what ZK_FacadeKit.blend renders. The 64-cell sign atlas at 512 would turn
     every Japanese sign to mush - which is exactly why shibuya_export_v2.KEEP_1024 exists.
   - 03_Textures is the AUTHORING source. OVERDARE's 512 guidance applies to what ships,
     and shibuya_export_v2.prep_image already writes EX_*.png at <=512 for delivery.
   So the source is left intact and audit_map now measures the DELIVERED textures instead.
   Degrading the source would have lost resolution for no delivery benefit.
"""
import hashlib
import os
import shutil

PACK = r"C:\Work\blender\ShibuyaAssetPack"
DEP = r"C:\Work\MeshTest\_deprecated\shibuya_pack_debris"

# verified by reading the .blend: these are the names NOTHING references
UNREFERENCED_DUPES = [
    r"03_Textures\SF_Street_Furniture\SF_VendingMachine_A_JIHANKI_ATLAS_GLASS_.png",
    r"03_Textures\SF_Street_Furniture\SF_VendingMachine_A_JIHANKI_EMISSION_emi.png",
]

DEBUG_ARTEFACTS = [
    r"03_Textures\ZK_Zakkyo_Facade_Kit\_check.png",
    r"03_Textures\ZK_Zakkyo_Facade_Kit\_chk_shops.png",
    r"03_Textures\ZK_Zakkyo_Facade_Kit\_chk_signs.png",
]

REJECTED_README = """# 07_Rejected

**This folder is intentionally empty. The evidence lives in
[`../05_Documentation/REJECTIONS.md`](../05_Documentation/REJECTIONS.md).**

Berlin's pack kept rejected downloads here so a later pass would not re-evaluate the same
asset twice. That does not transfer to Shibuya, because the two things that got rejected
here are not re-downloadable in any useful sense:

* **Oversized photogrammetry.** The utility-pole candidate was 903k faces and the whole-area
  scans were 2.19 M. Keeping a copy costs gigabytes to save a search that takes a minute,
  and the reason for rejection (torn geometry, floating cable shards, its own baked ground)
  is a property of the asset that will not change.
* **Metadata-only rejections.** Most candidates were rejected from the listing - wrong
  region, wrong style, incompatible licence - and were never downloaded at all, so there is
  nothing to file.

`REJECTIONS.md` records each rejection with its Sketchfab UID, face count, licence and the
measured reason. Where a preview was captured before rejection it is named there; where no
preview survives, that is stated rather than implied.

Do not delete this file - an empty folder with no explanation reads as an unfinished
deliverable, which is what it was before v027.
"""


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def run(apply=True):
    os.makedirs(DEP, exist_ok=True)
    freed = 0
    acted = []

    # --- 1. md5-identical textures that nothing references -------------------------
    for rel in UNREFERENCED_DUPES:
        p = os.path.join(PACK, rel)
        if not os.path.exists(p):
            print("  dupe already gone: %s" % os.path.basename(rel)); continue
        sz = os.path.getsize(p)
        if apply:
            shutil.move(p, os.path.join(DEP, os.path.basename(p)))
        freed += sz
        acted.append(("dupe", rel, sz))
        print("  dupe   -> _deprecated  %-52s %6.0f KB" % (os.path.basename(rel), sz/1024))

    # --- 2. debug artefacts shipped inside the pack --------------------------------
    for rel in DEBUG_ARTEFACTS:
        p = os.path.join(PACK, rel)
        if not os.path.exists(p):
            continue
        sz = os.path.getsize(p)
        if apply:
            shutil.move(p, os.path.join(DEP, os.path.basename(p)))
        freed += sz
        acted.append(("debug", rel, sz))
        print("  debug  -> _deprecated  %-52s %6.0f KB" % (os.path.basename(rel), sz/1024))

    # --- 3. Blender auto-backups (.blend1) are not deliverables ---------------------
    for root, _, names in os.walk(PACK):
        for n in names:
            if not n.endswith(".blend1"):
                continue
            p = os.path.join(root, n)
            sz = os.path.getsize(p)
            if apply:
                os.remove(p)
            freed += sz
            acted.append(("blend1", os.path.relpath(p, PACK), sz))
            print("  .blend1 removed        %-52s %6.0f KB" % (n, sz/1024))

    # --- 4. 07_Rejected: say why it is empty ---------------------------------------
    rp = os.path.join(PACK, "07_Rejected", "README.md")
    if apply:
        os.makedirs(os.path.dirname(rp), exist_ok=True)
        with open(rp, "w", encoding="utf-8", newline="\n") as f:
            f.write(REJECTED_README)
    print("  wrote 07_Rejected/README.md")

    # --- 5. report the texture inventory, do NOT rewrite it ------------------------
    import struct
    big = []
    for root, _, names in os.walk(os.path.join(PACK, "03_Textures")):
        for n in names:
            if not n.lower().endswith(".png"):
                continue
            p = os.path.join(root, n)
            with open(p, "rb") as f:
                head = f.read(26)
            if head[:8] != b"\x89PNG\r\n\x1a\n":
                continue
            w, h = struct.unpack(">II", head[16:24])
            if max(w, h) > 512:
                big.append((max(w, h), os.path.relpath(p, PACK)))
    big.sort(reverse=True)
    print("\n  authoring textures over 512 px: %d (source kept on purpose - see docstring)"
          % len(big))
    for px, rel in big[:6]:
        print("      %5d px  %s" % (px, rel))

    print("\n  freed %.2f MB, %d file(s) actioned" % (freed/1048576.0, len(acted)))
    return acted


if __name__ == "__main__":
    run(apply=True)
    print("S6 PACK CLEANUP DONE")
