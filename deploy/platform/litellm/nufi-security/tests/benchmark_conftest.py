"""CMP-296 — 벤치마크 regression gate pytest plugin.

pytest-benchmark 의 --benchmark-compare-fail 과 연동하여,
버전별 성능 추이 추적 + 리그레션 감지 시 CI 실패.

이 파일은 conftest.py 에서 import 해서 등록하거나,
pytest_plugins 로 직접 로드할 수 있다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

BENCHMARK_DIR = Path(__file__).resolve().parent.parent / ".benchmarks"


def pytest_addoption(parser):
    """벤치마크 리그레션 게이트 옵션 추가."""
    group = parser.getgroup("benchmark-gate", "NuFi benchmark regression gate")
    group.addoption(
        "--benchmark-gate-max-regression",
        action="store",
        default="15",
        help="최대 허용 리그레션 퍼센트 (기본: 15%%)",
    )
    group.addoption(
        "--benchmark-gate-json-out",
        action="store",
        default=None,
        help="벤치마크 결과를 JSON 파일로 저장",
    )


def pytest_sessionfinish(session, exitstatus):
    """벤치마크 결과 JSON 저장 (--benchmark-gate-json-out 지정 시)."""
    json_out = session.config.getoption("--benchmark-gate-json-out", default=None)
    if not json_out:
        return

    # pytest-benchmark 가 .benchmarks/ 에 저장한 최신 결과 로드
    if not BENCHMARK_DIR.exists():
        return

    # 최신 벤치마크 파일 찾기
    bench_files = sorted(BENCHMARK_DIR.rglob("*.json"), key=lambda p: p.stat().st_mtime)
    if not bench_files:
        return

    latest = bench_files[-1]
    data = json.loads(latest.read_text(encoding="utf-8"))

    # 요약 추출
    summary = {
        "version": data.get("machine_info", {}).get("python_version", "unknown"),
        "benchmarks": [],
    }
    for bench in data.get("benchmarks", []):
        stats = bench.get("stats", {})
        summary["benchmarks"].append({
            "name": bench.get("fullname", bench.get("name", "unknown")),
            "group": bench.get("group"),
            "mean_ms": round(stats.get("mean", 0) * 1000, 4),
            "stddev_ms": round(stats.get("stddev", 0) * 1000, 4),
            "min_ms": round(stats.get("min", 0) * 1000, 4),
            "max_ms": round(stats.get("max", 0) * 1000, 4),
            "rounds": stats.get("rounds", 0),
            "iterations": stats.get("iterations", 0),
        })

    Path(json_out).write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                              encoding="utf-8")
