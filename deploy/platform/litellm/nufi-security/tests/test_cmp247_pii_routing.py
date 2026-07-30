"""CMP-247 PII 기반 하이브리드 라우팅 — 단위·통합 테스트.

검증 기준:
  1. PII 포함 요청 → 로컬 모델로 강제 라우팅 (pii_routed=True)
  2. PII 미포함 요청 → 기존 라우팅 흐름 (public/private 결정)
  3. PII 라우팅 비활성 시 → 기존 동작 그대로
  4. entity_types 필터링 → 지정 엔티티만 대상
  5. PiiRouter 클래스 — route/cost 기능
  6. Gateway 통합 — end-to-end PII 라우팅

실행: python3 tests/test_cmp247_pii_routing.py  (FAIL → exit 1)
      pytest tests/test_cmp247_pii_routing.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import EgressGuard, DetectionPipeline  # noqa: E402
from gateway.router import Router, RouteDecision, PIIRoutingConfig  # noqa: E402
from gateway.pii_router import PiiRouter, RoutingDecision  # noqa: E402
from gateway.pii_router import ROUTE_REASON_PII, ROUTE_REASON_CLEAN, ROUTE_REASON_ERROR  # noqa: E402
from gateway.core import Gateway  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(crit: str, ok: bool, detail: str = ""):
    results.append((crit, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {crit}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# 1. Router.resolve_for_pii — PII 라우팅 결정
# ---------------------------------------------------------------------------
def test_router_resolve_for_pii():
    """PII 엔티티 감지 시 로컬 백엔드로 라우팅."""
    print("\n=== Router.resolve_for_pii ===")
    router = Router()
    # PII 라우팅 활성화 상태 확인
    check("pii_routing.enabled", router.pii_routing.enabled,
          f"enabled={router.pii_routing.enabled}")

    # PII 감지 → 로컬 라우팅
    decision = router.resolve_for_pii("nufi-default", ["KR_RRN", "KR_PHONE"])
    check("pii→local", decision is not None and not decision.is_public,
          f"backend={decision.backend if decision else 'None'}")
    check("pii_routed flag", decision is not None and decision.pii_routed)
    check("pii_entity_types", decision is not None and "KR_RRN" in decision.pii_entity_types)

    # PII 없음 → None (기존 흐름)
    decision_none = router.resolve_for_pii("nufi-default", [])
    check("no_pii→None", decision_none is None)


def test_router_pii_entity_filter():
    """entity_types 필터: 지정 엔티티만 대상."""
    print("\n=== Router PII entity filter ===")
    router = Router()
    # entity_types 필터 설정
    router.pii_routing.entity_types = ["KR_RRN"]

    # RRN 감지 → 라우팅 됨
    decision = router.resolve_for_pii("nufi-default", ["KR_RRN"])
    check("filtered_rrn→local", decision is not None and decision.pii_routed)

    # PHONE만 감지 → 라우팅 안 됨 (필터에 없음)
    decision = router.resolve_for_pii("nufi-default", ["KR_PHONE"])
    check("filtered_phone→None", decision is None)

    # 복합: RRN+PHONE → RRN만 매칭
    decision = router.resolve_for_pii("nufi-default", ["KR_RRN", "KR_PHONE"])
    check("filtered_mixed→local", decision is not None and decision.pii_routed)
    check("filtered_mixed_entities", decision is not None and decision.pii_entity_types == ["KR_RRN"])

    # 정리
    router.pii_routing.entity_types = []


def test_router_pii_disabled():
    """PII 라우팅 비활성 시 → 항상 None."""
    print("\n=== Router PII disabled ===")
    router = Router()
    router.pii_routing.enabled = False

    decision = router.resolve_for_pii("nufi-default", ["KR_RRN"])
    check("disabled→None", decision is None)

    router.pii_routing.enabled = True


# ---------------------------------------------------------------------------
# 2. PiiRouter — 독립 PII 라우터 클래스
# ---------------------------------------------------------------------------
def test_pii_router_route():
    """PiiRouter: PII 텍스트 → 로컬, 클린 텍스트 → 클라우드."""
    print("\n=== PiiRouter.route ===")
    router = PiiRouter(local_model="test-local", cloud_model="test-cloud")

    # PII 포함 텍스트
    pii_text = "주민번호 900101-1234568 입니다"
    decision = router.route(pii_text)
    check("pii_text→local", decision.routed_to_local,
          f"target={decision.target_model}, reason={decision.reason}")
    check("pii_reason", decision.reason == ROUTE_REASON_PII)
    check("pii_target_model", decision.target_model == "test-local")
    check("pii_detected_flag", decision.pii_detected)
    check("pii_findings_count", len(decision.findings) > 0,
          f"findings={len(decision.findings)}")

    # 클린 텍스트
    clean_text = "오늘 날씨가 좋습니다"
    decision = router.route(clean_text)
    check("clean_text→cloud", not decision.routed_to_local,
          f"target={decision.target_model}, reason={decision.reason}")
    check("clean_reason", decision.reason == ROUTE_REASON_CLEAN)
    check("clean_target_model", decision.target_model == "test-cloud")


def test_pii_router_to_dict():
    """RoutingDecision.to_dict() 직렬화 검증."""
    print("\n=== RoutingDecision.to_dict ===")
    router = PiiRouter(local_model="test-local", cloud_model="test-cloud")
    decision = router.route("전화번호 010-1234-5678 알려드립니다")
    d = decision.to_dict()
    check("to_dict_keys", all(k in d for k in ("target_model", "reason", "pii_detected",
                                                 "routed_to_local", "entity_types")))
    check("to_dict_entity_types", isinstance(d["entity_types"], list))
    check("to_dict_latency", d["latency_ms"] >= 0)


def test_pii_router_cost():
    """PiiRouter 비용 추적."""
    print("\n=== PiiRouter cost tracking ===")
    router = PiiRouter(local_model="test-local", cloud_model="test-cloud")

    # 로컬 비용 (0)
    rec = router.record_cost("test-local", "local", True,
                             prompt_tokens=100, completion_tokens=50)
    check("local_cost_zero", rec.estimated_cost_usd == 0.0)

    # 클라우드 비용 (>0)
    rec = router.record_cost("gpt-4o", "openai", False,
                             prompt_tokens=1000, completion_tokens=500)
    check("cloud_cost_positive", rec.estimated_cost_usd > 0,
          f"cost=${rec.estimated_cost_usd:.6f}")

    summary = router.cost_summary()
    check("cost_summary_total", summary["total_requests"] == 2)
    check("cost_summary_local", summary["local_requests"] == 1)
    check("cost_summary_cloud", summary["cloud_requests"] == 1)


# ---------------------------------------------------------------------------
# 3. Gateway 통합 — PII 라우팅 end-to-end
# ---------------------------------------------------------------------------
def test_gateway_pii_routing():
    """Gateway: public 경로의 PII 포함 요청이 로컬로 강제 라우팅되는 end-to-end.

    PII 라우팅은 public 경로로 해석된 요청에만 적용된다.
    이미 private인 요청은 PII 라우팅이 불필요하므로 기존 흐름 유지.
    """
    print("\n=== Gateway PII routing (end-to-end) ===")
    import os
    gw = Gateway(ner_backend="gazetteer")

    # PII 포함 + public 강제 (EGRESS_PRIVATE_DOWN=1) → PII 라우팅으로 로컬 전환
    os.environ["EGRESS_PRIVATE_DOWN"] = "1"
    pii_body = {
        "model": "nufi-default",
        "messages": [{"role": "user", "content": "주민번호 900101-1234568 조회해줘"}],
    }
    resp = gw.process(pii_body)
    check("pii_public_status_200", resp.status == 200)
    check("pii_public_outcome", resp.outcome == "pii_routed",
          f"outcome={resp.outcome}")
    check("pii_public_private_route", not resp.route.is_public,
          f"egress_class={resp.route.egress_class}")
    check("pii_public_pii_routed", resp.route.pii_routed)

    # 클린 + public 강제 → 기존 public 라우팅 (PII 라우팅 미적용)
    clean_body = {
        "model": "nufi-default",
        "messages": [{"role": "user", "content": "오늘 날씨가 좋습니다"}],
    }
    resp = gw.process(clean_body)
    check("clean_public_not_pii_routed", resp.outcome != "pii_routed",
          f"outcome={resp.outcome}")
    os.environ["EGRESS_PRIVATE_DOWN"] = "0"

    # PII 포함 + private 기본 → PII 라우팅 불필요 (이미 private)
    pii_private_body = {
        "model": "nufi-default",
        "messages": [{"role": "user", "content": "주민번호 900101-1234568 조회해줘"}],
    }
    resp = gw.process(pii_private_body)
    check("pii_private_outcome", resp.outcome == "private",
          f"outcome={resp.outcome}")
    check("pii_private_not_pii_routed", not resp.route.pii_routed)


def test_gateway_pii_routing_disabled():
    """PII 라우팅 비활성 시 → 기존 동작."""
    print("\n=== Gateway PII routing disabled ===")
    gw = Gateway(ner_backend="gazetteer")
    gw.router.pii_routing.enabled = False

    pii_body = {
        "model": "nufi-default",
        "messages": [{"role": "user", "content": "주민번호 900101-1234568"}],
    }
    resp = gw.process(pii_body)
    check("disabled_not_pii_routed", resp.outcome != "pii_routed",
          f"outcome={resp.outcome}")
    check("disabled_route_no_pii_flag", not resp.route.pii_routed)

    # 정리
    gw.router.pii_routing.enabled = True


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_router_resolve_for_pii()
    test_router_pii_entity_filter()
    test_router_pii_disabled()
    test_pii_router_route()
    test_pii_router_to_dict()
    test_pii_router_cost()
    test_gateway_pii_routing()
    test_gateway_pii_routing_disabled()

    print("\n" + "=" * 60)
    fails = [r for r in results if not r[1]]
    print(f"Total: {len(results)} checks, {len(results) - len(fails)} PASS, {len(fails)} FAIL")
    if fails:
        for name, _, detail in fails:
            print(f"  FAIL: {name}" + (f" — {detail}" if detail else ""))
        sys.exit(1)
    print("All checks passed.")
