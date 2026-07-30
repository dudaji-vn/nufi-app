#!/usr/bin/env bash
# =============================================================================
# demo_scan.sh — nufi-egress scan 데모 래퍼 (patch89)
#
# 파일/디렉터리 PII 스캔 기능 4 시나리오:
#   1. 기본 PII 스캔 → 발견 검증
#   2. --fail-on-pii → CI 게이트(exit 1)
#   3. --redact --dry-run → 치환 보고(미수정)
#   4. --format sarif → 유효 SARIF JSON
#
# 사용:  ./scripts/demo_scan.sh
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."

export EGRESS_NER_BACKEND=gazetteer

exec python3 scripts/demo_scan.py
