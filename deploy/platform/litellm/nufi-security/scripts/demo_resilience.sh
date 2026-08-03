#!/usr/bin/env bash
# demo_resilience.sh — 게이트웨이 강건성 데모 (v0.4.2)
#
# 시나리오:
#   1. 지연 추적 — 게이트웨이 응답에 latency_ms 포함 확인
#   2. 방어 파싱 — 비정상 메시지(None content, 비-dict) 안전 처리
#   3. 탐지 타임아웃 → fail-closed 차단
#
# 실행: ./scripts/demo_resilience.sh
# 사전조건: python3, requirements.txt 설치. root 불필요, 외부 네트워크 0.

set -euo pipefail
cd "$(dirname "$0")/.."

PASS=0 FAIL=0

run() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  [PASS] $label"; PASS=$(( PASS + 1 ))
  else
    echo "  [FAIL] $label"; FAIL=$(( FAIL + 1 ))
  fi
}

echo "=== 게이트웨이 강건성 데모 (v0.4.2) ==="

# 1. latency_ms 포함
echo ""
echo "--- 1. 지연 추적(latency_ms) ---"
run "latency_ms 포함 확인" python3 -c "
import os, sys, tempfile
sys.path.insert(0, '.')
os.environ['EGRESS_NER_BACKEND'] = 'gazetteer'
from gateway.core import Gateway
from egress_audit import AuditLogger
with tempfile.TemporaryDirectory() as tmp:
    gw = Gateway(audit=AuditLogger(path=os.path.join(tmp, 'a.jsonl')), ner_backend='gazetteer')
    r = gw.process({'model':'nufi-default','messages':[{'role':'user','content':'hello'}]})
    assert r.latency_ms is not None and r.latency_ms >= 0, f'latency_ms={r.latency_ms}'
"

# 2. 방어 파싱
echo ""
echo "--- 2. 방어 파싱 ---"
run "content=None 안전 처리" python3 -c "
import sys; sys.path.insert(0, '.')
from gateway.core import extract_text
assert extract_text([{'role':'user','content':None}]) == ''
"

run "비-dict 메시지 건너뜀" python3 -c "
import sys; sys.path.insert(0, '.')
from gateway.core import extract_text
assert 'hello' in extract_text(['bad', {'role':'user','content':'hello'}])
"

run "큰 프롬프트 잘림" python3 -c "
import sys; sys.path.insert(0, '.')
from gateway.core import extract_text, _MAX_PROMPT_BYTES
huge = 'A' * (_MAX_PROMPT_BYTES + 1000)
result = extract_text([{'role':'user','content':huge}])
assert len(result) < len(huge), 'not truncated'
"

# 3. 탐지 타임아웃 → fail-closed
echo ""
echo "--- 3. 탐지 타임아웃 → fail-closed ---"
run "타임아웃 시 403 차단" python3 -c "
import os, sys, tempfile
sys.path.insert(0, '.')
os.environ['EGRESS_NER_BACKEND'] = 'gazetteer'
os.environ['EGRESS_PRIVATE_DOWN'] = '1'
from unittest.mock import patch
from gateway.core import Gateway, DetectionTimeoutError
from egress_audit import AuditLogger
with tempfile.TemporaryDirectory() as tmp:
    gw = Gateway(audit=AuditLogger(path=os.path.join(tmp, 'a.jsonl')), ner_backend='gazetteer')
    with patch.object(gw, '_inspect_with_timeout', side_effect=DetectionTimeoutError('test')):
        r = gw.process({'model':'nufi-default','messages':[{'role':'user','content':'test'}]})
    assert r.status == 403, f'status={r.status}'
    assert 'FAIL_CLOSED' in r.blocked_entities
os.environ.pop('EGRESS_PRIVATE_DOWN', None)
"

echo ""
echo "==============================="
echo "결과: $PASS PASS / $FAIL FAIL"
[ "$FAIL" -eq 0 ] || exit 1
