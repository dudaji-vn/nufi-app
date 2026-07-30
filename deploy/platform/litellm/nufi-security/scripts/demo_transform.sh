#!/usr/bin/env bash
# =============================================================================
# demo_transform.sh — nufi-egress mask/redact/explain 데모 래퍼 (patch125)
#
# 텍스트 변환 기능 5 시나리오:
#   1. mask — PII를 asterisk(*)로 마스킹
#   2. redact — PII를 타입 태그([TYPE])로 교체
#   3. explain — PII 상세 설명(risk/action/routing)
#   4. mask + injection — 인젝션은 마스킹 안 됨(PII만 마스킹)
#   5. redact clean 텍스트 → 변환 없이 원문 그대로
#
# 사용:  ./scripts/demo_transform.sh
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."

export EGRESS_NER_BACKEND=gazetteer

exec python3 scripts/demo_transform.py
