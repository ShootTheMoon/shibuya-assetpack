# 출처 및 라이선스 — Shibuya Asset Pack

프로젝트는 **비상업 목적**이나, 배포 시 아래 저작자를 표기한다.

## Sketchfab 임포트 (CC-BY)

### SF_VendingMachine_A
- **원본**: "JPN vending machine"
- **저작자**: adenotoxin
- **UID**: `e9a1050ada83417592fc3233cb6a4c0a`
- **라이선스**: CC-BY 4.0
- **가공**: 계층 평탄화(armature 해제), 단일 메시 병합, 접지 원점 정렬, 텍스처 1024 다운스케일, FBX/GLB 임베드

### SF_TrafficSignal_A
- **원본**: "Japanese Traffic Light"
- **저작자**: afx_cgmotion
- **UID**: `3e35c76a6ee24d759e39edc2f90677e1`
- **라이선스**: CC-BY 4.0
- **가공**: 27파트 → 단일 메시 병합, 실제 높이 5.6 m 정규화, 접지 원점, 텍스처 4장 1024 다운스케일

### VG_StreetTree_A
- **원본**: "Maple trees pack (lowpoly, game ready, LODs)"
- **저작자**: lolipop_1707
- **UID**: `b5d2833c258f4054a01ee2b4ef85adf0`
- **라이선스**: CC-BY 4.0
- **가공**: 15종 팩에서 `Acer_medium_1` **LOD1**만 분리(bark+cluster), 실제 가로수 7 m로 재스케일, 잎 카드 alpha CLIP, 텍스처 6장 1024 다운스케일

## 자체 제작 (100% original)
- **UP_UtilityPole_A** — 일본 콘크리트 배전주. Sketchfab에 사용 가능한 소스 없음 (REJECTIONS.md 참조)
- **UP_CableSpan_A** — 가공 전선 스팬
- **GR_TactilePaving_Dot_A / _Bar_A** — JIS T 9251 점자블록

## 미사용 (참고용으로만 조사)
- 渋谷駅前「青ガエル」 tasklong `80c8a7af47644925907bd341ffeb618b` — **CC-BY-NC**. 유일한 소스이며 비상업 프로젝트에는 사용 가능하나, 상업 전환 시 차단됨
- 크라우드 세트 yancharkin (12종) — **CC-BY-SA**. 파생물에 동일 라이선스 전파 의무

## ZK_SignAtlas (signboard graphics)

`03_Textures/ZK_Zakkyo_Facade_Kit/ZK_SignAtlas_albedo.png` + `_emit.png` are **originally generated**
by `make_sign_atlas.py` (PIL) in this project — 64 fictional Japanese tenant signs rendered in
Yu Gothic Bold (a Windows system font; only the rendered raster is redistributed, not the font).
No third-party asset was used. The Sketchfab neon models surveyed as candidates
(`f4fb7741b2a94ae3938355c1c34554a8`, `7ad34566835c4ab0975016b9f97fa2ee`) were **rejected** — they are
3D letter geometry, not texture atlases. See REJECTIONS.md.

## Phase 1c — crowd & vehicles

| Asset | Source | Author | Licence | UID |
|---|---|---|---|---|
| `CR_Pedestrian_00..17` | "Low Detail Animated Crowd" | **shahriyarshahrabi** | **CC-BY 4.0** | `4fe76fdec12d456f9b0db06b45cc53d6` |
| `VH_TaxiCrown_A` | "Toyota Crown Comfort S10" | **iwak.rebus** | **CC-BY 4.0** | `3ef4527459f5406fb4599864800ab1fa` |

The andon roof sign on the taxi is originally modelled in this project.

## Phase 1d — landmarks

| Asset | Source | Author | Licence | UID |
|---|---|---|---|---|
| `LM_Hachiko_A` | Hachikō statue | **billycarlos354** | **CC-BY 4.0** | `75a9949393034d5cbc18625bc2bdb810` |

`LM_Shibuya109_A`, `LM_QFrontScreen` and the `LM_109_*` / `LM_QFront_screen` textures are
**originally created in this project**. The Q-FRONT screen content is abstract by design — no
real brand, logo, or broadcast frame is reproduced.

### ⚠ Non-commercial restriction

`LM_Aogaeru_A` — "Aogaeru / Tokyu 5000 deha5001", **tasklong**, UID `80c8a7af47644925907bd341ffeb618b`,
licensed **CC-BY-NC 4.0**. It is the only model of this subject in existence. Included at the user's
explicit direction. **This single asset makes the assembled map non-commercial.** To clear the map for
commercial use, delete `LM_Aogaeru_A` and re-run `06_Placement/place_landmarks.py` — nothing else
in the pack carries a non-commercial or share-alike term.
