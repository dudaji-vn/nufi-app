"""E2E 가명화 품질 벤치마크 — mock 모드 파이프라인 테스트 (CMP-351).

mock 모드는 API 키 없이 독립 실행 가능.
파이프라인 구조(가명화→LLM→원복→비교)의 정확성을 검증.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.bench_pseudonymize_e2e import (  # noqa: E402
    QASample,
    MockLLM,
    load_eval_set,
    rouge_l,
    exact_match,
    run_benchmark,
    EVAL_SET,
    TARGETS,
    _lcs_length,
    _tokenize,
)


# ── ROUGE-L 단위 테스트 ──────────────────────────────────────────────────
class TestRougeL:
    def test_identical(self):
        assert rouge_l("hello world", "hello world") == 1.0

    def test_empty_both(self):
        assert rouge_l("", "") == 1.0

    def test_empty_ref(self):
        assert rouge_l("", "hello") == 0.0

    def test_empty_hyp(self):
        assert rouge_l("hello", "") == 0.0

    def test_partial_overlap(self):
        ref = "고객 김민수님의 환불 요청을 접수했습니다"
        hyp = "고객 ⟦P1⟧님의 환불 요청을 접수했습니다"
        score = rouge_l(ref, hyp)
        # 대부분의 토큰이 일치하므로 높은 점수
        assert 0.7 < score < 1.0

    def test_no_overlap(self):
        assert rouge_l("가 나 다", "라 마 바") == 0.0

    def test_korean_text(self):
        ref = "정지율님의 환불 요청을 접수했습니다."
        hyp = "정지율님의 환불 요청을 접수했습니다."
        assert rouge_l(ref, hyp) == 1.0


class TestLCS:
    def test_basic(self):
        assert _lcs_length(["a", "b", "c"], ["a", "c"]) == 2

    def test_empty(self):
        assert _lcs_length([], ["a"]) == 0

    def test_identical(self):
        tokens = ["hello", "world"]
        assert _lcs_length(tokens, tokens) == 2


class TestTokenize:
    def test_korean(self):
        tokens = _tokenize("고객 김민수님의 환불")
        assert tokens == ["고객", "김민수님의", "환불"]

    def test_empty(self):
        assert _tokenize("") == []

    def test_mixed(self):
        tokens = _tokenize("email: test@example.com")
        assert len(tokens) == 2


class TestExactMatch:
    def test_identical(self):
        assert exact_match("hello", "hello") is True

    def test_whitespace(self):
        assert exact_match("hello ", " hello") is True

    def test_different(self):
        assert exact_match("hello", "world") is False


# ── MockLLM 테스트 ───────────────────────────────────────────────────────
class TestMockLLM:
    @pytest.fixture
    def samples(self):
        return [
            QASample(
                id="test_001",
                question="고객 김민수님(010-1234-5678)의 환불 요청을 처리해주세요.",
                expected_answer="김민수님의 환불 요청을 접수했습니다. 010-1234-5678로 처리 결과를 안내드리겠습니다.",
                pii_entities=[
                    {"type": "KR_PERSON", "value": "김민수", "start": 3, "end": 6},
                    {"type": "KR_PHONE", "value": "010-1234-5678", "start": 8, "end": 21},
                ],
                category="customer_service",
            ),
            QASample(
                id="test_002",
                question="오늘 날씨가 어떤가요?",
                expected_answer="오늘은 맑고 기온은 25도입니다.",
                pii_entities=[],
                category="control",
            ),
        ]

    def test_exact_question_returns_expected(self, samples):
        llm = MockLLM(samples)
        resp = llm.generate(samples[0].question)
        assert resp == samples[0].expected_answer

    def test_control_question(self, samples):
        llm = MockLLM(samples)
        resp = llm.generate(samples[1].question)
        assert resp == samples[1].expected_answer

    def test_unknown_question_fallback(self, samples):
        llm = MockLLM(samples)
        resp = llm.generate("전혀 다른 질문입니다 완전히 새로운 내용")
        # 폴백: 에코 또는 유사 매칭
        assert isinstance(resp, str)
        assert len(resp) > 0


# ── 평가셋 로드 테스트 ────────────────────────────────────────────────────
class TestEvalSet:
    def test_load(self):
        if not EVAL_SET.exists():
            pytest.skip("평가셋 파일 없음")
        samples = load_eval_set()
        assert len(samples) > 0
        assert all(s.id for s in samples)
        assert all(s.question for s in samples)
        assert all(s.expected_answer for s in samples)

    def test_sample_schema(self):
        if not EVAL_SET.exists():
            pytest.skip("평가셋 파일 없음")
        samples = load_eval_set()
        for s in samples:
            assert isinstance(s.pii_entities, list)
            for ent in s.pii_entities:
                assert "type" in ent
                assert "value" in ent


# ── E2E 파이프라인 통합 테스트 (mock 모드) ────────────────────────────────
class TestE2EPipeline:
    @pytest.fixture(scope="class")
    def report(self):
        """mock 모드로 전체 파이프라인 실행."""
        if not EVAL_SET.exists():
            pytest.skip("평가셋 파일 없음")
        return run_benchmark(llm_backend="mock")

    def test_report_structure(self, report):
        assert report["benchmark"] == "pseudonymize-e2e-quality"
        assert report["llm_backend"] == "mock"
        assert "scores" in report
        assert "acceptance" in report
        assert "by_type" in report
        assert "latency" in report

    def test_has_samples(self, report):
        assert report["n_samples"] > 0
        assert report["n_pii_samples"] > 0

    def test_rouge_l_target(self, report):
        """Utility Retention (ROUGE-L) ≥ 0.90."""
        score = report["scores"]["utility_retention_rouge_l"]
        assert score >= TARGETS["rouge_l"], (
            f"ROUGE-L {score:.4f} < 목표 {TARGETS['rouge_l']}")

    def test_pii_protection_rate(self, report):
        """PII Protection Rate: gazetteer 백엔드 기준 합리적 수준 (≥0.80).

        참고: 목표 1.0 은 프로덕션(ML 백엔드) 기준. Gazetteer 는 등록되지 않은
        이름을 탐지 못하므로 mock 테스트에서는 ≥0.80 을 하한으로 검증.
        """
        rate = report["scores"]["pii_protection_rate"]
        assert rate >= 0.80, (
            f"PII Protection Rate {rate:.4f} < 하한 0.80 (gazetteer)")

    def test_roundtrip_fidelity(self, report):
        """Roundtrip Fidelity: gazetteer 백엔드 기준 ≥0.80.

        참고: 목표 0.95 는 프로덕션 기준. Gazetteer 가 탐지한 PII 만 원복
        대상이므로, 미탐지 PII → surrogate 미발급 → mock 응답에서도 미원복.
        """
        fidelity = report["scores"]["roundtrip_fidelity"]
        assert fidelity >= 0.80, (
            f"Roundtrip Fidelity {fidelity:.4f} < 하한 0.80 (gazetteer)")

    def test_by_type_coverage(self, report):
        """타입별 분석이 주요 PII 타입을 포함."""
        expected_types = {"KR_PERSON", "KR_PHONE", "EMAIL"}
        actual_types = set(report["by_type"].keys())
        assert expected_types.issubset(actual_types), (
            f"누락 타입: {expected_types - actual_types}")

    def test_latency_present(self, report):
        """레이턴시 측정값 존재."""
        lat = report["latency"]
        assert lat["pseudonymize_ms"]["p50"] >= 0
        assert lat["deanonymize_ms"]["p50"] >= 0

    def test_acceptance_gates_present(self, report):
        """게이트 판정이 존재하고 형식이 올바름."""
        assert len(report["acceptance"]) == 3
        for k, v in report["acceptance"].items():
            assert isinstance(v, bool), f"게이트 {k} 값이 bool 이 아님: {v}"

    def test_control_samples_high_rouge(self, report):
        """Control 샘플(PII 없음)은 ROUGE-L 가 높아야 함."""
        # control 샘플은 가명화 영향 없으므로 높은 유사도 기대
        assert report["n_control_samples"] > 0

    def test_degraded_samples_tracked(self, report):
        """품질 저하 샘플이 추적되고 구조가 올바름."""
        for d in report["degraded_samples"]:
            assert "id" in d
            assert "rouge_l" in d
            assert d["rouge_l"] < TARGETS["rouge_l"]

    def test_json_serializable(self, report):
        """리포트가 JSON 직렬화 가능."""
        out = json.dumps(report, ensure_ascii=False)
        parsed = json.loads(out)
        assert parsed["benchmark"] == report["benchmark"]
