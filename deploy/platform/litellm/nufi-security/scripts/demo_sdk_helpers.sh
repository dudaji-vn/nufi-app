#!/usr/bin/env bash
# demo_sdk_helpers.sh — SDK 편의 함수 데모 (v0.4.6)
#
# 시나리오:
#   1. scan_file — 파일에서 PII 탐지
#   2. guard_file — 파일 정책 평가 (차단/허용)
#   3. batch_detect — 여러 텍스트 일괄 탐지
#
# 실행: ./scripts/demo_sdk_helpers.sh
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

echo "=== SDK 편의 함수 데모 (v0.4.6) ==="

TMP=$(mktemp /tmp/nufi_demo_XXXXXX.txt)
trap "rm -f $TMP" EXIT

# 1. scan_file
echo ""
echo "--- 1. scan_file ---"
echo "김민수님 주민번호 900101-1234568 계좌 110-123-456789" > "$TMP"
run "scan_file PII 탐지" python3 -c "
import sys; sys.path.insert(0, '.')
from nufi import scan_file
findings = scan_file('$TMP')
types = {f.entity_type for f in findings}
assert 'KR_RRN' in types, f'KR_RRN not found in {types}'
assert 'KR_ACCOUNT' in types, f'KR_ACCOUNT not found in {types}'
"

echo "안녕하세요 오늘 날씨가 좋습니다" > "$TMP"
run "scan_file 무해 텍스트 0건" python3 -c "
import sys; sys.path.insert(0, '.')
from nufi import scan_file
assert len(scan_file('$TMP')) == 0
"

# 2. guard_file
echo ""
echo "--- 2. guard_file ---"
echo "주민번호 900101-1234568" > "$TMP"
run "guard_file 차단" python3 -c "
import sys; sys.path.insert(0, '.')
from nufi import guard_file
assert guard_file('$TMP').blocked
"

echo "안녕하세요" > "$TMP"
run "guard_file 허용" python3 -c "
import sys; sys.path.insert(0, '.')
from nufi import guard_file
assert not guard_file('$TMP').blocked
"

# 3. batch_detect
echo ""
echo "--- 3. batch_detect ---"
run "batch_detect 일괄 탐지" python3 -c "
import sys; sys.path.insert(0, '.')
from nufi import batch_detect
results = batch_detect(['주민번호 900101-1234568', '안녕', '계좌 110-123-456789'])
assert len(results) == 3
assert len(results[0]) > 0
assert len(results[1]) == 0
assert len(results[2]) > 0
"

echo ""
echo "==============================="
echo "결과: $PASS PASS / $FAIL FAIL"
[ "$FAIL" -eq 0 ] || exit 1
