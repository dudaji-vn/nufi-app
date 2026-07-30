#!/usr/bin/env bash
# =============================================================================
# NuFi 차등 감사 데모 — public/private 분리 저장 + 패킷 우회 탭 + 비동기 감사봇
#
# public/private 분리 저장(P0) + 패킷 레이어 캡처·게이트웨이 우회 탭(P1) +
# 비동기 감사 봇(P2, producer/consumer)을 한 번에 띄워 6개 시나리오를 실행·
# 자동검증하고 PASS/FAIL 을 출력한다.
#
#   S1  private 질의      → private 싱크에만 분리 저장(외부 미전송, public dump 0)
#   S2  public 약한 PII   → 인라인 즉시 통과(가명화·무지연) + 봇이 준실시간 finding
#   S3  public 강한 PII   → 인라인 fast hard-block(403) + 봇이 차단 내용 상관(finding/alert)
#   S4  게이트웨이 우회   → flow tap 이 패킷 레이어에서 탐지 → 봇 high-sev 우회 알림  [헤드라인]
#   S5  무지연·준실시간   → 사용자 경로 지연(인라인만) + producer→finding p95 ≤ 5s 증명
#   S6  자동 검증         → 위 전부 PASS/FAIL 집계(멱등)
#
# 멱등: 매 실행마다 격리 워크스페이스를 초기화하고, 빈 포트를 자동 선택하며,
#       본 스크립트가 띄운 게이트웨이/봇만 정리한다(EXIT trap).
# --simulate(기본): root 없이(에어갭/CI) flow tap 을 미리 만든 flow 로그로 리플레이.
#                   외부 네트워크 호출 0(gazetteer NER + stub 백엔드, NFR1).
# --enforce: S4 차단을 mode=ENFORCED 로 승격 — 격리 netns 에서 실제 egress drop
#            (scripts/demo_bypass_enforcement.sh). **root/nft 필요**. 없으면
#            정직하게 SIMULATED 로 폴백(기본 경로 보존). 기본(미지정)=SIMULATED.
# 사용: ./scripts/demo_audit_separation.sh            (PORT 로 시작 포트 지정 가능, 기본 4500)
#       sudo ./scripts/demo_audit_separation.sh --enforce   (S4 실제 drop 시연; root 필요)
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

PY="${PYTHON:-python3}"
START_PORT="${PORT:-4500}"
SIMULATE=1                      # 기본 simulate(에어갭/CI). --live 는 root 필요(범위 밖).
ENFORCE=0                       # 기본 SIMULATED(root 불요). --enforce 는 격리 netns 실제 drop.
REPLAY="$ROOT/samples/flow_replay.jsonl"
for arg in "$@"; do
  case "$arg" in
    --simulate) SIMULATE=1 ;;
    --live)     SIMULATE=0 ;;
    --enforce)  ENFORCE=1 ;;
    *) echo "알 수 없는 인자: $arg (사용: --simulate|--live|--enforce)"; exit 2 ;;
  esac
done

# 격리 워크스페이스(멱등): 매 실행 초기화. 모든 산출물이 여기에만 쌓인다.
WS="$ROOT/logs/demo_audit_separation"
rm -rf "$WS"
mkdir -p "$WS/messages" "$WS/packets" "$WS/audit_state"

# uvicorn 필수 — 미설치 시 SKIP(에어갭/CI 환경에서 정상적 skip).
if ! "$PY" -c "import uvicorn" 2>/dev/null; then
  echo "SKIP: uvicorn 미설치 — pip install uvicorn 후 재실행"; exit 0
fi

export EGRESS_NER_BACKEND="gazetteer"            # 에어갭·결정적(NFR1)
export EGRESS_AUDIT_PROFILES="$WS/profiles.yaml"  # 봇·스토어 공용 프로파일(NFR3)
export EGRESS_MESSAGE_STORE_DIR="$WS/messages"    # 게이트웨이 메시지 스토어
export EGRESS_PACKET_DIR="$WS/packets"            # content dump + flow tap 출력
export EGRESS_AUDIT_LOG="$WS/egress_audit.jsonl"  # 인라인 감사 로그(M1/M2)

# 데모 감사 프로파일(NFR3 외부화). 핵심:
#  - public.retain_raw=true → 감사 스토어가 egress 원문을 보존하여 비동기 봇이
#    실제 나간 내용을 재검사한다(감사 보존 모드; 운영 시 접근제어·보존기간은
#    SPEC §P0/README 의 컴플라이언스 게이트를 따른다).
#  - 차등 프로파일: private=경량(secrets+strong_pii, 임계 high) / public=풀.
cat > "$WS/profiles.yaml" <<YAML
version: 1
message_store:
  base_dir: $WS/messages
  rotation: daily
profiles:
  private:
    retain_raw: true
  public:
    retain_raw: true        # 감사 보존 모드(봇이 원문 재검사). 운영=컴플라이언스 게이트.
detection:
  private:
    detectors: [secrets, strong_pii]
    sampling_rate: 1.0
    severity_threshold: high
  public:
    detectors: [secrets, strong_pii, weak_pii, confidential_keywords, bypass_correlation]
    sampling_rate: 1.0
    severity_threshold: low
confidential_keywords: [대외비, 기밀, 사내한, 영업비밀, confidential]
audit_bot:
  poll_interval_sec: 0.25
  workers: 4
  findings_path: $WS/audit_findings.jsonl
  alerts_path: $WS/alerts.jsonl
  state_path: $WS/audit_state/offsets.json
  flow_dir: $WS/packets/public
  gateway_identity:
    hosts: [127.0.0.1, "::1", localhost]
    ips: [127.0.0.1, "::1"]
    process_names: [litellm, gateway, uvicorn]
YAML

c_g=$'\033[32m'; c_r=$'\033[31m'; c_y=$'\033[33m'; c_b=$'\033[1m'; c_d=$'\033[2m'; c_0=$'\033[0m'
hr()  { printf '%s\n' "────────────────────────────────────────────────────────────────────────"; }
sect(){ echo; hr; printf '%s%s%s\n' "$c_b" "$1" "$c_0"; hr; }

SERVER_PID=""; BOT_PID=""
cleanup() {
  [[ -n "$BOT_PID"    ]] && kill "$BOT_PID"    2>/dev/null && wait "$BOT_PID"    2>/dev/null
  [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null && wait "$SERVER_PID" 2>/dev/null
  SERVER_PID=""; BOT_PID=""
}
trap cleanup EXIT INT TERM

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

# 게이트웨이 기동(빈 포트) 후 /health 대기. $1=private_down(0|1)
start_gateway() {
  local private_down="$1"
  PORT_IN_USE="$(free_port)"
  EGRESS_PRIVATE_DOWN="$private_down" \
    "$PY" -m uvicorn gateway.app:app --host 127.0.0.1 --port "$PORT_IN_USE" \
    >"$WS/server.log" 2>&1 &
  SERVER_PID=$!
  local base="http://127.0.0.1:$PORT_IN_USE"
  for _ in $(seq 1 50); do
    if curl -fs "$base/health" >/dev/null 2>&1; then BASE="$base"; return 0; fi
    kill -0 "$SERVER_PID" 2>/dev/null || { echo "서버 기동 실패:"; cat "$WS/server.log"; return 1; }
    sleep 0.2
  done
  echo "서버 health 타임아웃:"; cat "$WS/server.log"; return 1
}

# POST /v1/chat/completions + 사용자 경로 지연 측정 → $WS/user_latency.jsonl 적재.
# $1=scenario $2=model $3=conversation_id $4=content → CODE/BODY 전역 채움
chat() {
  local scen="$1" model="$2" conv="$3" content="$4" out
  out="$("$PY" - "$BASE" "$model" "$conv" "$content" "$scen" "$WS/user_latency.jsonl" <<'PY'
import json, sys, time, urllib.request, urllib.error
base, model, conv, content, scen, latpath = sys.argv[1:7]
data = json.dumps({"model": model, "conversation_id": conv,
                   "messages": [{"role": "user", "content": content}]}).encode()
req = urllib.request.Request(base + "/v1/chat/completions", data=data,
                             headers={"Content-Type": "application/json"})
t0 = time.perf_counter()
try:
    r = urllib.request.urlopen(req); code = r.status; body = r.read().decode()
except urllib.error.HTTPError as e:
    code = e.code; body = e.read().decode()
elapsed_ms = (time.perf_counter() - t0) * 1000.0
with open(latpath, "a", encoding="utf-8") as f:
    f.write(json.dumps({"scenario": scen, "conversation_id": conv, "status": code,
                        "elapsed_ms": round(elapsed_ms, 2)}, ensure_ascii=False) + "\n")
print(code); print(body)
PY
)"
  CODE="$(printf '%s' "$out" | sed -n '1p')"
  BODY="$(printf '%s' "$out" | tail -n +2)"
}

jget() { "$PY" -c 'import json,sys
d=json.load(sys.stdin)
for k in sys.argv[1].split("."):
    d = d.get(k, "") if isinstance(d, dict) else ""
print(json.dumps(d, ensure_ascii=False) if isinstance(d,(list,dict)) else d)' "$1"; }

# 파이프라인 라우팅 결정 로그(관측성만 — 라우팅 로직 변경 0, CMP-92 §P3).
# 사용자는 nufi-default 단일 엔드포인트만 호출하고, 파이프라인이 private/public 결정.
# $1=scenario $2=route $3=reason $4=backend
plog() {
  printf '  %spipeline: route=%s reason=%s backend=%s%s\n' "$c_d" "$2" "$3" "$4" "$c_0"
  "$PY" - "$WS/pipeline_decisions.jsonl" "$1" "$2" "$3" "$4" <<'PY'
import json, sys
path, scen, route, reason, backend = sys.argv[1:6]
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps({"scenario": scen, "route": route, "reason": reason,
                        "backend": backend}, ensure_ascii=False) + "\n")
PY
}

printf '%s%s%s\n' "$c_b" "NuFi 차등 감사 데모 (CMP-85 P0~P2 통합) · CMP-89" "$c_0"
printf '%s실행: %s · NER=%s · mode=%s · enforce=%s · ws=%s%s\n' "$c_d" \
  "$("$PY" -c 'import time;print(time.strftime("%Y-%m-%d %H:%M:%S"))')" \
  "$EGRESS_NER_BACKEND" "$([[ $SIMULATE -eq 1 ]] && echo simulate || echo live)" \
  "$([[ $ENFORCE -eq 1 ]] && echo on || echo off)" \
  "${WS/#$ROOT\//}" "$c_0"

# ── 비동기 감사 봇(consumer)을 데몬으로 먼저 기동 → producer 와 동시 동작(준실시간) ──
"$PY" -m egress_audit.audit_bot --profiles "$WS/profiles.yaml" --daemon \
  >"$WS/bot.log" 2>&1 &
BOT_PID=$!
printf '%s감사 봇 데몬 기동(pid=%s, poll=0.25s) — 사용자 경로와 분리되어 백그라운드 감사%s\n' \
  "$c_d" "$BOT_PID" "$c_0"

# ───────────────────────── S1: private 라우팅(파이프라인 결정) ─────────────────────────
sect "S1 — 사용자가 LLM 호출 → 파이프라인이 private 라우팅 결정 → private 분리 저장"
start_gateway 0 || exit 1
echo "  \$ POST /v1/chat/completions  model=nufi-default  conv=s1  \"내부 회의록 요약해줘\"  (사용자는 백엔드 미지정)"
chat "S1" "nufi-default" "s1" "내부 회의록 요약해줘"
plog "S1" "private" "primary(기본 private 우선)" "private-llm"
printf '  %s→ HTTP %s · 파이프라인 취합·반환 model=%s (외부 미전송)%s\n' "$c_d" "$CODE" "$(printf '%s' "$BODY" | jget model)" "$c_0"
cleanup_server() { [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null && wait "$SERVER_PID" 2>/dev/null; SERVER_PID=""; }
cleanup_server

# ─────────────── S2~S3: 파이프라인이 public failover 결정(운영상 private 용량 불가) ───────────────
start_gateway 1 || exit 1     # EGRESS_PRIVATE_DOWN=1 = 파이프라인의 운영상 failover 결정(사용자 선택 아님)

sect "S2 — 사용자가 LLM 호출 → 파이프라인 public failover + 약한 PII: 인라인 가명화(무지연) + 봇 준실시간 finding"
echo "  \$ POST … conv=s2  \"연락처 정리: 010-1234-5678, hong@dudaji.com 회신\"  (동일 단일 엔드포인트)"
chat "S2" "nufi-default" "s2" "연락처 정리: 010-1234-5678, hong@dudaji.com 으로 회신"
plog "S2" "public" "failover(파이프라인 운영상 결정: private 용량 불가)" "claude-3-5-sonnet"
printf '  %s→ HTTP %s · outcome=가명화후 전송(사용자 지연=인라인만)%s\n' "$c_d" "$CODE" "$c_0"

sect "S3 — 사용자가 LLM 호출 → 파이프라인 public failover + 강한 PII: 인라인 fast hard-block(403) + 봇 상관"
echo "  \$ POST … conv=s3  \"김민수 주민번호 900101-1234568 으로 신청서 작성\"  (동일 단일 엔드포인트)"
chat "S3" "nufi-default" "s3" "김민수님 주민번호 900101-1234568 으로 신청서 작성해줘"
plog "S3" "public" "failover(파이프라인 운영상 결정: private 용량 불가)" "claude-3-5-sonnet"
printf '  %s→ HTTP %s · error.entities=%s%s\n' "$c_d" "$CODE" \
  "$(printf '%s' "$BODY" | jget error.entities)" "$c_0"
cleanup_server

# ───────────────────────── S4: 파이프라인 우회 탐지 → 차단 결정(헤드라인) ─────────────────────────
sect "S4 — 파이프라인 우회 탐지 → high-sev 알림 → 차단 결정$([[ $ENFORCE -eq 1 ]] && echo '(ENFORCED 시도)' || echo '(SIMULATED)')  [헤드라인]"
export PYTHONWARNINGS="ignore::RuntimeWarning"   # runpy '-m' 임포트 경고 억제(무해)
if [[ $SIMULATE -eq 1 ]]; then
  echo "  \$ python3 -m capture.flow_tap --simulate samples/flow_replay.jsonl  (root 불필요)"
  "$PY" -m capture.flow_tap --simulate "$REPLAY" --out "$WS/packets" 2>&1 | sed 's/^/  /'
else
  echo "  \$ python3 -m capture.flow_tap --live  (root/CAP_NET_RAW 필요)"
  "$PY" -m capture.flow_tap --live --out "$WS/packets" 2>&1 | sed 's/^/  /' \
    || { echo "  ⚠ live 캡처 불가(권한). --simulate 로 폴백"; \
         "$PY" -m capture.flow_tap --simulate "$REPLAY" --out "$WS/packets" 2>&1 | sed 's/^/  /'; }
fi

# ── 준실시간 대기: 봇 데몬이 기대 finding/alert 전부를 낼 때까지 폴(최대 15s) ──
#    기대 우회 건수 = flow 로그의 bypass=true 개수(샘플 비의존, 동적 산정).
printf '%s봇 데몬이 producer 출력을 tail 하며 준실시간 감사 중…%s\n' "$c_d" "$c_0"
"$PY" - "$WS/audit_findings.jsonl" "$WS/alerts.jsonl" "$WS/packets/public" <<'PY'
import glob, json, sys, time
findings_p, alerts_p, flow_dir = sys.argv[1], sys.argv[2], sys.argv[3]
def load(p):
    try:
        return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    except FileNotFoundError:
        return []
def flows():
    out = []
    for fp in sorted(glob.glob(flow_dir + "/flow-*.jsonl")):
        out += load(fp)
    return out
want_bypass = sum(1 for f in flows() if f.get("bypass"))
deadline = time.time() + 15.0
while time.time() < deadline:
    f = load(findings_p); a = load(alerts_p)
    have_s2 = any(x.get("conversation_id") == "s2" and "weak_pii" in x.get("detectors", []) for x in f)
    have_s3 = any(x.get("conversation_id") == "s3" for x in a)
    have_bypass = sum(1 for x in f if x.get("kind") == "flow_bypass") >= max(1, want_bypass)
    if have_s2 and have_s3 and have_bypass:
        break
    time.sleep(0.2)
PY

# 봇 데몬 정지 후, 잔여분이 있으면 1회 드레인으로 결정적 완결(데몬 타이밍 비의존).
cleanup
"$PY" -m egress_audit.audit_bot --profiles "$WS/profiles.yaml" --once >>"$WS/bot.log" 2>&1

# ── S4 강화: 우회 high-sev 알림 → 차단 결정 ───────────────────────────────────
#   기본(SIMULATED): flow tap 은 관찰 전용이라 실제 drop 없음 → mode=SIMULATED 로 정직히.
#   --enforce(ENFORCED): CMP-94 트랙 B 빌드로 승격 — 격리 netns 에서 실제 egress drop
#     (scripts/demo_bypass_enforcement.sh). root/nft 필요. 없으면 정직하게 SIMULATED 로 폴백.
S4_MODE="SIMULATED"
if [[ $ENFORCE -eq 1 ]]; then
  if [[ "$(id -u)" == "0" ]] && command -v nft >/dev/null 2>&1; then
    printf '%s우회 알림 → ENFORCED 승격: 격리 netns 실제 egress drop(CMP-94 트랙 B):%s\n' "$c_d" "$c_0"
    # 공유 워크스페이스($WS)에 enforcement.jsonl(ENFORCED)·blocked_attempts.json·
    # s4_enforced.json 을 적재. 자체 PASS/FAIL 도 출력(증강 하니스).
    if S4_WS="$WS" bash "$ROOT/scripts/demo_bypass_enforcement.sh" 2>&1 | sed 's/^/  /'; then
      S4_MODE="ENFORCED"
    else
      printf '%s  ⚠ ENFORCED 증강 실패 — SIMULATED 결정으로 폴백.%s\n' "$c_y" "$c_0"
    fi
  else
    printf '%s  ⚠ --enforce 는 root/nft(격리 netns) 필요 — 이번 실행은 SIMULATED 로 폴백.%s\n' "$c_y" "$c_0"
    printf '%s    실제 drop 시연:  sudo PORT=%s ./scripts/demo_audit_separation.sh --enforce%s\n' "$c_d" "$START_PORT" "$c_0"
  fi
fi
if [[ "$S4_MODE" == "SIMULATED" ]]; then
  printf '%s우회 알림 → enforcement 결정(차단 제어점 스텁, mode=SIMULATED):%s\n' "$c_d" "$c_0"
  "$PY" -m egress_audit.enforcement --alerts "$WS/alerts.jsonl" \
    --out "$WS/enforcement.jsonl" --mode SIMULATED 2>&1 | sed 's/^/  /'
fi
export DEMO_S4_MODE="$S4_MODE"

# ───────────────────────── S5~S6: 무지연·준실시간 증명 + 자동 검증 ─────────────────────────
sect "S5~S6 — 무지연·준실시간 증명 + 6개 시나리오 자동 PASS/FAIL"
"$PY" - "$WS" "$ROOT" <<'PY'
import json, os, sys
from pathlib import Path
WS, ROOT = Path(sys.argv[1]), Path(sys.argv[2])
S4_MODE = os.environ.get("DEMO_S4_MODE", "SIMULATED")   # SIMULATED(기본) | ENFORCED(--enforce+root)

def load(p):
    p = Path(p)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

def read_class(cls):
    d = WS / "messages" / cls
    out = []
    if d.exists():
        for p in sorted(d.glob("*.jsonl")):
            out += [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return out

priv      = read_class("private")
pub       = read_class("public")
findings  = load(WS / "audit_findings.jsonl")
alerts    = load(WS / "alerts.jsonl")
lat       = load(WS / "user_latency.jsonl")
dumps     = []
ddir = WS / "packets" / "public"
if ddir.exists():
    for p in sorted(ddir.glob("dump-*.jsonl")):
        dumps += [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
flows = []
if ddir.exists():
    for p in sorted(ddir.glob("flow-*.jsonl")):
        flows += [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
pipe      = load(WS / "pipeline_decisions.jsonl")   # 파이프라인 라우팅 결정 로그
enforce   = load(WS / "enforcement.jsonl")          # 우회 차단 결정(SIMULATED|ENFORCED)
def load_json(p):                                    # 단일 JSON 객체(jsonl 아님)
    p = Path(p)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
s4enf     = load_json(WS / "s4_enforced.json")       # ENFORCED 증강 요약(netns 하니스)
blocked   = load_json(WS / "blocked_attempts.json")  # drop 피드백 카운터(A3)
def pipe_route(scen):
    r = [p for p in pipe if p.get("scenario") == scen]
    return r[0].get("route") if r else None

G, R, Y, B, D, Z = "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[2m", "\033[0m"
rows = []
def check(name, ok, detail=""):
    rows.append((name, ok))
    tag = f"{G}[PASS]{Z}" if ok else f"{R}[FAIL]{Z}"
    print(f"  {tag} {name}" + (f" {D}— {detail}{Z}" if detail else ""))

def p95(vals):
    if not vals:
        return None
    s = sorted(vals); i = max(0, int(round(0.95 * (len(s) - 1))))
    return s[i]

# helpers
def by_conv(recs, conv):
    return [r for r in recs if r.get("conversation_id") == conv]
f_s2 = [f for f in findings if f.get("conversation_id") == "s2"]
f_s3 = [f for f in findings if f.get("conversation_id") == "s3"]
a_s3 = [a for a in alerts if a.get("conversation_id") == "s3"]
bypass_f = [f for f in findings if f.get("kind") == "flow_bypass"]
bypass_a = [a for a in alerts if a.get("kind") == "flow_bypass"]

# ── S1: private 분리 저장 ──
s1_priv = by_conv(priv, "s1")
s1_dirs = {r["direction"] for r in s1_priv}
s1_ok = (
    len(s1_priv) >= 2 and s1_dirs == {"in", "out"}
    and all(r["egress_class"] == "private" for r in s1_priv)
    and not by_conv(pub, "s1")                      # public 싱크엔 s1 없음
    and not any(d.get("conversation_id") == "s1" for d in dumps)  # public dump 0
    and not any(f.get("conversation_id") == "s1" for f in findings)  # 봇 finding 0(경량)
    and pipe_route("S1") == "private"               # 파이프라인이 private 라우팅 결정
)
check("S1 사용자→단일 엔드포인트 · 파이프라인 private 라우팅 → private 싱크에만 in·out(외부 미전송, dump 0)",
      s1_ok, f"pipeline route={pipe_route('S1')}, private in·out={sorted(s1_dirs)}, "
             f"public(s1)={len(by_conv(pub,'s1'))}, dump(s1)=0, finding(s1)=0")

# ── S2: public 약한 PII 인라인 무지연 + 봇 준실시간 finding ──
s2_lat = [r for r in lat if r["scenario"] == "S2"]
s2_200 = bool(s2_lat) and all(r["status"] == 200 for r in s2_lat)
s2_finding = bool(f_s2) and any("weak_pii" in f.get("detectors", []) for f in f_s2)
s2_lat_ok = bool(f_s2) and all(f["latency_ms"] <= 5000 for f in f_s2)
s2_ok = s2_200 and s2_finding and s2_lat_ok and pipe_route("S2") == "public"
check("S2 파이프라인 public failover + 약한 PII → 인라인 200(가명화·무지연) + 봇 준실시간 weak_pii finding(≤5s)",
      s2_ok, f"pipeline route={pipe_route('S2')}, HTTP200={s2_200}, weak_pii finding={len(f_s2)}건, "
             f"finding 지연={[f['latency_ms'] for f in f_s2]}ms")

# ── S3: public 강한 PII 인라인 차단(403) + 봇 상관(finding/alert) ──
s3_lat = [r for r in lat if r["scenario"] == "S3"]
s3_403 = bool(s3_lat) and all(r["status"] == 403 for r in s3_lat)
s3_finding = bool(f_s3) and any("strong_pii" in f.get("detectors", []) for f in f_s3)
s3_alert = bool(a_s3) and any(a["severity"] in ("high", "critical") for a in a_s3)
s3_ok = s3_403 and s3_finding and s3_alert and pipe_route("S3") == "public"
check("S3 파이프라인 public failover + 강한 PII → 인라인 403 fast hard-block + 봇 strong_pii finding/alert 상관",
      s3_ok, f"pipeline route={pipe_route('S3')}, HTTP403={s3_403}, strong_pii finding={len(f_s3)}건, "
             f"high/critical alert={len(a_s3)}건")

# ── S4(헤드라인): 게이트웨이 우회 flow tap 탐지 → high-sev 알림 ──
captured_hosts = {f.get("dst_host") for f in flows}
non443 = [f for f in flows if f.get("dst_port") != 443]
flow_bypass = [f for f in flows if f.get("bypass")]
bypass_high = bool(bypass_f) and all(f["severity"] == "high" for f in bypass_f)
bypass_alerted = len(bypass_a) >= 1
src_not_gw = all(not f.get("via_gateway") for f in flow_bypass) and bool(flow_bypass)
# 차단 결정: 우회 알림 → action=BLOCK. 모드별로 정직하게 검증.
enf_block = [e for e in enforce if e.get("action") == "BLOCK"]
if S4_MODE == "ENFORCED":
    # ENFORCED(--enforce+root): 격리 netns 에서 실제 drop. 결정=ENFORCED·applied·rule_id +
    # blocked_attempts 증가 + A2 실제 drop·A1 정상 통과(scripts/demo_bypass_enforcement.sh 증강).
    enf_ok = (
        bool(enf_block)
        and all(e.get("mode") == "ENFORCED" for e in enf_block)    # 실제 집행 라벨
        and all(e.get("applied") is True for e in enf_block)       # 동적 set 보강 성공
        and all(e.get("rule_id") for e in enf_block)               # nft 규칙 식별자
        and bool(s4enf) and s4enf.get("a2_drop") is True           # 비-게이트웨이 직결 실제 drop
        and s4enf.get("a1_pass") is True                           # 게이트웨이 정상 통과(동시)
        and int(blocked.get("blocked_attempts", 0)) >= 1           # drop 피드백 카운터 증가(A3)
    )
    enf_detail = (f"mode=ENFORCED·applied, rule_id={(enf_block[0].get('rule_id') if enf_block else None)}, "
                  f"A2 drop={s4enf.get('a2_drop')}·A1 통과={s4enf.get('a1_pass')}, "
                  f"blocked_attempts={blocked.get('blocked_attempts', 0)}(실제 egress drop·CMP-94 트랙B)")
    enf_label = "차단 결정(action=BLOCK, mode=ENFORCED · 실제 drop)"
else:
    # SIMULATED(기본): flow tap 관찰 전용 → 결정만, 실제 drop 안 함, 제어점 명시.
    enf_ok = (
        len(enf_block) == len(bypass_a)               # 우회 알림 1건당 차단 결정 1건
        and bool(enf_block)
        and all(e.get("mode") == "SIMULATED" for e in enf_block)   # 정직한 라벨(실제 drop 아님)
        and all(e.get("applied") is False for e in enf_block)      # 관찰 전용 = 미적용
        and all(e.get("control_point") for e in enf_block)         # 차단 제어점 스텁 명시
    )
    enf_detail = (f"high alert={len(bypass_a)}, 차단결정={len(enf_block)}(SIMULATED·미적용). "
                  f"실제 drop=--enforce(CMP-95)/CMP-93(트랙B)")
    enf_label = "차단 결정(action=BLOCK, mode=SIMULATED)"
s4_ok = (
    len(flows) > 0 and len(non443) == 0           # public 443 목적지만 캡처
    and len(flow_bypass) >= 1 and src_not_gw      # 우회(src≠게이트웨이) 식별
    and bypass_high and bypass_alerted            # 봇이 high-sev finding + alert
    and enf_ok                                    # 탐지→차단 결정(모드별) 강화
)
check(f"S4 파이프라인 우회 → flow tap 탐지 → high-sev 알림 → {enf_label}  [헤드라인]",
      s4_ok, f"flow 캡처={len(flows)}(호스트={sorted(captured_hosts)}), 우회(src≠gw)={len(flow_bypass)}, "
             f"{enf_detail}")

# ── S5: 무지연(사용자 경로) + 준실시간(봇 지연 p95 ≤ 5s) 증명 ──
user_p95 = p95([r["elapsed_ms"] for r in lat]) if lat else None
finding_lat = [f["latency_ms"] for f in findings]
finding_p95 = p95(finding_lat) if finding_lat else None
# 디커플링(구조적 무지연): 사용자 경로(gateway/core)가 봇/큐를 참조하지 않음.
gw_src = (ROOT / "security" / "gateway" / "core.py")
gw_src = gw_src if gw_src.exists() else (ROOT / "gateway" / "core.py")
src = gw_src.read_text(encoding="utf-8")
decoupled = not any(k in src for k in ("audit_bot", "AuditBot", "file_queue", "FileQueue"))
s5_ok = (
    user_p95 is not None and decoupled
    and finding_p95 is not None and finding_p95 <= 5000
)
check("S5 무지연(사용자 경로=인라인만·봇 디커플링) + 준실시간(producer→finding p95 ≤ 5s)",
      s5_ok, f"사용자 경로 p95={user_p95}ms(봇 디커플링={decoupled}), "
             f"producer→finding p95={finding_p95}ms (n={len(finding_lat)})")

# ── S6: 자동 검증 집계(멱등) ──
prior_all = all(ok for _, ok in rows)
s6_ok = (
    prior_all
    and (WS / "audit_findings.jsonl").exists()
    and (WS / "alerts.jsonl").exists()
    and str(WS).endswith("logs/demo_audit_separation")  # 격리 워크스페이스(멱등)
)
check("S6 자동 검증 — S1~S5 PASS/FAIL 집계 + 멱등(격리 워크스페이스 logs/demo_audit_separation)",
      s6_ok, f"S1~S5 통과={prior_all}, findings/alerts 산출물 소비={(WS/'audit_findings.jsonl').exists()}")

passed = sum(1 for _, ok in rows if ok)
total = len(rows)
print()
print(f"  {B}요약{Z}: {G}{passed}{Z}/{total} 시나리오 PASS, {R}{total-passed}{Z} FAIL")
if passed == total:
    print(f"  {G}✅ S6 자동 검증 — 6개 시나리오 전부 기대대로 동작 (데모 PASS){Z}")
    sys.exit(0)
else:
    print(f"  {R}❌ S6 자동 검증 — 일부 시나리오 실패 (위 [FAIL] 확인){Z}")
    sys.exit(1)
PY
RC=$?
exit $RC
