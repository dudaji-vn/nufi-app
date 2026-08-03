"""Injection detection CI gate — recall ≥ 0.95, benign FP rate ≤ 0.05 (CMP-323).

이 테스트는 인젝션 골드셋(samples/injection_gold.jsonl) 대상
탐지 품질이 CI 게이트 기준을 충족하는지 검증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


@pytest.fixture(scope="module")
def injection_metrics():
    """Run the injection benchmark once per module."""
    import bench_injection
    return bench_injection.run_benchmark()


def test_injection_recall_gate(injection_metrics):
    """Injection recall must be >= 0.95."""
    recall = injection_metrics["recall"]
    assert recall >= 0.95, (
        f"Injection recall {recall:.4f} < 0.95 gate "
        f"(TP={injection_metrics['tp']} FN={injection_metrics['fn']})"
    )


def test_benign_fp_rate_gate(injection_metrics):
    """Benign false-positive rate must be <= 0.05."""
    fp_rate = injection_metrics["benign_fp_rate"]
    assert fp_rate <= 0.05, (
        f"Benign FP rate {fp_rate:.4f} > 0.05 gate "
        f"(FP={injection_metrics['fp']} TN={injection_metrics['tn']})"
    )


def test_pattern_count_minimum():
    """Built-in pattern count must be >= 40 (drift prevention)."""
    from egress_audit.detectors.prompt_injection import _PATTERN_DEFS
    count = len(_PATTERN_DEFS)
    assert count >= 40, (
        f"Built-in pattern count {count} < 40 — "
        "PROMPT_INJECTION.md 문서와 코드가 불일치할 수 있습니다"
    )


def test_pattern_categories_match():
    """All categories used in _PATTERN_DEFS must match PATTERN_CATEGORIES."""
    from egress_audit.detectors.prompt_injection import (
        PATTERN_CATEGORIES,
        _PATTERN_DEFS,
    )
    used_categories = {cat for _, _, _, cat in _PATTERN_DEFS}
    declared = set(PATTERN_CATEGORIES)
    missing = used_categories - declared
    assert not missing, (
        f"_PATTERN_DEFS uses undeclared categories: {missing} — "
        "PATTERN_CATEGORIES에 추가하세요"
    )
    unused = declared - used_categories
    assert not unused, (
        f"PATTERN_CATEGORIES declares unused categories: {unused} — "
        "사용하지 않는 카테고리를 제거하세요"
    )


def test_run_benchmarks_injection_integration():
    """run_benchmarks(only='injection') returns passing injection results."""
    from enforcement.benchmark import run_benchmarks

    report = run_benchmarks(only="injection")
    inj = report["injection"]
    assert inj is not None, "injection 결과 누락"
    assert inj["recall"] >= 0.95, f"recall {inj['recall']:.4f} < 0.95"
    assert inj["pass"] is True, "injection benchmark did not pass"
    assert report["overall_pass"] is True, "overall_pass is False"
