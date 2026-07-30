#!/usr/bin/env bash
# =============================================================================
# 프롬프트 인젝션 탐지 데모 (셸 래퍼)
#
# demo_prompt_injection.py 를 실행하고 PASS/FAIL 을 판정한다.
# demo_all.sh 러너에서 일관된 호출을 위한 래퍼.
#
# 사용:   ./scripts/demo_prompt_injection.sh
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."

python3 scripts/demo_prompt_injection.py
