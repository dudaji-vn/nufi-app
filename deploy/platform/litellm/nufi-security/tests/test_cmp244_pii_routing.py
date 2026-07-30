"""CMP-244: PII 기반 하이브리드 LLM 라우팅 테스트.

PII 포함/미포함 요청의 라우팅 결정을 검증한다.
"""
from __future__ import annotations

import pytest

from gateway.pii_router import (
    PiiRouter, RoutingDecision, CostRecord,
    ROUTE_REASON_PII, ROUTE_REASON_CLEAN, ROUTE_REASON_ERROR,
)


@pytest.fixture
def router():
    return PiiRouter(
        local_model="test-local",
        cloud_model="test-cloud",
    )


# ── 기본 라우팅 결정 ──


class TestPiiRouting:
    """PII 감지 결과에 따른 라우팅 분기."""

    def test_clean_text_routes_to_cloud(self, router):
        """PII 없는 텍스트 → 클라우드 허용."""
        decision = router.route("파이썬에서 리스트를 정렬하는 방법")
        assert decision.target_model == "test-cloud"
        assert decision.reason == ROUTE_REASON_CLEAN
        assert not decision.pii_detected
        assert not decision.routed_to_local
        assert decision.latency_ms > 0

    def test_rrn_routes_to_local(self, router):
        """주민등록번호 포함 → 로컬 강제."""
        decision = router.route("주민번호 900101-1234568 확인")
        assert decision.target_model == "test-local"
        assert decision.reason == ROUTE_REASON_PII
        assert decision.pii_detected
        assert decision.routed_to_local
        assert any(f.entity_type == "KR_RRN" for f in decision.findings)

    def test_phone_routes_to_local(self, router):
        """전화번호 포함 → 로컬 강제."""
        decision = router.route("연락처 010-1234-5678 입니다")
        assert decision.target_model == "test-local"
        assert decision.pii_detected

    def test_email_routes_to_local(self, router):
        """이메일 포함 → 로컬 강제."""
        decision = router.route("메일 주소: user@example.com")
        assert decision.target_model == "test-local"
        assert decision.pii_detected

    def test_credit_card_routes_to_local(self, router):
        """신용카드 포함 → 로컬 강제."""
        decision = router.route("카드번호 4532-0151-2345-6789")
        assert decision.target_model == "test-local"
        assert decision.pii_detected

    def test_brn_routes_to_local(self, router):
        """사업자등록번호 포함 → 로컬 강제."""
        decision = router.route("사업자등록번호 123-45-67890")
        assert decision.target_model == "test-local"
        assert decision.pii_detected

    def test_multiple_pii_routes_to_local(self, router):
        """다중 PII → 로컬 강제, 모든 findings 포함."""
        text = "김민수 010-1234-5678 주민번호 900101-1234568"
        decision = router.route(text)
        assert decision.target_model == "test-local"
        assert len(decision.findings) >= 2

    def test_english_clean_text(self, router):
        """영어 일반 텍스트 → 클라우드."""
        decision = router.route("How to implement a binary search tree?")
        assert decision.target_model == "test-cloud"
        assert not decision.pii_detected


# ── 선택적 엔티티 필터링 ──


class TestEntityFiltering:
    """force_local_entities 로 특정 엔티티만 로컬 라우팅."""

    def test_filter_rrn_only(self):
        """주민번호만 로컬 강제, 이메일은 클라우드 허용."""
        router = PiiRouter(
            local_model="local", cloud_model="cloud",
            force_local_entities={"KR_RRN"},
        )
        # 이메일만 → 클라우드
        d1 = router.route("user@example.com 으로 보내세요")
        assert d1.target_model == "cloud"

        # 주민번호 → 로컬
        d2 = router.route("주민번호 900101-1234568")
        assert d2.target_model == "local"

    def test_filter_multiple_entities(self):
        """복수 엔티티 타입 필터."""
        router = PiiRouter(
            local_model="local", cloud_model="cloud",
            force_local_entities={"KR_RRN", "CREDIT_CARD"},
        )
        d = router.route("전화 010-1234-5678")
        assert d.target_model == "cloud"  # 전화번호는 필터 밖


# ── Fail-closed ──


class TestFailClosed:
    """감지 오류 시 안전 폴백."""

    def test_detection_error_routes_to_local(self):
        """파이프라인 예외 → 로컬 폴백."""
        router = PiiRouter(local_model="safe-local", cloud_model="cloud")
        # 파이프라인을 고장낸다
        original_analyze = router.pipeline.analyze
        def broken_analyze(text):
            raise RuntimeError("simulated pipeline crash")
        router.pipeline.analyze = broken_analyze

        decision = router.route("아무 텍스트")
        assert decision.target_model == "safe-local"
        assert decision.reason == ROUTE_REASON_ERROR
        assert not decision.pii_detected

        router.pipeline.analyze = original_analyze  # 복원


# ── RoutingDecision ──


class TestRoutingDecision:
    """RoutingDecision 데이터 구조."""

    def test_to_dict(self, router):
        decision = router.route("주민번호 900101-1234568")
        d = decision.to_dict()
        assert d["target_model"] == "test-local"
        assert d["pii_detected"] is True
        assert d["routed_to_local"] is True
        assert "KR_RRN" in d["entity_types"]
        assert d["latency_ms"] > 0

    def test_original_model_preserved(self, router):
        decision = router.route("일반 질문", requested_model="gpt-4o")
        assert decision.original_model == "gpt-4o"


# ── 비용 추적 ──


class TestCostTracking:
    """모델별 비용 추적."""

    def test_cloud_cost_positive(self, router):
        record = router.record_cost("gpt-4o", "openai", False,
                                    prompt_tokens=1000, completion_tokens=500)
        assert record.estimated_cost_usd > 0
        assert not record.is_local

    def test_local_cost_zero(self, router):
        record = router.record_cost("test-local", "local", True,
                                    prompt_tokens=1000, completion_tokens=500)
        assert record.estimated_cost_usd == 0.0
        assert record.is_local

    def test_cost_summary(self, router):
        router.record_cost("gpt-4o", "openai", False, 1000, 500)
        router.record_cost("test-local", "local", True, 1000, 500)
        router.record_cost("gpt-4o", "openai", False, 500, 200)

        summary = router.cost_summary()
        assert summary["total_requests"] == 3
        assert summary["local_requests"] == 1
        assert summary["cloud_requests"] == 2
        assert summary["cloud_cost_usd"] > 0
        assert summary["local_cost_usd"] == 0.0

    def test_estimate_cost_prefix_match(self, router):
        """모델명 접두사 매치."""
        cost = router.estimate_cost("claude-3-5-sonnet-20241022", 1000, 500)
        assert cost > 0

    def test_estimate_cost_unknown_model(self, router):
        """미등록 모델 → 0 비용 (local 폴백)."""
        cost = router.estimate_cost("unknown-model-xyz", 1000, 500)
        assert cost == 0.0


# ── 통합 시나리오 ──


class TestIntegration:
    """E2E 라우팅 + 비용 추적."""

    def test_mixed_workload(self, router):
        """혼합 워크로드: PII/비PII 요청의 올바른 분류."""
        cases = [
            ("일반 질문입니다", False),
            ("주민번호 900101-1234568", True),
            ("코드 리뷰 부탁", False),
            ("010-1234-5678 전화주세요", True),
            ("REST API 설계", False),
        ]
        for text, expect_local in cases:
            decision = router.route(text)
            assert decision.routed_to_local == expect_local, \
                f"'{text}' → expected local={expect_local}, got {decision.routed_to_local}"
            router.record_cost(
                decision.target_model,
                "local" if decision.routed_to_local else "cloud",
                decision.routed_to_local,
                prompt_tokens=100, completion_tokens=50,
            )

        summary = router.cost_summary()
        assert summary["total_requests"] == 5
        assert summary["local_requests"] == 2
        assert summary["cloud_requests"] == 3
