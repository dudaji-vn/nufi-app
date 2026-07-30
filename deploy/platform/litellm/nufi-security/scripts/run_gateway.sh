#!/usr/bin/env bash
# standalone Egress-Audit 게이트웨이 기동 (PoC).
#   PORT             기본 4000
#   EGRESS_PRIVATE_DOWN=1  private 백엔드 불가 → public 폴백 강제(데모)
#   EGRESS_NER_BACKEND     gazetteer(기본) | transformers | auto
#   EGRESS_AUDIT_LOG       감사 로그 경로 (기본 logs/egress_audit.jsonl)
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-4000}"
exec python3 -m uvicorn gateway.app:app --host 0.0.0.0 --port "$PORT"
