# Sketchfab 거부 기록 — Shibuya Asset Pack

CC-BY 우선, 비상업 프로젝트이므로 CC-BY-NC도 허용. 거부 사유를 남긴다.

## 電柱 / Japanese utility pole — 사용 가능한 소스 없음 → 직접 모델링
| 후보 | 작가 | UID | Faces | 사유 |
|---|---|---|---|---|
| 電柱 | ytprogf | `3300dc07bde94544a9a1e6c02b4bf739` | 903,153 | **프리뷰 확인: 사용 불가.** 사진측량 원본으로 케이블이 찢어진 채 공중에 뜬 파편. 어떤 데시메이션으로도 복구 불가 |
| 電柱 (형제 업로드) | ytprogf | `e3c17376f4da4b8f8b6fd104eca5c1e6` / `d110be847f754acb8a74dcc1d7410d14` / `33f59d0086fb4c88994eaa31b24c9687` | 545k / 1.89M / 560k | 동일 결함 |
| War-Damaged Utility Pole | — | `45a3c7e44b22416c974aacd58e66c459` | 104k | 전쟁 폐허 — 주제 불일치 |
| 東京大空襲焼け残り電柱 | — | `6f75b3d9b16c48c8885e811e272d552f` | 2.19M | 동상/기념물 — 주제 불일치 |
| "utility pole" 일반 검색 20건 | — | — | — | 전부 미국식 목재 크로스암 — 일본 電柱(콘크리트 주 + 변압기 캔 + 밀집 케이블)과 **실루엣이 근본적으로 다름** |

**결론:** `UP_UtilityPole_A` 직접 제작 (1,836 tris).

## 기타 소스 없음 (직접 제작 예정)
- **점자블록 (点字ブロック)** — 검색 결과 1건뿐, 100만 faces / Free Standard 라이선스 / 주제 불일치
- **일본식 가드파이프** — 18건 전부 미국식 W빔 가드레일
- **현대 일본 가로등** — 전통 등롱만 검색됨
- **잡거빌딩 간판 스택** — 해당 소스 없음

## 가로수 — 1차 후보 거부
| 후보 | 작가 | UID | Faces | 사유 |
|---|---|---|---|---|
| Tree 3D Scan - Retopo | zdenkoroman | `9e6778e11ad2413dab940e23bb0b89df` | 22,369 | **프리뷰 확인: 잎이 전혀 없는 앙상한 줄기.** 가로수로 사용 불가 |
| "tree lowpoly" 검색 24건 | — | — | — | 대부분 툰/스타일라이즈드 — 실사 PLATEAU 건물과 톤 불일치 |

**채택:** lolipop_1707 Maple pack (CC-BY) — 실사 계열 + LOD 제공

## Neon sign texture atlases — REJECTED (2026-07-28)

Both Sketchfab candidates recorded in the plan as "take the materials, not the geometry" turn out to
carry **no usable sign textures at all**:

| UID | Author | Finding |
|---|---|---|
| `f4fb7741b2a94ae3938355c1c34554a8` | diegoichinose (CC-BY) | Downloaded and inspected. 12 materials, **1 image total** (`screen-A_emissive.jpeg`, 512x256). Every sign is **3D letter geometry** with flat emissive materials (`emissive-white/blue/red`, `yellow`, `black`). Nothing to harvest. |
| `7ad34566835c4ab0975016b9f97fa2ee` | — | Same class of asset; not downloaded after the first result. |

**Resolution:** generated our own atlas instead — `03_Textures/ZK_Zakkyo_Facade_Kit/make_sign_atlas.py`
draws 64 Japanese tenant signs (4 cols x 16 rows of 1024x256 banner cells on a 4096 sheet;
it started at 16 in a 2x8 layout and was expanded once measurement showed 38,325 placed
panels drawing on 16 graphics = 2,395 repeats each) plus a separate emission
mask. Fully owned, no licence burden, and controllable (cell count, colours, text, glow per cell).

## Crowd set — the plan's CC-BY-SA candidate was NOT used (2026-07-28)

The plan named the **yancharkin** 12-variant crowd (~1.1k f each) as the best crowd option and flagged it
as **CC-BY-SA**, which would virally licence any derivative of the map. A fresh search surfaced
**"Low Detail Animated Crowd"** (shahriyarshahrabi, `4fe76fdec12d456f9b0db06b45cc53d6`) — **18 characters,
10,254 faces total, CC-BY** (attribution only, no share-alike). Previewed: varied clothing, real walking
poses, consistent scale. Strictly better on both count and licence, so the CC-BY-SA set was dropped and
the commercial-pivot flag it carried no longer applies to the crowd.
