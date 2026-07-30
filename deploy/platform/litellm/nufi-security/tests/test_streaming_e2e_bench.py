"""스트리밍 E2E 가명화 벤치마크 테스트 (CMP-366).

StreamingDeanonymizer 가 다양한 청크 크기에서
비스트리밍 deanonymize() 와 동일한 결과를 생성하는지 검증.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.bench_streaming_e2e import (  # noqa: E402
    EVAL_SET,
    TARGETS,
    run_streaming_benchmark,
    split_fixed,
    split_random,
)
from egress_audit import ReversibleEgress  # noqa: E402
from egress_audit.surrogate import StreamingDeanonymizer, deanonymize  # noqa: E402


# ── 유틸 함수 테스트 ────────────────────────────────────────────────────────
class TestSplitFixed:
    def test_exact_division(self):
        chunks = split_fixed("abcdef", 3)
        assert chunks == ["abc", "def"]

    def test_remainder(self):
        chunks = split_fixed("abcde", 3)
        assert chunks == ["abc", "de"]

    def test_single_char(self):
        chunks = split_fixed("abc", 1)
        assert chunks == ["a", "b", "c"]

    def test_larger_than_text(self):
        chunks = split_fixed("ab", 10)
        assert chunks == ["ab"]

    def test_empty(self):
        chunks = split_fixed("", 5)
        assert chunks == []


class TestSplitRandom:
    def test_covers_full_text(self):
        rng = random.Random(42)
        text = "hello world streaming test"
        chunks = split_random(text, rng)
        assert "".join(chunks) == text

    def test_all_nonempty(self):
        rng = random.Random(42)
        chunks = split_random("abcdefghij", rng)
        assert all(len(c) > 0 for c in chunks)

    def test_deterministic(self):
        text = "deterministic test"
        c1 = split_random(text, random.Random(42))
        c2 = split_random(text, random.Random(42))
        assert c1 == c2


# ── 단위 스트리밍 테스트 ─────────────────────────────────────────────────────
class TestStreamingDeanonymizerUnit:
    """StreamingDeanonymizer 가 다양한 청크 경계에서 비스트리밍과 일치."""

    def _roundtrip(self, text: str, chunk_size: int):
        """가명화 → 비스트리밍 원복 vs 스트리밍 원복 비교."""
        rev = ReversibleEgress()
        sid = "unit-stream"
        res = rev.pseudonymize(text, sid)
        if res.blocked:
            rev.end_session(sid)
            return  # 차단된 경우 스킵
        echo = res.transformed_text
        nonstream, _ = rev.deanonymize(echo, sid)

        restorer = rev.stream_restorer(sid)
        chunks = split_fixed(echo, chunk_size)
        stream_out = "".join(restorer.feed(c) for c in chunks)
        stream_out += restorer.flush()

        rev.end_session(sid)
        assert stream_out == nonstream, (
            f"chunk_size={chunk_size}\n"
            f"  nonstream: {nonstream!r}\n"
            f"  stream:    {stream_out!r}"
        )

    @pytest.mark.parametrize("chunk_size", [1, 2, 3, 5, 7, 10])
    def test_single_entity(self, chunk_size):
        self._roundtrip("고객 김민수님의 계정을 확인합니다.", chunk_size)

    @pytest.mark.parametrize("chunk_size", [1, 3, 5])
    def test_multi_entity(self, chunk_size):
        self._roundtrip(
            "담당자 박지영님 연락처 010-9876-5432, 이메일 park@example.com 입니다.",
            chunk_size,
        )

    @pytest.mark.parametrize("chunk_size", [1, 3, 5])
    def test_no_entity(self, chunk_size):
        """PII 없는 텍스트 — 스트리밍도 원문 그대로."""
        rev = ReversibleEgress()
        sid = "unit-no-pii"
        text = "오늘 날씨가 맑습니다."
        res = rev.pseudonymize(text, sid)
        echo = res.transformed_text

        restorer = rev.stream_restorer(sid)
        chunks = split_fixed(echo, chunk_size)
        stream_out = "".join(restorer.feed(c) for c in chunks)
        stream_out += restorer.flush()

        assert stream_out == echo
        rev.end_session(sid)


# ── E2E 파이프라인 통합 테스트 ────────────────────────────────────────────
class TestStreamingE2EPipeline:
    @pytest.fixture(scope="class")
    def report(self):
        """170 샘플 전체에 대한 스트리밍 벤치마크 실행."""
        if not EVAL_SET.exists():
            pytest.skip("평가셋 파일 없음")
        return run_streaming_benchmark()

    def test_report_structure(self, report):
        assert report["benchmark"] == "streaming-e2e-quality"
        assert "scores" in report
        assert "by_chunk_size" in report
        assert "acceptance" in report
        assert "by_category" in report

    def test_has_samples(self, report):
        assert report["n_samples"] > 0

    def test_streaming_match_rate_target(self, report):
        """Streaming Match Rate == 1.0."""
        rate = report["scores"]["streaming_match_rate"]
        assert rate >= TARGETS["streaming_match_rate"], (
            f"Streaming Match Rate {rate:.4f} < 목표 {TARGETS['streaming_match_rate']}")

    def test_all_chunk_sizes_present(self, report):
        """모든 청크 크기가 결과에 포함."""
        expected = {"1", "3", "5", "10", "random"}
        actual = set(report["by_chunk_size"].keys())
        assert expected == actual, f"누락 청크 크기: {expected - actual}"

    def test_per_chunk_match_rates(self, report):
        """각 청크 크기별 매치율 == 1.0."""
        for label, data in report["by_chunk_size"].items():
            assert data["match_rate"] >= 1.0, (
                f"chunk={label} match_rate={data['match_rate']:.4f} < 1.0")

    def test_no_mismatches(self, report):
        """불일치 샘플 0건."""
        assert report["n_mismatches"] == 0, (
            f"불일치 {report['n_mismatches']}건: {report['mismatches'][:3]}")

    def test_latency_present(self, report):
        """레이턴시 측정값 존재."""
        for label, data in report["by_chunk_size"].items():
            assert data["latency_ms"]["p50"] >= 0

    def test_category_coverage(self, report):
        """카테고리별 매치율 존재."""
        assert len(report["by_category"]) > 0

    def test_acceptance_pass(self, report):
        """게이트 전체 통과."""
        assert report["acceptance_pass"] is True

    def test_json_serializable(self, report):
        """리포트가 JSON 직렬화 가능."""
        out = json.dumps(report, ensure_ascii=False)
        parsed = json.loads(out)
        assert parsed["benchmark"] == report["benchmark"]
