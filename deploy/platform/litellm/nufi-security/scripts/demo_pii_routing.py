#!/usr/bin/env python3
"""PII 기반 하이브리드 LLM 라우팅 데모 (CMP-244).

LiteLLM 프록시 없이도 PII 라우팅 로직을 검증할 수 있는 end-to-end 데모.
실행: python scripts/demo_pii_routing.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.pii_router import PiiRouter


def _banner(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def _show_result(label: str, text: str, decision) -> None:
    status = "🔒 LOCAL" if decision.routed_to_local else "☁️  CLOUD"
    print(f"\n[{label}] {status}")
    print(f"  입력: {text[:80]}{'…' if len(text)>80 else ''}")
    print(f"  모델: {decision.original_model} → {decision.target_model}")
    print(f"  사유: {decision.reason}")
    if decision.findings:
        entities = sorted({f.entity_type for f in decision.findings})
        print(f"  감지: {', '.join(entities)}")
    print(f"  지연: {decision.latency_ms:.1f}ms")


def main() -> None:
    router = PiiRouter(
        local_model="nufi-local",
        cloud_model="nufi-cloud",
    )

    # ── 시나리오 1: PII 없는 일반 질문 → 클라우드 허용 ──
    _banner("시나리오 1: PII 없는 일반 질문")
    test_cases_clean = [
        ("일반 질문", "파이썬에서 리스트를 정렬하는 방법을 알려주세요."),
        ("코드 리뷰", "이 코드의 시간 복잡도를 분석해 주세요: for i in range(n): for j in range(n): pass"),
        ("번역 요청", "Please translate the following to Korean: Hello, how are you?"),
    ]
    for label, text in test_cases_clean:
        decision = router.route(text)
        _show_result(label, text, decision)
        # 클라우드 비용 시뮬레이션
        router.record_cost(decision.target_model, "cloud", False,
                           prompt_tokens=len(text) * 2, completion_tokens=200)

    # ── 시나리오 2: PII 포함 요청 → 로컬 강제 ──
    _banner("시나리오 2: PII 포함 요청")
    test_cases_pii = [
        ("주민등록번호", "고객 김민수의 주민등록번호는 900101-1234568 입니다. 이 정보를 분석해주세요."),
        ("전화번호+이름", "박서연 과장에게 010-1234-5678로 연락해서 회의 일정을 잡아주세요."),
        ("이메일", "john.doe@example.com 으로 보고서를 보내주세요."),
        ("신용카드", "결제 카드번호 4532-0151-2345-6789 로 처리해 주세요."),
        ("사업자등록번호", "우리 회사 사업자등록번호 123-45-67890 을 확인해주세요."),
    ]
    for label, text in test_cases_pii:
        decision = router.route(text)
        _show_result(label, text, decision)
        # 로컬 비용 시뮬레이션 (비용 0)
        router.record_cost(decision.target_model, "local", True,
                           prompt_tokens=len(text) * 2, completion_tokens=200)

    # ── 시나리오 3: 혼합 워크로드 시뮬레이션 ──
    _banner("시나리오 3: 혼합 워크로드 (10건)")
    mixed_workload = [
        "오늘 날씨가 어떤가요?",
        "김철수의 전화번호 010-9876-5432를 메모해두세요.",
        "REST API 설계 원칙을 설명해주세요.",
        "주민번호 850315-2345679 소유자 정보를 조회합니다.",
        "Kubernetes 파드 스케줄링은 어떻게 동작하나요?",
        "고객 이메일 customer@company.co.kr 로 안내문을 보내세요.",
        "Git rebase와 merge의 차이점은?",
        "계좌번호 110-123-456789로 이체해 주세요.",
        "Docker 컨테이너와 VM의 차이는?",
        "박지성 선수의 경력을 알려주세요.",
    ]
    for i, text in enumerate(mixed_workload, 1):
        decision = router.route(text)
        is_local = decision.routed_to_local
        router.record_cost(
            decision.target_model,
            "local" if is_local else "cloud",
            is_local,
            prompt_tokens=len(text) * 2,
            completion_tokens=200,
        )
        status = "LOCAL" if is_local else "CLOUD"
        entities = ",".join(sorted({f.entity_type for f in decision.findings})) or "-"
        print(f"  [{i:2d}] {status:5s} | {entities:20s} | {text[:50]}")

    # ── 비용 요약 ──
    _banner("비용 요약")
    summary = router.cost_summary()
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    total = summary["total_requests"]
    local = summary["local_requests"]
    cloud = summary["cloud_requests"]
    print(f"\n  총 {total}건: 로컬 {local}건 ({local/total*100:.0f}%), "
          f"클라우드 {cloud}건 ({cloud/total*100:.0f}%)")
    print(f"  클라우드 비용: ${summary['cloud_cost_usd']:.4f}")
    print(f"  로컬 비용: ${summary['local_cost_usd']:.4f} (인프라 비용 별도)")

    # ── 시나리오 4: 폴백 동작 (감지 오류 시) ──
    _banner("시나리오 4: Fail-closed 동작")
    print("  감지 파이프라인 오류 발생 시 → 로컬로 안전 폴백 (fail-closed)")
    # 정상 동작 확인만 (실제 오류 주입은 테스트에서)
    decision = router.route("정상 텍스트 — 오류 없음")
    print(f"  정상 시: {decision.target_model} (reason={decision.reason})")

    print(f"\n{'='*60}")
    print("  ✅ PII 기반 하이브리드 라우팅 데모 완료")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
