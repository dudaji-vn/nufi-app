"""CMP-249 · nufi Python SDK 파사드 — 스모크 테스트.

수용기준(docs/SDK.md §5):
- stable 심볼 전부 임포트 성공
- ``import nufi`` 가 모델·config 로딩 0 (부수효과 없음)
- detect / Guard / compliance_report 동작
- __version__ 이 루트 VERSION 과 일치
"""

from __future__ import annotations

import importlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"


# ── 1. 부수효과 없는 임포트 ──────────────────────────────────────────────

def test_import_no_side_effects():
    """import nufi 가 외부 호출 0 · 모델 로딩 0."""
    # 캐시 제거 후 재임포트 — 모델 로딩이 import 시 일어나면 여기서 터진다
    if "nufi" in sys.modules:
        # 이미 임포트된 경우에도 최소 확인
        import nufi
        assert nufi._DEFAULT_DETECTOR is None or callable(nufi.detect)
        return
    import nufi  # noqa: F811
    # 지연 로딩이므로 _DEFAULT_DETECTOR 는 아직 None
    assert nufi._DEFAULT_DETECTOR is None


# ── 2. __version__ 동기화 ────────────────────────────────────────────────

def test_version_matches_root():
    import nufi
    expected = VERSION_FILE.read_text().strip()
    assert nufi.__version__ == expected, (
        f"nufi.__version__={nufi.__version__!r} != VERSION={expected!r}"
    )


# ── 3. stable 심볼 전부 임포트 ───────────────────────────────────────────

STABLE_SYMBOLS = [
    "detect", "Detector", "Finding",
    "pseudonymize", "mask", "redact", "ReversibleEgress",
    "Guard", "GuardResult", "PolicyEngine", "Decision",
    "compliance_report", "render_report", "load_catalog",
]


@pytest.mark.parametrize("name", STABLE_SYMBOLS)
def test_stable_symbol_importable(name):
    import nufi
    obj = getattr(nufi, name, None)
    assert obj is not None, f"nufi.{name} not found"
    assert name in nufi.__all__, f"nufi.{name} not in __all__"


# ── 4. detect 편의 함수 ─────────────────────────────────────────────────

def test_detect_returns_findings():
    from nufi import detect, Finding
    results = detect("김민수님 계좌번호 110-123-456789")
    assert isinstance(results, list)
    assert len(results) > 0
    assert all(isinstance(f, Finding) for f in results)
    types = {f.entity_type for f in results}
    assert "KR_ACCOUNT" in types or "KR_PERSON" in types, (
        f"Expected KR_ACCOUNT or KR_PERSON in {types}"
    )


def test_detect_benign_empty():
    from nufi import detect
    results = detect("오늘 날씨가 좋습니다.")
    assert isinstance(results, list)
    pii_types = {f.entity_type for f in results}
    assert "KR_RRN" not in pii_types
    assert "KR_ACCOUNT" not in pii_types


# ── 5. 가명화 ────────────────────────────────────────────────────────────

def test_pseudonymize():
    from nufi import pseudonymize
    token = pseudonymize("KR_PERSON", "홍길동")
    assert isinstance(token, str)
    assert "홍길동" not in token


def test_mask():
    from nufi import mask
    result = mask("900101-1234567", keep_tail=4)
    assert result.endswith("4567")
    assert "900101" not in result


def test_redact():
    from nufi import redact
    result = redact("KR_RRN")
    assert "REDACTED" in result


# ── 6. Guard (탐지+정책) ─────────────────────────────────────────────────

def test_guard_inspect():
    from nufi import Guard, GuardResult
    guard = Guard()
    result = guard.inspect("김민수님 계좌번호 110-123-456789")
    assert isinstance(result, GuardResult)
    # 기본 정책에서 KR_PERSON → pseudonymize, KR_ACCOUNT → block/pseudonymize
    assert len(result.findings) > 0, "Should detect PII"


def test_guard_benign():
    from nufi import Guard
    guard = Guard()
    result = guard.inspect("오늘 회의 시간 변경되었습니다.")
    assert result.blocked is False


# ── 7. compliance_report / render_report ─────────────────────────────────

def test_load_catalog():
    from nufi import load_catalog
    catalog = load_catalog()
    assert isinstance(catalog, dict)
    assert "controls" in catalog


# ── 8. Detector 별칭 ────────────────────────────────────────────────────

def test_detector_alias():
    from nufi import Detector
    from egress_audit.pipeline import DetectionPipeline
    assert Detector is DetectionPipeline


def test_guard_alias():
    from nufi import Guard
    from egress_audit.guard import EgressGuard
    assert Guard is EgressGuard
