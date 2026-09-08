"""Stamp the OVERDARE import findings INTO the Shibuya .blend as a Text datablock.

Why a script instead of just editing the file: the only copy of shibuya_detail_v033.blend
lives in Google Drive (내 드라이브 > overdare > GameDev > Maps > Shibuya) and Drive is not
mounted on this machine - there is no G:, no DriveFS process, and Desktop\\blender is empty.
So the notes are delivered as something that can be applied the moment the file is pulled
down, rather than as a document that will drift away from the asset it describes.

USAGE
    headless:  blender --background <file.blend> --python shibuya_overdare_notes.py -- --save
    in the UI: open in the Text Editor, Run Script, then save the file yourself

Without --save nothing is written to disk; the datablock exists in the session only. That is
deliberate - this should not silently rewrite a 27 MB asset.

Idempotent: re-running replaces the datablock rather than adding a second one.
"""
import sys

try:
    import bpy
except ImportError:                       # let it be read outside Blender
    bpy = None

NAME = "OVERDARE_IMPORT_NOTES.md"

NOTES = """\
# 시부야 → OVERDARE 임포트: 확정된 사실 (2026-08-12 실측)

이 맵을 OVERDARE에 올릴 때의 제약. 전부 엔진에서 직접 확인한 것이고,
추정이 아니라 에셋 테이블/크래시 로그로 뒷받침된다.

## 1. FBX 안에 콜라이더를 넣을 수 없다 — 두 방식 다 죽음

| 방식 | 결과 |
|---|---|
| 단독 `UCX_*.fbx` 5개 | "Failed to create asset" |
| 렌더 파일 안에 `UCX_` 메시 내장 | **Studio 치명적 크래시** |

크래시 원문:

    Fatal error: LevelActor.cpp:583
    Cannot generate unique name for 'MetaBaseWorldSettings'
    in level '/Engine/Transient.Untitled:PersistentLevel'

**원인:** OVERDARE 임포터는 파일 안의 **오브젝트마다** 월드 에셋을 하나씩 발행하고
transient world를 누수시킨다. 헐 32개 = 발행 32번 추가 → 이름 생성기 고갈.
그래서 `prepare_all.py`가 모든 메시를 파일당 하나로 합치는 것이고,
**콜라이더도 그 규칙의 예외가 아니다.**

**증거(프로젝트 에셋 테이블이 기록한 그라데이션):**

| 파일 | 헐 | 결과 |
|---|---|---|
| `SF_TrafficSignal_A` | 0 | MODEL + STATIC_MESH + TEXTURE — 정상 |
| `ROADS_02` | 32 | STATIC_MESH만 — 반쪽 임포트 |
| `PROBE_UCX128` | 128 | 크래시 |

**감당도 안 된다:** 머티리얼 1개짜리 파일이 3유닛 → 35유닛.
배포본 전체가 456 → 1,600+ 유닛, Studio 세션 15회 → 약 47회.

## 2. MeshPart에 콜리전 정밀도 옵션이 없다

저장된 `.ovdrjm`의 모든 인스턴스를 훑어 확인. 콜리전 관련 속성은
`CanCollide` / `CollisionProfile`(BlockAll) / `CanClimb` 뿐이고
**CollisionFidelity류는 존재하지 않는다.** 임포트된 STATIC_MESH가 들고 오는 형상이
곧 충돌의 전부다.

## 3. 답: 엔진 Part

이 맵의 콜리전 헐은 **전부 축정렬 박스**다(건물·랜드마크는 오브젝트별 AABB,
지형은 적응형 쿼드트리의 평평한 박스). Part가 곧 박스이므로 **1:1, 근사 없음**.
게다가 Part는 네이티브 프리미티브라 **발행 에셋 0개** — 임포트 예산을 건드리지 않고,
나중에 Studio에서 손으로 고칠 수도 있다.

    Transparency 1 / CanCollide true / Anchored / Static
    → Part 3,807개 (지형 3,118 · 건물 597 · 랜드마크 17 · 전주·차량 75)

전주와 차량은 **배치 행마다 회전된 박스**로 만든다. 45° 돌아간 4.7 m 택시를
월드 AABB로 잡으면 40% 이상 부풀어 차선을 막는다.

## 4. 지형 콜리전 — 측정으로 정한 것

- **평평한 박스가 삼각 프리즘보다 싸다.** 프리즘은 경사를 따라가서 셀은 적게 쓰지만
  (코어 44 vs 79) 셀당 2개라 헐은 더 든다(88 vs 79).
- **코어는 거의 평탄하다.** 10 m 셀 기준 오차 p50 = 0.06 m. 계곡 비탈이 오차를 다 갖는다.
- 그래서 균일 격자는 낭비 → **거리별 등급 적응형 쿼드트리**.
  균일 0.30 m로 ±340 m를 덮으면 2,935 헐인데, 코어 ±128 m만은 79 헐이면 된다.
- 채택값: **코어 ±128 m 0.30 m / 128–200 m 0.50 m / 200–340 m 1.00 m**.
  (FBX 내장 시절엔 파일당 32헐 상한 때문에 1.54/4.82로 풀어야 했으나,
  Part에는 상한이 없어 되찾았다.)

콜리전을 **의도적으로 넣지 않은 것**: 군중(넣으면 스크램블이 통행 불가), 나무, 네온,
점자블록, 잡거빌딩 파사드 키트(건물 박스가 이미 덮음),
13 cm 연석(넘어다니는 것이라 넣으면 이동이 끈적해진다).

## 5. 정적 배포 파일은 지역별로 나뉘어 있지 않다

`BUILDINGS_01~17`은 **트라이앵글 예산**으로 쪼갠 것이라 하나하나가 맵 전체(±330 m)를
덮는다. 지형 7개 파일도 마찬가지. "이 오브젝트가 어느 파일에 속하나"를 bbox로
판정하려 하면 안 된다. 반대로, 정적 파일은 각자 자기 월드 bbox 중심에 배치되므로
**월드 좌표 기준의 무언가를 어느 파일에 붙여도 위치는 맞는다.**

## 6. 임포트 회계 (실측 확인됨)

- 머티리얼 1개짜리 파일 = **정확히 3 발행 에셋** (TEXTURE + STATIC_MESH + MODEL)
- **완료 표시는 MODEL 뿐.** STATIC_MESH만 있으면 반쪽이고 쓸 수 없다 —
  UI에서는 성공처럼 보인다.
- **재시도는 교체가 아니라 중복 발행이다.** 실패한 파일을 다시 넣지 말고
  재개 스크립트를 돌릴 것.
- **한 번에 한 파일씩(Home > Import). Bulk Import 금지** — 벌크는 26 에셋을 넘긴 적이
  없고 MODEL을 발행하지 않는다.
- **세션마다 Studio 재시작.** transient world 누수는 재시작 외에 초기화되지 않는다.

## 7. 배포본 (v18)

    105 파일 / 505,508 tris / 246 MB / 파일당 메시 1개
    453 발행 에셋 ⇒ Studio 세션 15회
    콜리전은 FBX에 없음 — Part로 별도 생성

## 8. 배치 단계에서 확정된 것 (v17 패스)

임포트가 끝난 뒤 실제로 레벨에 놓는 단계에서 나온 것들. 위 1~7이 "어떻게 넣는가"라면
이쪽은 "넣은 것을 어떻게 세우는가"다.

**`MeshPart.MeshId`는 STATIC_MESH여야 한다. MODEL을 넣으면 안 된다.**
MODEL은 지오메트리가 없는 묶음 노드다. 넣어도 대입은 성공하고, 모든 속성이 정상으로
읽히고, 스포너는 "9,986개 생성, 실패 0"을 찍고, **화면에는 아무것도 안 그려진다.**

    41030500  BUILDINGS_01_overdare      MODEL        ← 틀림
    41032100  BUILDINGS_01_overdare_1    STATIC_MESH  ← 맞음

**조용히 실패하는 속성 3개.** 셋 다 생략해도 오류가 없다.

    Size       생략 → 0으로 저장 → 영원히 안 보임 (나머지 속성은 정상으로 읽힘)
    TextureId  생략 → 복제된 템플릿에서 상속. 레벨 전체가 BUILDINGS_15의 텍스처를 쓰고 있었다
    MeshId     위 항목

MeshPart는 `TextureId`를 하나만 갖는다. 다중 머티리얼 파일(104개 중 67개, 택시 10장·역
9장)은 MeshPart 하나로 온전히 표현할 수 없다 — 임포터가 만드는 Model 계층이 그 역할이다.

**수직 오프셋은 bbox 중심이지 높이의 절반이 아니다.**
`CFrame`은 파트의 중심, `placements.csv`의 Y는 발밑이다.

    y = csv_Y + (bbox_min.z + bbox_max.z) / 2 * 100      ← 높이/2 아님

둘은 마스터의 피벗이 정확히 발밑일 때만 일치한다. 점자블록은 그렇고 — 그래서 점자블록으로
만든 스모크 테스트가 통과했다 — 다음은 아니다.

    ZK_SignboardStack_*   bbox z 0.35..3.07   +35 cm   (마스터 40종)
    ZK_ShopFront_*        bbox z 0.10..2.80   +10 cm
    ZK_RollerShutter      bbox z 0.10..3.40   +10 cm

코어 9,995개 중 2,954개가 해당됐다.

**맵 버그로 착각하기 쉬운 것 2가지.**

- **기본 `Baseplate`** — 1 km × 1 km 회색 Part가 Y = −20 cm에 깔려 맵을 덮는다.
  "도로 텍스처가 다 깨졌다"로 보인다. Transparency 1 + CanCollide false, 또는 삭제.
- **CDN 스트리밍** — 임포트 호출이 끝난 뒤에도 메시는 계속 내려온다. 너무 일찍 찍은
  부감은 **모서리가 직선인 큰 사각형 구멍**으로 보이고, 진짜 누락과 구분되지 않는다.
  지면 절반이 40분간 "없다가" 저절로 채워졌다. 납품물·준비 파일·좌표를 전부 재측정하고
  가설 2개(뒷면 컬링, 파트 크기 상한)를 검증·기각한 뒤에야 그냥 채워졌다.
  **스트리밍이 끝나기 전 화면은 증거가 아니다.**

**아틀라스 시트는 텍스처 상한의 예외다.**
시트는 텍스처 1장이 아니라 이미 각자 상한이 적용된 60여 장을 재배치한 것이다. 시트에
512 상한을 걸면 그 상한이 60번 적용된다 — rect가 506 px에서 63 px로, 픽셀의 1/64만 남는다.
이 규칙이 4곳에 복사돼 있었고(`texture_caps.py`, `make_texwork.py` 2곳,
`shibuya_export_v2.py`) `prepare_all.py`가 또 따로 줄여서, 익스포터만 고치면 아무 효과가
없었다. v15는 시트를 전부 512로 실어 보냈다. 지금은 정의가 하나다 —
`texture_caps.cap_for` + `KEEP_FULL = ("ATLAS_", "ATLASM_")`.
수정 후 검증: 코어 지면 90.1 텍셀/m², 1024 타일이 예측하는 92와 일치.

**고장난 RPC 2개.**

    instance.delete   이 빌드에서 파라미터 형태와 무관하게 Internal error.
                      .ovdrjm 파일 편집 경로만 동작하고, 한 번에 guid 하나씩이다.
    game.screenshot   영구히 죽을 수 있고 Studio 재시작으로도 안 살아난다.
                      데스크톱 캡처가 확실한 대안이다. 내장 캡처 고치는 데 시간 쓰지 말 것.

## 9. 남은 작업

1. **yaw 부호 미확인.** `placements.csv`의 `yaw_deg = -degrees(rot_z)`가 맞는지
   엔진 밖에서는 검증 불가능하다. 틀리면 9,986개가 전부 돌아간다.
   방향이 있는 물체(신호등)를 하나 배치해 도로를 따라 보는지 확인할 것 —
   전주는 대칭이라 이걸 못 본다.
2. **본 임포트 15세션.** 한 번에 한 파일씩, 세션마다 Studio 재시작. 자동화 불가.
3. **콜리전 Part는 아직 한 번도 배치되지 않았다.** 청크는 만들어졌고 소비만 남았다.

## 10. 헐 분배에서 둘 다 틀렸던 것 (FBX 내장 시절 기록)

둘 다 그럴듯해 보였고 둘 다 틀렸다.

- **라운드로빈 배정** → `TERRAIN_01`의 bbox가 Z로 **+84.8 m** 커졌다.
  높이 129 m짜리 건물 헐을 받았기 때문이다.
- **bbox 증가 최소 배정** → 넘친 분이 `FRN_01/03/04`(폭 ~120 m 메이지도리 회랑
  측량)에 쌓여 **+700 m** 커졌다.

교훈: 맵 전역 헐은 이미 맵 전역을 덮는 파일만 받아야 한다.
(Part로 가면서 이 문제는 통째로 사라졌다.)

## 11. 이번에 내가 틀렸던 것

- 계획 단계에서 **"FBX 안에 UCX 넣기"를 권장안으로 올렸다.** 임포터가
  오브젝트마다 에셋을 발행한다는 사실은 `prepare_all.py` 주석에 이미 적혀
  있었는데 콜라이더에 연결하지 못했다.
- **일부러 실패하도록 만든 프로브를 임포트 폴더 안에 같이 두었다.**
  정상 파일의 실패를 엉뚱한 원인으로 판단할 뻔했다. 실패용 파일은 임포트
  폴더 밖에 둔다.
## 관련 스크립트 (Drive: overdare > GameDev > Tools > MeshTest)

    ucx_lib.py              헐 수학 + _UCX_PARTS 사이드카
    ucx_split.py            콜리전 FBX → 헐 추출 (Blender 헤드리스)
    make_collision_parts.py 헐 → overdare_create_instances용 Part itemsFile
    prepare_all.py          EMBED_UCX = False (켜지 말 것, 이유는 상수 주석에)
    make_import_batches.py  세션/배치 분할 + 재개
    import_status.py        MODEL 유무로 진척 판정
    check_placed.py         Size/|UnitExtent| == 2.000 로 렌더 여부 판정
    check_import_tree.py    배치 트리 무결성

⚠ 실패하도록 만든 프로브는 `_PROBES_DO_NOT_IMPORT\\`에 격리돼 있다. 임포트하지 말 것.

"""


def main():
    if bpy is None:
        print(NOTES)
        return
    t = bpy.data.texts.get(NAME)
    if t is None:
        t = bpy.data.texts.new(NAME)
    t.clear()
    t.write(NOTES)
    # Survives a purge of unused datablocks; a note nobody references is exactly the kind of
    # thing "Clean Up > Unused Data" throws away.
    t.use_fake_user = True
    print("stamped '%s' into %s  (%d chars)"
          % (NAME, bpy.data.filepath or "<unsaved>", len(NOTES)))

    if "--save" in sys.argv:
        if not bpy.data.filepath:
            print("  !! no filepath - open a .blend first, or save it by hand")
            return
        bpy.ops.wm.save_mainfile()
        print("  saved %s" % bpy.data.filepath)
    else:
        print("  NOT saved. Re-run with  -- --save  , or save the file yourself.")


if __name__ == "__main__":
    main()
