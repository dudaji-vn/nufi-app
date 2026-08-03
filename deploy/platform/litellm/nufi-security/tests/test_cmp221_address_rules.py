"""CMP-221 (v0.2.0 P2) — 규칙 백엔드 확장 검증: 도로명·상세주소·랜드마크·시군구.

부모 CMP-218. 선행 P1(CMP-220) 오차분석: 프로덕션 KR_LOCATION FN 은 100% "어휘밖
고유지명"(국제도시·테크노밸리·몰·플라자·시티·공원 등 규칙적 접미사). 본 테스트는
gazetteer 규칙 백엔드의 신규 규칙이

  · 어휘밖 고유지명(P1 class c)을 josa 부착 형태까지 탐지하고,
  · 도로명주소(…로/길+번지)·상세주소(동/호)를 탐지하며,
  · 부사/일반명사(참고로·쇼핑몰·메모리 등) 오탐을 차단(정밀도)하고,
  · 골드셋 벤치 corpus 에서 benign false-positive 0 을 유지하는지

를 결정적·에어갭(gazetteer)으로 고정한다.

실행: python3 -m pytest tests/test_cmp221_address_rules.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import EgressGuard  # noqa: E402
from egress_audit.detectors.ner import KoreanNerDetector  # noqa: E402

_DET = KoreanNerDetector(backend="gazetteer")
assert _DET.backend_name == "gazetteer", "에어갭 결정성: gazetteer 백엔드여야 함"


def _locs(text: str) -> set[str]:
    return {s.text for s in _DET.detect(text) if s.entity_type == "KR_LOCATION"}


def _has_loc(text: str) -> bool:
    return bool(_locs(text))


# ---------------------------------------------------------------------------
# 1. 어휘밖 고유지명(P1 class c) — 랜드마크/개발지구 접미사, josa 부착 포함
# ---------------------------------------------------------------------------
def test_landmark_unlisted_places_detected():
    for name in ("송도국제도시", "센텀시티", "판교테크노밸리", "동대문디자인플라자",
                 "광교호수공원", "코엑스몰", "마곡지구"):
        assert name in _locs(name), f"{name} 미탐지"


def test_landmark_with_korean_josa():
    # 조사(로/에서/에)가 붙어도 지명을 인식해야 한다(경계 처리).
    assert "송도국제도시" in _locs("배송지를 송도국제도시로 변경해 주세요.")
    assert "코엑스몰" in _locs("이번 워크숍은 코엑스몰에서 진행됩니다.")
    assert "마곡지구" in _locs("이번 워크숍은 마곡지구에서 진행됩니다.")


def test_landmark_homograph_common_nouns_suppressed():
    # 접미사는 같지만 지명이 아닌 일반명사 복합어는 오탐하지 않는다.
    for w in ("쇼핑몰", "온라인몰", "고객센터", "데이터센터", "콜센터",
              "놀이공원", "테마파크", "워터파크"):
        assert not _has_loc(f"{w} 이용 방법 알려줘"), f"{w} 오탐"


# ---------------------------------------------------------------------------
# 2. 도로명주소 (…대로|로|길 + 건물번호) — task 1
# ---------------------------------------------------------------------------
def test_road_addresses_detected():
    cases = {
        "테헤란로 152": "테헤란로 152",
        "판교로 235번길 4": "판교로 235번길 4",
        "세종대로 110 방문": "세종대로 110",
        "불정로 6번지 소재": "불정로 6번지",
    }
    for text, want in cases.items():
        assert want in _locs(text), f"{text!r} → {_locs(text)} (기대 {want!r})"


def test_road_adverbs_not_matched():
    # …로 로 끝나는 부사/일반명사 + 숫자 조합을 도로명으로 오탐하지 않는다.
    for text in ("참고로 3가지 정리", "별도로 2개 준비", "그대로 100번 반복",
                 "주로 5명 참석", "실제로 10건 발생"):
        assert not _has_loc(text), f"{text!r} 오탐: {_locs(text)}"


def test_road_requires_building_number():
    # 건물번호 없는 도로명 단독(…로 변경)은 도로명주소로 잡지 않는다.
    assert not _has_loc("배송지로 변경해 주세요")


# ---------------------------------------------------------------------------
# 3. 상세주소 (동/호, 층/호) — task 2
# ---------------------------------------------------------------------------
def test_detail_addresses_detected():
    assert "101동 203호" in _locs("우리집은 101동 203호 입니다.")
    assert "3층 402호" in _locs("사무실 3층 402호로 오세요.")
    assert "지하 1층 12호" in _locs("주차는 지하 1층 12호.")


def test_detail_boundary_not_over_matched():
    # 동/호가 함께 오지 않는 층/호 번호(안건 번호·노선 등)는 오탐하지 않는다.
    for text in ("제3호 안건 검토", "3층 회의실 예약", "회의록 초안 v3", "2호선 지하철"):
        assert not _has_loc(text), f"{text!r} 오탐: {_locs(text)}"


# ---------------------------------------------------------------------------
# 4. 시군구 사전 확장(28→~230) — 전국 시군구 화이트리스트
# ---------------------------------------------------------------------------
def test_nationwide_sigungu_detected():
    # 기존 28 사전 밖의 전국 시군구가 접미사 규칙으로 탐지된다.
    for name in ("여수시", "안동시", "김포시", "남양주시", "파주시", "속초시",
                 "송파구", "유성구"):
        assert name in _locs(f"{name} 방문 예정입니다."), f"{name} 미탐지"


def test_metro_district_combined_span():
    # 다토큰 행정 스팬(시 + 구)을 하나로 결합해 경계 품질을 보존(P1 class d).
    assert "성남시 분당구" in _locs("배송지를 성남시 분당구로 변경해 주세요.")
    assert "용인시 기흥구" in _locs("용인시 기흥구 지점 오픈 일정 알려줘.")


# ---------------------------------------------------------------------------
# 5. 골드셋 회귀 — KR_LOCATION recall 상승 + benign FP 0 유지
# ---------------------------------------------------------------------------
def _gold_rows(entity: str):
    for split in ("test", "dev"):
        path = ROOT / "samples" / "gold" / f"{split}.jsonl"
        for line in path.open(encoding="utf-8"):
            line = line.strip()
            if line:
                yield json.loads(line)


def test_goldset_kr_location_recall_high():
    # P1 baseline(gazetteer) 행-레벨 recall 0.575 → 규칙확장 후 대폭 상승.
    rows = [r for r in _gold_rows("KR_LOCATION")
            if "KR_LOCATION" in r.get("expect", [])]
    hit = sum(1 for r in rows if _has_loc(r["prompt"]))
    assert rows, "골드셋에 KR_LOCATION 행이 있어야 함"
    recall = hit / len(rows)
    assert recall >= 0.90, f"KR_LOCATION 행-레벨 recall={recall:.4f} (기대 ≥0.90)"


def test_goldset_benign_false_positive_zero():
    # DoD: benign false-positive(차단·finding) 0 유지.
    guard = EgressGuard(ner_backend="gazetteer")
    benign_files = [ROOT / "samples" / "benign_samples.jsonl",
                    ROOT / "samples" / "gold" / "test.jsonl",
                    ROOT / "samples" / "gold" / "dev.jsonl"]
    findings_fp = blocks_fp = total = 0
    for f in benign_files:
        for line in f.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("expect"):
                continue
            total += 1
            res = guard.inspect(r["prompt"])
            findings_fp += bool(res.findings)
            blocks_fp += bool(res.blocked)
    assert total > 0
    assert blocks_fp == 0, f"benign block FP={blocks_fp}"
    assert findings_fp == 0, f"benign finding FP={findings_fp}"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
