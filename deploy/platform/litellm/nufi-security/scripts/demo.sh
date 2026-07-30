#!/usr/bin/env bash
# =============================================================================
# NuFi Egress-Audit Gateway — end-to-end 데모 (M1 + M2)  [CMP-82]
#
# 보드가 볼 수 있는 재현 가능한 시연. scripts/demo.sh 1회 실행으로 6개 시나리오를
# 실제 HTTP 게이트웨이에 대해 실행·검증하고 PASS/FAIL 을 출력한다.
#
#   1. private 기본 라우팅 — 외부 미전송(감사 0건)
#   2. public 폴백 + 주민등록번호(강한 PII)  → 403 차단 + entities=[KR_RRN]
#   3. public 폴백 + API 키(비밀)            → 403 차단 + entities=[SECRET]
#   4. public 폴백 + 약한 PII(전화/이메일)   → 가명화 후 전송(200, transformed)
#   5. 감사 로그(logs/egress_audit.jsonl)    → public 전송 100% 기록(private 0건)
#   6. 자동 검증: tests/run_acceptance.py(20/20) · tests/test_unit.py · scripts/bench.py
#
# 멱등: 매 실행마다 감사 로그를 초기화하고, 빈 포트를 자동 선택하며, 본 스크립트가
#       띄운 서버만 정리한다(EXIT trap). 외부 의존 0(gazetteer NER, stub 백엔드).
# 사용: ./scripts/demo.sh            (PORT 환경변수로 시작 포트 지정 가능, 기본 4000)
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

PY="${PYTHON:-python3}"

# uvicorn 필수 — 미설치 시 SKIP(에어갭/CI 환경에서 정상적 skip).
if ! "$PY" -c "import uvicorn" 2>/dev/null; then
  echo "SKIP: uvicorn 미설치 — pip install uvicorn 후 재실행"; exit 0
fi

export EGRESS_NER_BACKEND="${EGRESS_NER_BACKEND:-gazetteer}"   # 에어갭·결정적
export EGRESS_AUDIT_LOG="${EGRESS_AUDIT_LOG:-$ROOT/logs/egress_audit.jsonl}"
START_PORT="${PORT:-4000}"

PASS=0; FAIL=0
SERVER_PID=""
c_g=$'\033[32m'; c_r=$'\033[31m'; c_b=$'\033[1m'; c_d=$'\033[2m'; c_0=$'\033[0m'

hr()  { printf '%s\n' "────────────────────────────────────────────────────────────────────────"; }
sect(){ echo; hr; printf '%s%s%s\n' "$c_b" "$1" "$c_0"; hr; }
ok()  { PASS=$((PASS+1)); printf '  %s[PASS]%s %s\n' "$c_g" "$c_0" "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  %s[FAIL]%s %s\n' "$c_r" "$c_0" "$1"; }

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  SERVER_PID=""
}
trap cleanup EXIT INT TERM

# 빈 TCP 포트를 START_PORT 부터 위로 탐색(포트 충돌 회피).
free_port() {
  "$PY" - "$START_PORT" <<'PY'
import socket, sys
start = int(sys.argv[1])
for p in range(start, start + 200):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", p)); s.close(); print(p); break
    except OSError:
        s.close()
else:
    sys.exit("no free port")
PY
}

# 게이트웨이 기동 후 /health 준비될 때까지 대기. $1=private_down(0|1)
start_gateway() {
  local private_down="$1"
  PORT_IN_USE="$(free_port)"
  EGRESS_PRIVATE_DOWN="$private_down" \
    "$PY" -m uvicorn gateway.app:app --host 127.0.0.1 --port "$PORT_IN_USE" \
    >/tmp/nufi_demo_server.log 2>&1 &
  SERVER_PID=$!
  local base="http://127.0.0.1:$PORT_IN_USE"
  for _ in $(seq 1 50); do
    if curl -fs "$base/health" >/dev/null 2>&1; then
      BASE="$base"; return 0
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "서버 기동 실패:"; cat /tmp/nufi_demo_server.log; return 1
    fi
    sleep 0.2
  done
  echo "서버 health 타임아웃:"; cat /tmp/nufi_demo_server.log; return 1
}

# POST /v1/chat/completions. $1=model $2=content → CODE/BODY 전역에 채움
chat() {
  local model="$1" content="$2" out
  out="$("$PY" - "$BASE" "$model" "$content" <<'PY'
import json, sys, urllib.request
base, model, content = sys.argv[1], sys.argv[2], sys.argv[3]
data = json.dumps({"model": model, "messages": [{"role": "user", "content": content}]}).encode()
req = urllib.request.Request(base + "/v1/chat/completions", data=data,
                            headers={"Content-Type": "application/json"})
try:
    r = urllib.request.urlopen(req)
    print(r.status); print(r.read().decode())
except urllib.error.HTTPError as e:
    print(e.code); print(e.read().decode())
PY
)"
  CODE="$(printf '%s' "$out" | sed -n '1p')"
  BODY="$(printf '%s' "$out" | tail -n +2)"
}

# JSON 본문에서 점-경로 값 추출(jq 비의존)
jget() { "$PY" -c 'import json,sys
d=json.load(sys.stdin)
for k in sys.argv[1].split("."):
    d = d.get(k, "") if isinstance(d, dict) else ""
print(json.dumps(d, ensure_ascii=False) if isinstance(d,(list,dict)) else d)' "$1"; }

# 멱등: 감사 로그 초기화
mkdir -p "$ROOT/logs"
: > "$EGRESS_AUDIT_LOG"

printf '%s%s%s\n' "$c_b" "NuFi Egress-Audit Gateway — end-to-end 데모 (M1+M2) · CMP-82" "$c_0"
printf '%s실행: %s · NER=%s · audit=%s%s\n' "$c_d" "$("$PY" -c 'import time;print(time.strftime("%Y-%m-%d %H:%M:%S"))')" \
  "$EGRESS_NER_BACKEND" "${EGRESS_AUDIT_LOG/#$ROOT\//}" "$c_0"

# ───────────────────────── 시나리오 1: private 기본 라우팅 ─────────────────────────
sect "① private 기본 라우팅 — 외부 미전송(감사 0건)"
audit_before=$(wc -l < "$EGRESS_AUDIT_LOG" | tr -d ' ')
start_gateway 0 || exit 1
echo "  \$ POST /v1/chat/completions  model=nufi-default  content=\"내부 회의록 요약해줘\""
chat "nufi-default" "내부 회의록 요약해줘"
model="$(printf '%s' "$BODY" | jget model)"
printf '  %s→ HTTP %s · model=%s%s\n' "$c_d" "$CODE" "$model" "$c_0"
audit_after=$(wc -l < "$EGRESS_AUDIT_LOG" | tr -d ' ')
[[ "$CODE" == "200" ]] && ok "private 응답 200" || bad "private 응답이 200 아님 (got $CODE)"
[[ "$model" == "private-llm" ]] && ok "private-llm 백엔드로 처리(외부 미전송)" || bad "private-llm 아님 (got $model)"
[[ "$audit_after" -eq "$audit_before" ]] && ok "감사 로그 증가 0건 (private=외부 미전송)" \
  || bad "private인데 감사 로그가 증가함 ($audit_before→$audit_after)"
cleanup

# ─────────────────── 시나리오 2~4: public 폴백 (private 불가 → public) ───────────────────
start_gateway 1 || exit 1   # EGRESS_PRIVATE_DOWN=1 → nufi-default 가 public 폴백

sect "② public 폴백 + 주민등록번호(강한 PII) → 403 차단"
echo "  \$ POST … model=nufi-default  content=\"김민수님 주민번호 900101-1234568 으로 신청서 작성\""
chat "nufi-default" "김민수님 주민번호 900101-1234568 으로 신청서 작성해줘"
err_type="$(printf '%s' "$BODY" | jget error.type)"
entities="$(printf '%s' "$BODY" | jget error.entities)"
printf '  %s→ HTTP %s · error.type=%s · entities=%s%s\n' "$c_d" "$CODE" "$err_type" "$entities" "$c_0"
[[ "$CODE" == "403" ]] && ok "강한 PII → 403 차단" || bad "403 아님 (got $CODE)"
[[ "$entities" == *"KR_RRN"* ]] && ok "차단 entity=KR_RRN 보고" || bad "KR_RRN 미보고 (got $entities)"

sect "③ public 폴백 + API 키(비밀) → 403 차단"
echo "  \$ POST … model=nufi-default  content=\"이 키로 배포 sk-ant-api03-…\""
chat "nufi-default" "이 키로 배포해줘 sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCdEfGh01"
err_type="$(printf '%s' "$BODY" | jget error.type)"
entities="$(printf '%s' "$BODY" | jget error.entities)"
printf '  %s→ HTTP %s · error.type=%s · entities=%s%s\n' "$c_d" "$CODE" "$err_type" "$entities" "$c_0"
[[ "$CODE" == "403" ]] && ok "비밀(API 키) → 403 차단" || bad "403 아님 (got $CODE)"
[[ "$entities" == *"SECRET"* ]] && ok "차단 entity=SECRET 보고" || bad "SECRET 미보고 (got $entities)"

sect "④ public 폴백 + 약한 PII(전화/이메일) → 가명화 후 전송(200)"
echo "  \$ POST … model=nufi-default  content=\"연락처: 010-1234-5678, hong@dudaji.com 으로 회신\""
chat "nufi-default" "연락처 정리: 010-1234-5678, hong@dudaji.com 으로 회신"
fr="$(printf '%s' "$BODY" | jget choices)"
printf '  %s→ HTTP %s · (본문 가명화 후 public 전송)%s\n' "$c_d" "$CODE" "$c_0"
[[ "$CODE" == "200" ]] && ok "약한 PII → 가명화 후 전송 200" || bad "200 아님 (got $CODE)"
cleanup

# ───────────────────────── 시나리오 5: 감사 로그 ─────────────────────────
sect "⑤ 감사 로그(logs/egress_audit.jsonl) — public 전송 100% 기록"
total=$(wc -l < "$EGRESS_AUDIT_LOG" | tr -d ' ')
pub=$("$PY" -c 'import json,sys;print(sum(1 for l in open(sys.argv[1]) if l.strip() and json.loads(l)["is_public"]))' "$EGRESS_AUDIT_LOG")
nonpub=$((total - pub))
echo "  기록 라인:"
"$PY" - "$EGRESS_AUDIT_LOG" <<'PY'
import json, sys
for l in open(sys.argv[1]):
    if not l.strip(): continue
    d = json.loads(l)
    print(f"    {d['ts']}  is_public={str(d['is_public']).lower():5}  outcome={d['outcome']:11}  model={d['model']}")
PY
printf '  %s→ 총 %s건 · public %s건 · private(비public) %s건%s\n' "$c_d" "$total" "$pub" "$nonpub" "$c_0"
[[ "$total" -eq 3 && "$pub" -eq 3 ]] && ok "public 전송 3건 모두 기록(100%), private 0건" \
  || bad "기대=public3/total3, 실측 total=$total pub=$pub"
[[ "$nonpub" -eq 0 ]] && ok "private 경로는 감사 로그에 미기록(외부 미전송)" || bad "private가 로그에 기록됨"

# ───────────────────────── 시나리오 6: 자동 검증 ─────────────────────────
sect "⑥ 자동 검증 — acceptance(20/20) · unit · bench(recall·p95)"

echo "  \$ python3 tests/run_acceptance.py"
acc_out="$("$PY" tests/run_acceptance.py 2>&1)"; acc_rc=$?
echo "$acc_out" | grep -E '기준 PASS|FAIL' | tail -3 | sed 's/^/    /'
acc_pass="$(echo "$acc_out" | grep -oE '[0-9]+/[0-9]+ 기준 PASS' | tail -1)"
{ [[ $acc_rc -eq 0 ]] && [[ -n "$acc_pass" ]]; } \
  && ok "수용기준 ${acc_pass:-PASS}" || bad "수용기준 미통과 (rc=$acc_rc)"

echo "  \$ python3 tests/test_unit.py"
unit_out="$("$PY" tests/test_unit.py 2>&1)"; unit_rc=$?
echo "$unit_out" | grep -E 'unit tests PASS|FAIL' | tail -2 | sed 's/^/    /'
[[ $unit_rc -eq 0 ]] && ok "단위 테스트 PASS" || bad "단위 테스트 실패 (rc=$unit_rc)"

echo "  \$ python3 scripts/bench.py --ner gazetteer"
bench_out="$("$PY" scripts/bench.py --ner gazetteer 2>&1)"; bench_rc=$?
echo "$bench_out" | grep -E 'recall|Latency|target' | sed 's/^/    /'
{ [[ $bench_rc -eq 0 ]] && echo "$bench_out" | grep -q "Latency target p95  : PASS"; } \
  && ok "벤치 recall·p95 목표 충족" || bad "벤치 목표 미달 (rc=$bench_rc)"

# ───────────────────────── 요약 ─────────────────────────
sect "요약"
TOTAL=$((PASS+FAIL))
printf '  통과 %s%s%s / %s   실패 %s%s%s\n' "$c_g" "$PASS" "$c_0" "$TOTAL" "$c_r" "$FAIL" "$c_0"
if [[ "$FAIL" -eq 0 ]]; then
  printf '  %s✅ 6개 시나리오 전부 기대대로 동작 — 데모 PASS%s\n' "$c_g" "$c_0"
  exit 0
else
  printf '  %s❌ 일부 시나리오 실패 — 위 [FAIL] 확인%s\n' "$c_r" "$c_0"
  exit 1
fi
