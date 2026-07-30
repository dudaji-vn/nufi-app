"""Unified benchmark (accuracy + pseudonymize + injection) 테스트 (patch127)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_run_benchmarks_includes_injection():
    """run_benchmarks(only='injection') 이 인젝션 메트릭을 반환해야 한다."""
    from enforcement.benchmark import run_benchmarks

    report = run_benchmarks(only="injection")

    assert report["injection"] is not None, "injection 결과가 없습니다"
    assert report["accuracy"] is None, "only=injection 인데 accuracy 가 포함됨"
    assert report["pseudonymize"] is None, "only=injection 인데 pseudonymize 가 포함됨"

    inj = report["injection"]
    assert "recall" in inj
    assert "precision" in inj
    assert "f1" in inj
    assert "gates" in inj
    assert len(inj["gates"]) == 2

    # 인젝션 벤치마크가 통과해야 함 (recall/precision >= 0.90)
    assert inj["pass"] is True, (
        f"인젝션 벤치마크 실패: recall={inj['recall']:.4f}, precision={inj['precision']:.4f}"
    )
    assert report["overall_pass"] is True


def test_run_benchmarks_all_includes_injection():
    """run_benchmarks(only=None) 이 인젝션을 포함한 전체 결과를 반환해야 한다."""
    from enforcement.benchmark import run_benchmarks

    report = run_benchmarks(only=None)

    assert report["injection"] is not None, "전체 벤치마크에 injection 이 누락"
    assert report["accuracy"] is not None, "전체 벤치마크에 accuracy 가 누락"
    assert report["pseudonymize"] is not None, "전체 벤치마크에 pseudonymize 가 누락"

    # injection 게이트 구조 검증
    inj = report["injection"]
    assert inj["benchmark"] == "injection"
    gate_ids = {g["id"] for g in inj["gates"]}
    assert "injection_recall" in gate_ids
    assert "injection_precision" in gate_ids
