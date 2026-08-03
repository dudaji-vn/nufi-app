#!/usr/bin/env bash
# =============================================================================
# CLI Showcase Demo -- 주요 CLI 커맨드 5가지를 빠르게 검증 (patch148)
#
# 시나리오:
#   1. playground --text (비인터랙티브 inspect)
#   2. summary --json (프로젝트 대시보드)
#   3. pipeline --text --json (체인 파이프라인)
#   4. mask --text (PII 마스킹)
#   5. redact --text (PII 리댁션)
#
# root 불필요 · 외부 네트워크 호출 0
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."

export EGRESS_NER_BACKEND=gazetteer

echo "=== CLI Showcase Demo (patch148) ==="
echo

python3 scripts/demo_cli_showcase.py
exit $?
