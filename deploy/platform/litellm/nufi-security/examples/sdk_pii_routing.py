#!/usr/bin/env python3
"""NuFi SDK — PII 기반 라우팅 결정 예시.

PII 감지 결과에 따라 로컬/클라우드 모델 라우팅을 한 줄로 결정한다.

실행:
    EGRESS_NER_BACKEND=gazetteer python3 examples/sdk_pii_routing.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nufi import route, RoutingDecision  # noqa: E402

# ──────────────────────────────────────────────────────────────────────────────
# 1. PII 포함 텍스트 → 로컬 모델로 라우팅
# ──────────────────────────────────────────────────────────────────────────────
pii_text = "고객 홍길동님 주민번호 900101-1234568 확인 부탁드립니다."
decision: RoutingDecision = route(pii_text)

print("=== PII 포함 텍스트 ===")
print(f"  입력: {pii_text}")
print(f"  PII 감지: {decision.pii_detected}")
print(f"  라우팅 대상: {decision.target_model}")
print(f"  사유: {decision.reason}")
print(f"  로컬 라우팅: {decision.routed_to_local}")
print(f"  감지 엔티티: {[f.entity_type for f in decision.findings]}")
print()

assert decision.pii_detected, "PII 가 감지되어야 합니다"
assert decision.routed_to_local, "로컬로 라우팅되어야 합니다"

# ──────────────────────────────────────────────────────────────────────────────
# 2. PII 없는 텍스트 → 클라우드 모델 허용
# ──────────────────────────────────────────────────────────────────────────────
clean_text = "오늘 날씨가 좋습니다. 회의는 3시에 시작합니다."
decision_clean = route(clean_text)

print("=== PII 없는 텍스트 ===")
print(f"  입력: {clean_text}")
print(f"  PII 감지: {decision_clean.pii_detected}")
print(f"  라우팅 대상: {decision_clean.target_model}")
print(f"  사유: {decision_clean.reason}")
print(f"  로컬 라우팅: {decision_clean.routed_to_local}")
print()

assert not decision_clean.pii_detected, "PII 가 없어야 합니다"
assert not decision_clean.routed_to_local, "클라우드로 라우팅되어야 합니다"

# ──────────────────────────────────────────────────────────────────────────────
# 3. to_dict() — JSON 직렬화 가능한 요약
# ──────────────────────────────────────────────────────────────────────────────
print("=== to_dict() 출력 ===")
import json

print(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2))

print("\n✅ PII 라우팅 예시 완료")
