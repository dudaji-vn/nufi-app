#!/usr/bin/env bash
# =============================================================================
# NuFi Python SDK 데모 — from nufi import ... 한 줄로 탐지·가명화·정책 평가
#
# SDK 파사드(nufi/)가 올바르게 동작하는지 4가지를 검증한다:
#   S1  임포트 + 버전 동기화  — import nufi; nufi.__version__ == VERSION
#   S2  탐지 (detect)        — 한국어 PII 탐지 결과 반환
#   S3  가명화               — pseudonymize / mask / redact 동작
#   S4  Guard (탐지+정책)    — Guard().inspect() 로 탐지+정책 한 번에
#
# root 불필요 · 외부 네트워크 호출 0 · 결정론적(모델 스택 불필요).
#
# 사용: ./scripts/demo_sdk.sh
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"

PASS=0; FAIL=0; TOTAL=4

ok()   { PASS=$((PASS+1)); echo "  ✅ PASS  $1"; }
fail() { FAIL=$((FAIL+1)); echo "  ❌ FAIL  $1: $2"; }

echo "=== NuFi Python SDK 데모 ==="
echo ""

# ── S1: 임포트 + 버전 ────────────────────────────────────────────────────
echo "--- S1: import nufi + __version__"
EXPECTED_VER=$(cat VERSION)
ACTUAL_VER=$($PY -c "import nufi; print(nufi.__version__)" 2>&1) || true
if [ "$ACTUAL_VER" = "$EXPECTED_VER" ]; then
    ok "nufi.__version__ == $EXPECTED_VER"
else
    fail "S1" "expected=$EXPECTED_VER actual=$ACTUAL_VER"
fi

# ── S2: detect ────────────────────────────────────────────────────────────
echo "--- S2: detect()"
S2=$($PY -c "
from nufi import detect
r = detect('김민수님 계좌번호 110-123-456789')
types = {f.entity_type for f in r}
assert len(r) > 0, 'no findings'
print('OK', ','.join(sorted(types)))
" 2>&1) || true
if echo "$S2" | grep -q "^OK"; then
    ok "detect → ${S2#OK }"
else
    fail "S2" "$S2"
fi

# ── S3: 가명화 ───────────────────────────────────────────────────────────
echo "--- S3: pseudonymize / mask / redact"
S3=$($PY -c "
from nufi import pseudonymize, mask, redact
t = pseudonymize('KR_PERSON', '홍길동')
assert '홍길동' not in t, 'pseudonymize failed'
m = mask('900101-1234567', keep_tail=4)
assert m.endswith('4567'), 'mask failed'
r = redact('KR_RRN')
assert 'REDACTED' in r, 'redact failed'
print('OK')
" 2>&1) || true
if [ "$S3" = "OK" ]; then
    ok "pseudonymize·mask·redact"
else
    fail "S3" "$S3"
fi

# ── S4: Guard ─────────────────────────────────────────────────────────────
echo "--- S4: Guard().inspect()"
S4=$($PY -c "
from nufi import Guard
g = Guard()
r = g.inspect('김민수님 계좌번호 110-123-456789')
assert len(r.findings) > 0, 'no findings'
r2 = g.inspect('오늘 회의 시간 변경되었습니다.')
assert r2.blocked is False, 'benign should pass'
print('OK')
" 2>&1) || true
if [ "$S4" = "OK" ]; then
    ok "Guard.inspect — PII 탐지 + benign 통과"
else
    fail "S4" "$S4"
fi

# ── 집계 ──────────────────────────────────────────────────────────────────
echo ""
echo "=== 결과: $PASS/$TOTAL PASS, $FAIL FAIL ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
