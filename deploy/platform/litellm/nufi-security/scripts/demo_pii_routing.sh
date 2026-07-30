#!/usr/bin/env bash
# =============================================================================
# PII 기반 하이브리드 LLM 라우팅 데모 (셸 래퍼)
#
# demo_pii_routing.py 를 실행하고 PASS/FAIL 을 판정한다.
# demo_all.sh 러너에서 일관된 호출을 위한 래퍼.
#
# 사용:   ./scripts/demo_pii_routing.sh
# 매뉴얼: docs/PII_ROUTING.md
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."

python3 scripts/demo_pii_routing.py
