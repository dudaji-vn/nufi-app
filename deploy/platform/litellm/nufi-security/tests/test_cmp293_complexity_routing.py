"""CMP-293: RouteLLM 복잡도 분류기 통합 테스트.

Phase 2 비용-품질 최적화: 복잡도 분류, A/B 테스트, 비용 대시보드.
"""
from __future__ import annotations

import pytest

from gateway.complexity_classifier import (
    ComplexityClassifier,
    ComplexityResult,
    extract_features,
    compute_score,
    COMPLEXITY_SIMPLE,
    COMPLEXITY_MODERATE,
    COMPLEXITY_COMPLEX,
)
from gateway.ab_testing import (
    ABTestManager,
    Experiment,
    ExperimentVariant,
    Assignment,
)
from gateway.cost_dashboard import CostDashboard


# ══════════════════════════════════════════════════════════════════════════
# 복잡도 분류기 (ComplexityClassifier)
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def classifier():
    return ComplexityClassifier(
        strong_model="gpt-4o",
        weak_model="gpt-4o-mini",
        threshold=0.5,
    )


class TestFeatureExtraction:
    """한국어 프롬프트 피처 추출."""

    def test_empty_text(self):
        features = extract_features("")
        assert features["token_count"] == 0.0
        assert features["sentence_count"] == 0.0

    def test_simple_korean(self):
        features = extract_features("파이썬에서 리스트를 정렬하는 방법")
        assert features["token_count"] > 0
        assert features["sentence_count"] >= 1
        assert features["technical_density"] == 0.0

    def test_technical_terms(self):
        text = "마이크로서비스 아키텍처에서 쿠버네티스 오케스트레이션 설정"
        features = extract_features(text)
        assert features["technical_density"] > 0

    def test_legal_terms(self):
        text = "개인정보보호법 제15조에 따른 동의 약관 작성"
        features = extract_features(text)
        assert features["legal_density"] > 0

    def test_medical_terms(self):
        text = "임상시험 프로토콜에서 투여 용량 결정"
        features = extract_features(text)
        assert features["medical_density"] > 0

    def test_multi_step(self):
        text = "먼저 데이터를 수집하고, 그 다음 전처리한 뒤, 마지막으로 모델을 학습시켜주세요"
        features = extract_features(text)
        assert features["multi_step_count"] >= 2

    def test_code_blocks(self):
        text = "다음 코드를 수정해주세요:\n```python\nprint('hello')\n```"
        features = extract_features(text)
        assert features["code_block_count"] >= 1

    def test_conditional(self):
        text = "만약 에러가 발생하면 재시도하고, 그렇지 않으면 결과를 반환"
        features = extract_features(text)
        assert features["conditional_count"] >= 1

    def test_comparison(self):
        text = "React와 Vue의 장단점을 비교해주세요"
        features = extract_features(text)
        assert features["comparison_count"] >= 1


class TestComplexityScore:
    """복잡도 점수 계산."""

    def test_simple_prompt_low_score(self):
        features = extract_features("안녕하세요")
        score = compute_score(features)
        assert score < 0.5

    def test_complex_prompt_high_score(self):
        text = (
            "마이크로서비스 아키텍처에서 분산 트랜잭션을 구현할 때 "
            "Saga 패턴과 2PC의 트레이드오프를 비교하고 "
            "먼저 각각의 구현 방법을 설명한 다음, "
            "쿠버네티스 환경에서의 장단점을 분석해주세요. "
            "만약 네트워크 파티션이 발생하면 어떻게 대응해야 하나요?"
        )
        features = extract_features(text)
        score = compute_score(features)
        assert score > 0.5

    def test_score_range(self):
        for text in ["hi", "안녕", "복잡한 기술 문서 " * 50]:
            features = extract_features(text)
            score = compute_score(features)
            assert 0.0 <= score <= 1.0


class TestComplexityClassifier:
    """ComplexityClassifier 라우팅 결정."""

    def test_simple_routes_to_weak(self, classifier):
        result = classifier.classify("안녕하세요. 오늘 날씨 어때요?")
        assert result.label == COMPLEXITY_SIMPLE
        assert result.target_model == "gpt-4o-mini"
        assert result.score < 0.5
        assert result.latency_ms >= 0

    def test_complex_routes_to_strong(self, classifier):
        text = (
            "마이크로서비스 아키텍처에서 데이터베이스 분산 트랜잭션의 "
            "Saga 패턴과 2PC 비교 분석. 먼저 각 패턴의 구현을 설명하고, "
            "그 다음 쿠버네티스 환경에서의 트레이드오프를 분석해주세요. "
            "만약 네트워크 장애가 발생하면 어떻게 대응하나요?"
        )
        result = classifier.classify(text)
        assert result.label in (COMPLEXITY_MODERATE, COMPLEXITY_COMPLEX)
        assert result.target_model == "gpt-4o"

    def test_disabled_returns_original(self):
        c = ComplexityClassifier()
        c.enabled = False
        result = c.classify("아무 텍스트", requested_model="my-model")
        assert result.target_model == "my-model"
        assert result.label == COMPLEXITY_SIMPLE
        assert result.score == 0.0

    def test_original_model_preserved(self, classifier):
        result = classifier.classify("간단한 질문", requested_model="custom-model")
        assert result.original_model == "custom-model"

    def test_result_to_dict(self, classifier):
        result = classifier.classify("테스트 프롬프트")
        d = result.to_dict()
        assert "score" in d
        assert "label" in d
        assert "target_model" in d
        assert "features" in d
        assert "latency_ms" in d

    def test_features_in_result(self, classifier):
        result = classifier.classify("쿠버네티스 아키텍처 설계")
        assert "token_count" in result.features
        assert "technical_density" in result.features


# ══════════════════════════════════════════════════════════════════════════
# A/B 테스트 프레임워크 (ABTestManager)
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def ab_manager():
    exp = Experiment(
        id="test_exp",
        name="Test Experiment",
        variants=[
            ExperimentVariant("control", "gpt-4o", 0.5),
            ExperimentVariant("treatment", "gpt-4o-mini", 0.5),
        ],
    )
    return ABTestManager(experiments=[exp])


class TestABTesting:
    """A/B 테스트 그룹 할당."""

    def test_deterministic_assignment(self, ab_manager):
        """같은 세션 → 같은 그룹."""
        a1 = ab_manager.assign("test_exp", "session-123")
        a2 = ab_manager.assign("test_exp", "session-123")
        assert a1.variant == a2.variant
        assert a1.model == a2.model

    def test_different_sessions_vary(self, ab_manager):
        """다른 세션 → 그룹이 달라질 수 있음 (확률적으로 검증)."""
        variants = set()
        for i in range(100):
            a = ab_manager.assign("test_exp", f"session-{i}")
            variants.add(a.variant)
        # 100개 세션에서 최소 2개 변형이 나와야 함 (50/50 분배)
        assert len(variants) == 2

    def test_disabled_experiment(self):
        exp = Experiment(id="disabled", name="Off", enabled=False)
        mgr = ABTestManager(experiments=[exp])
        result = mgr.assign("disabled", "session-1")
        assert result is None

    def test_unknown_experiment(self, ab_manager):
        result = ab_manager.assign("nonexistent", "session-1")
        assert result is None

    def test_assignment_to_dict(self, ab_manager):
        a = ab_manager.assign("test_exp", "session-1")
        d = a.to_dict()
        assert d["experiment_id"] == "test_exp"
        assert "variant" in d
        assert "model" in d


class TestABMetrics:
    """A/B 테스트 메트릭 수집."""

    def test_record_and_summary(self, ab_manager):
        ab_manager.record_metric("test_exp", "control", "gpt-4o",
                                 cost_usd=0.01, latency_ms=100)
        ab_manager.record_metric("test_exp", "treatment", "gpt-4o-mini",
                                 cost_usd=0.001, latency_ms=50)
        ab_manager.record_metric("test_exp", "control", "gpt-4o",
                                 cost_usd=0.015, latency_ms=120)

        summary = ab_manager.summary("test_exp")
        assert summary["total_observations"] == 3
        assert len(summary["variants"]) == 2

    def test_empty_summary(self, ab_manager):
        summary = ab_manager.summary()
        assert summary["total_observations"] == 0

    def test_quality_score(self, ab_manager):
        ab_manager.record_metric("test_exp", "control", "gpt-4o",
                                 quality_score=0.9)
        ab_manager.record_metric("test_exp", "control", "gpt-4o",
                                 quality_score=0.8)
        summary = ab_manager.summary("test_exp")
        variant_key = "test_exp:control"
        assert summary["variants"][variant_key]["avg_quality"] is not None

    def test_list_experiments(self, ab_manager):
        exps = ab_manager.list_experiments()
        assert len(exps) == 1
        assert exps[0]["id"] == "test_exp"
        assert len(exps[0]["variants"]) == 2


# ══════════════════════════════════════════════════════════════════════════
# 비용 대시보드 (CostDashboard)
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def dashboard():
    return CostDashboard(baseline_model="gpt-4o")


class TestCostDashboard:
    """비용 대시보드 통계."""

    def test_empty_dashboard(self, dashboard):
        s = dashboard.summary()
        assert s["total_requests"] == 0
        assert s["cost"]["actual_usd"] == 0.0

    def test_record_and_summary(self, dashboard):
        dashboard.record("gpt-4o", 1000, 500, routing_reason="no_pii")
        dashboard.record("gpt-4o-mini", 1000, 500,
                         complexity_label="simple")
        dashboard.record("local", 1000, 500,
                         routing_reason="pii_detected", is_local=True)

        s = dashboard.summary()
        assert s["total_requests"] == 3
        assert s["cost"]["actual_usd"] < s["cost"]["baseline_usd"]
        assert s["cost"]["savings_usd"] > 0
        assert s["cost"]["savings_pct"] > 0

    def test_routing_stats(self, dashboard):
        dashboard.record("local", 500, 200, routing_reason="pii_detected",
                         is_local=True)
        dashboard.record("gpt-4o-mini", 500, 200, complexity_label="simple")
        dashboard.record("gpt-4o", 500, 200, complexity_label="complex")

        stats = dashboard.routing_stats()
        assert stats.pii_routed == 1
        assert stats.complexity_simple == 1
        assert stats.complexity_complex == 1

    def test_cost_savings_pii(self, dashboard):
        # PII → 로컬 (무료) vs baseline (gpt-4o)
        dashboard.record("local", 1000, 500,
                         routing_reason="pii_detected", is_local=True)
        savings = dashboard.cost_savings()
        assert savings.pii_savings_usd > 0
        assert savings.actual_cost_usd == 0.0

    def test_cost_savings_complexity(self, dashboard):
        # 단순 → gpt-4o-mini (저렴) vs baseline (gpt-4o)
        dashboard.record("gpt-4o-mini", 1000, 500, complexity_label="simple")
        savings = dashboard.cost_savings()
        assert savings.complexity_savings_usd > 0

    def test_by_model_breakdown(self, dashboard):
        dashboard.record("gpt-4o", 500, 200)
        dashboard.record("gpt-4o-mini", 500, 200)
        dashboard.record("gpt-4o-mini", 500, 200)

        s = dashboard.summary()
        assert "gpt-4o" in s["by_model"]
        assert "gpt-4o-mini" in s["by_model"]
        assert s["by_model"]["gpt-4o-mini"]["requests"] == 2

    def test_render_ascii(self, dashboard):
        dashboard.record("gpt-4o", 1000, 500)
        dashboard.record("local", 500, 200, is_local=True)
        output = dashboard.render_ascii()
        assert "NuFi 비용 대시보드" in output
        assert "절약" in output


# ══════════════════════════════════════════════════════════════════════════
# 통합 테스트: PII + 복잡도 라우팅 파이프라인
# ══════════════════════════════════════════════════════════════════════════


class TestPhase2Integration:
    """Phase 1 (PII) + Phase 2 (복잡도) 통합 시나리오."""

    def test_pii_overrides_complexity(self):
        """PII 포함 시 복잡도 무관하게 로컬 라우팅."""
        from gateway.pii_router import PiiRouter

        pii_router = PiiRouter(local_model="local", cloud_model="cloud")
        classifier = ComplexityClassifier(
            strong_model="gpt-4o", weak_model="gpt-4o-mini",
        )

        text = "주민번호 900101-1234568 확인하고 마이크로서비스 아키텍처 분석"

        # Phase 1: PII 감지 → 로컬
        pii_decision = pii_router.route(text)
        assert pii_decision.routed_to_local
        assert pii_decision.target_model == "local"

        # Phase 2: 복잡도 분류 (PII 라우팅이 우선이므로 실제로는 스킵)
        complexity = classifier.classify(text)
        # 복잡도 자체는 높지만 PII가 있으므로 Phase 1이 우선
        assert complexity.score > 0  # 복잡도 점수는 계산됨

    def test_clean_simple_routes_to_weak(self):
        """PII 없고 단순 → 저비용 모델."""
        from gateway.pii_router import PiiRouter

        pii_router = PiiRouter(local_model="local", cloud_model="cloud")
        classifier = ComplexityClassifier(
            strong_model="gpt-4o", weak_model="gpt-4o-mini",
        )

        text = "안녕하세요. 오늘 날씨 어때요?"

        pii_decision = pii_router.route(text)
        assert not pii_decision.routed_to_local

        complexity = classifier.classify(text)
        assert complexity.label == COMPLEXITY_SIMPLE
        assert complexity.target_model == "gpt-4o-mini"

    def test_clean_complex_routes_to_strong(self):
        """PII 없고 복잡 → 고성능 모델."""
        from gateway.pii_router import PiiRouter

        pii_router = PiiRouter(local_model="local", cloud_model="cloud")
        classifier = ComplexityClassifier(
            strong_model="gpt-4o", weak_model="gpt-4o-mini",
        )

        text = (
            "마이크로서비스 아키텍처에서 데이터베이스 분산 트랜잭션을 "
            "구현할 때 Saga 패턴과 2PC의 트레이드오프를 비교하고 "
            "먼저 각각의 장단점을 설명한 다음, 쿠버네티스 환경에서의 "
            "디자인패턴 적용 방법을 분석해주세요."
        )

        pii_decision = pii_router.route(text)
        assert not pii_decision.routed_to_local

        complexity = classifier.classify(text)
        assert complexity.label in (COMPLEXITY_MODERATE, COMPLEXITY_COMPLEX)
        assert complexity.target_model == "gpt-4o"

    def test_mixed_workload_cost_savings(self):
        """혼합 워크로드에서 비용 절감 효과 검증."""
        from gateway.pii_router import PiiRouter

        pii_router = PiiRouter(local_model="local", cloud_model="cloud")
        classifier = ComplexityClassifier(
            strong_model="gpt-4o", weak_model="gpt-4o-mini",
        )
        dashboard = CostDashboard(baseline_model="gpt-4o")

        workload = [
            ("안녕하세요", False, "simple"),
            ("주민번호 900101-1234568", True, None),
            ("파이썬 리스트 정렬", False, "simple"),
            ("쿠버네티스 아키텍처 분석하고 비교해주세요", False, None),
            ("010-1234-5678로 연락주세요", True, None),
        ]

        for text, expect_pii, expect_label in workload:
            pii = pii_router.route(text)
            if pii.routed_to_local:
                assert expect_pii
                dashboard.record("local", 500, 200,
                                 routing_reason="pii_detected", is_local=True)
            else:
                cx = classifier.classify(text)
                dashboard.record(cx.target_model, 500, 200,
                                 complexity_label=cx.label)
                if expect_label:
                    assert cx.label == expect_label

        savings = dashboard.cost_savings()
        assert savings.savings_usd > 0
        assert savings.savings_pct > 0


# ══════════════════════════════════════════════════════════════════════════
# SDK 노출 테스트
# ══════════════════════════════════════════════════════════════════════════


class TestSDKExposure:
    """nufi SDK에서 Phase 2 API 접근."""

    def test_classify_complexity_importable(self):
        from nufi import classify_complexity
        result = classify_complexity("간단한 질문")
        assert isinstance(result, ComplexityResult)

    def test_complexity_classes_importable(self):
        from nufi import ComplexityClassifier, ComplexityResult, CostDashboard, ABTestManager
        assert ComplexityClassifier is not None
        assert ComplexityResult is not None
        assert CostDashboard is not None
        assert ABTestManager is not None

    def test_complexity_features_importable(self):
        from nufi import complexity_features
        features = complexity_features("테스트")
        assert "token_count" in features
