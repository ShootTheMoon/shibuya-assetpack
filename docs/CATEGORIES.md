# Category register

The pack declared **12** category prefixes. Eight carry assets; four were promises. This
file resolves all twelve, because a declared-but-empty folder reads as unfinished work when
in two of these cases the thing genuinely exists and in the other two it should never have
been declared.

Counts are measured from the `.blend` files by `06_Placement/s6_manifest.py`, not carried
over from the previous manifest — that one listed every `CR_Pedestrian` as exactly 570
triangles when the real range is 524–648, i.e. it was a placeholder, not a measurement.

## Carrying assets (8)

| Prefix | Folder | Assets | Notes |
|---|---|---|---|
| `UP_` | `UP_Utility_Overhead` | 2 | Pole textured in v027 S5 (it had no UV layer at all). 274 instances. |
| `SF_` | `SF_Street_Furniture` | 3 | Vending machine and signal decimated in v027 S4. |
| `GR_` | `GR_Ground_Detail` | 2 | Dot tile 912 → 60 tris; only the Bar variant is placed. |
| `ZK_` | `ZK_Zakkyo_Facade_Kit` | 57 | +16 signboard variants in S5; the 40 now reach all 64 atlas cells. |
| `VH_` | `VH_Vehicles` | 4 | Taxi + 3 sedans, four separate mesh datablocks (see below). |
| `CR_` | `CR_Crowd` | 18 | Exported but **not placed** — the map ships without a crowd on purpose. |
| `VG_` | `VG_Vegetation` | 1 | 45 instances. |
| `LM_` | `LM_Landmarks` | 4 | 109, Hachiko, Aogaeru, Scramble Square. |

## Resolved promises (4)

### `ST_Station_Rail` — EXISTS, but as builders, not assets
`SHIBUYA_STATION` (10,698 tris), `SHIBUYA_STATION_HALL` (368) and `SHIBUYA_VIADUCT` (1,900)
are real, shipped geometry. They are **procedural**: single meshes generated from OSM
railway ways and PLATEAU `tran` polygons by `06_Placement/build_station.py`,
`build_station_hall.py` and `build_viaduct.py`. There is no authored `.blend` to put in a
category folder and there should not be — the geometry is a function of the geodata, and
freezing it into an asset would break the moment the extract is refreshed.

They are absent from `asset_manifest.csv` for the same reason: that manifest describes
authored assets with an FBX/GLB export path per row. Their delivery is by map collection
(`11_STATION`, `09_VIADUCT` in `shibuya_export_v2.STATIC_FOLDER`), not per asset.

### `SC_Scramble_Landmarks` — folded into `LM_Landmarks`
`LM_ScrambleSquare_A` (18,250 tris) is the only asset this category was ever going to hold,
and `place_landmarks.py` loads all four landmarks from one directory. A second folder holding one file, with a second code path to
find it, is worse than the `LM_` prefix it already carries. **Category retired.**

### `PR_Props_Clutter` — NOT BUILT, promise withdrawn
A-boards, bicycles, bollards and ground-level AC units: 8–10 props at ≤300 triangles,
estimated ~120,000 on screen. The v027 budget could afford it — S4 recovered 4.25 M and S5
spent under 0.2 M of it — but it is new asset authoring, not the cleanup pass this version
is, and shipping the folder empty implies otherwise. **Withdrawn, not deferred**: if it is
wanted it should be scoped as its own piece of work with its own review.

### `SG_Signage_Neon` — SUPERSEDED, do not build
The geometry this category was for already exists twice over: the `ZK_` kit provides
`ZK_SignboardStack_00..39` and `ZK_SignRail_Module_A` (8,926 placed rails), and the
procedural `MAP_SHIBUYA_NEON` carries 3,808 emissive sign polygons in 8 colour-merged
meshes. Building a third source would fragment the same 4096 sign atlas across three
pipelines. **Retired.**

Note for whoever wires the night preset: all 8 `MAP_SHIBUYA_NEON` meshes currently sit at
emission strength **0.0** — the map is in its day configuration, and the night preset raises
them. That switch has no script (see the reproducibility note in the v027 plan).

## Vehicle variants are four datablocks on purpose

`VH_TaxiCrown_A`, `VH_SedanWhite_A`, `VH_SedanSilver_A`, `VH_SedanBlue_A` share the reduced
Crown Comfort bodyshell and differ by colour, ±1.5% length, and the andon roof lamp (taxi
only). They are separate **mesh datablocks** rather than one mesh with four materials
because `shibuya_export_v2.classify()` keys on `o.data.name`; material-only variants would
collapse into a single export entry and the variety would never reach OVERDARE.
