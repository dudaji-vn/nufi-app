"""CMP-317 — 조사 부착 인명 탐지 검증.

한국어 조사(에게/은/는/이/가/을/를 등)가 붙은 인명을 문맥 게이팅 하에서
정확히 탐지하는지 검증한다.

실행: python3 -m pytest tests/test_cmp317_person_josa.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit.detectors.ner import detect_kr_persons  # noqa: E402


def _person_names(text: str) -> set[str]:
    return {s.text for s in detect_kr_persons(text)}


# ---------------------------------------------------------------------------
# 조사 부착 인명 — 문맥 게이팅(담당자/고객/직원 등) + 조사 경계
# ---------------------------------------------------------------------------

def test_josa_ege():
    """'담당자 겸소율에게' → KR_PERSON '겸소율'."""
    assert "겸소율" in _person_names("담당자 겸소율에게 연락해 주세요.")


def test_josa_eun():
    """'고객 박지현은' → KR_PERSON '박지현'."""
    assert "박지현" in _person_names("고객 박지현은 본인확인을 완료했습니다.")


def test_josa_reul():
    """'직원 최민수를' → KR_PERSON '최민수'."""
    assert "최민수" in _person_names("직원 최민수를 담당자로 배정합니다.")


def test_josa_wa():
    """'고객 김서연과' → KR_PERSON '김서연'."""
    assert "김서연" in _person_names("고객 김서연과 통화 완료.")


def test_josa_ui():
    """'담당자 이도윤의' → KR_PERSON '이도윤'."""
    assert "이도윤" in _person_names("담당자 이도윤의 보고서를 확인하세요.")


def test_josa_egeseo():
    """'고객 정하준에게서' → KR_PERSON '정하준'."""
    assert "정하준" in _person_names("고객 정하준에게서 연락이 왔습니다.")


def test_josa_hante():
    """'담당자 윤지호한테' → KR_PERSON '윤지호'."""
    assert "윤지호" in _person_names("담당자 윤지호한테 전달해 주세요.")


# ---------------------------------------------------------------------------
# 기존 게이팅(경칭/직함/문맥 비-조사) 회귀 확인
# ---------------------------------------------------------------------------

def test_honor_gate_still_works():
    """경칭 게이팅: '김철수님' → 탐지."""
    assert "김철수" in _person_names("고객 김철수님의 계정입니다.")


def test_title_gate_still_works():
    """직함 게이팅: '이영희 부장' → 탐지."""
    assert "이영희" in _person_names("이영희 부장 보고서 검토.")


def test_context_bare_still_works():
    """문맥 게이팅(조사 없음): '담당자 박민수 앞으로' → 탐지."""
    assert "박민수" in _person_names("담당자 박민수 앞으로 전달.")


def test_no_gate_no_detection():
    """게이팅 없는 인명은 오탐 억제로 미배출."""
    assert "김철수" not in _person_names("김철수가 갔다.")
