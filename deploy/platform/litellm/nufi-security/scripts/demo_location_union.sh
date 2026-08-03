#!/usr/bin/env bash
# =============================================================================
# NuFi 주소 유니온 데모 (v0.2.0 P3)
#
# 주소(KR_LOCATION)에 한해 **프로덕션 모델 백엔드 ∪ 확장 규칙(P2)** 유니온으로
# 재현율을 끌어올리는 경로를 1-명령으로 시연·자동검증하고 PASS/FAIL 을 출력한다.
#
#   U1  유니온 이득 측정  → union_check --location: recall(union) ≥ max(model,rule),
#                           benign 오탐 0, precision 방어 → dod_pass=true (exit 0)
#   U2  FN 회복 메커니즘   → 모델(stub)이 놓친 어휘밖·구조적 주소를 규칙 유니온이 회복
#   U3  채널 격리          → 유니온이 인명·기타 PII 채널을 바꾸지 않음(주소만 추가)
#   U4  gazetteer no-op    → 규칙 내장 백엔드는 유니온이 중복 배출하지 않음
#
# 모델 스택(onnx-int8) 미제공(에어갭)이면 규칙·유니온은 라이브, 모델 리콜은 커밋된
# baseline 을 정직하게 인용한다(출처 표기). U2~U4 는 결정적 stub 로 모델 없이 재현.
#
# root 불필요 · 외부 네트워크 호출 0(gazetteer/stub NER + 커밋 산출물).
# 사용: ./scripts/demo_location_union.sh
# 매뉴얼: docs/DEMO.md(데모 카탈로그)
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="${PYTHON:-python3}"
REPORT="$ROOT/docs/reports/kr-location-union.json"

PASS=0 ; FAIL=0
ok()  { echo "  [PASS] $1" ; PASS=$((PASS+1)) ; }
bad() { echo "  [FAIL] $1" ; FAIL=$((FAIL+1)) ; }
hr()  { echo "------------------------------------------------------------" ; }

echo "============================================================"
echo " NuFi 주소 유니온 데모 — 모델 ∪ 확장규칙(P2), 주소 채널 한정"
echo " root 불필요 · 외부 호출 0 · gazetteer/stub NER"
echo "============================================================"

# --- U1: 유니온 이득 측정 (union_check --location) ---------------------------
echo ""
echo "U1 — 유니온 이득: recall(union) ≥ max(model,rule) · benign 0 · precision 방어"
OUT="$($PY scripts/union_check.py --mode location --split test --json-out "$REPORT")" ; RC=$?
echo "$OUT" | $PY -c "import sys,json; d=json.load(sys.stdin); \
print('    location_recall:', d['location_recall']); \
print('    benign_false_block:', d['benign_false_block']); \
print('    union_gain_vs_model:', d['union_gain_vs_model'], '· dod_pass:', d['dod_pass'])" 2>/dev/null \
  || echo "$OUT" | sed 's/^/    /'
if [ "$RC" -eq 0 ] && echo "$OUT" | grep -q '"dod_pass": true'; then
  ok "U1 dod_pass=true (exit 0) — union ≥ max, benign 0"
else
  bad "U1 기대=dod_pass true exit 0, 실제 exit=$RC"
fi

# --- U2/U3/U4: 메커니즘(FN 회복·채널 격리·no-op) — 결정적 stub 모델 -----------
echo ""
echo "U2/U3/U4 — 메커니즘: FN 회복 · 채널 격리 · gazetteer no-op (stub 모델)"
MECH="$($PY - <<'PY'
import sys
sys.path.insert(0, '.'); sys.path.insert(0, 'scripts')
from egress_audit import EgressGuard
from egress_audit.pipeline import DetectionPipeline
from egress_audit.detectors.korean_pii import RawSpan
from egress_audit.detectors.ner import KoreanNerDetector

class Stub:
    name = 'stub-model'; source = 'ner:stub-model'; _pool = None
    def detect(self, text):
        for kw in ('부산광역시', '청주시'):
            i = text.find(kw)
            if i >= 0:
                yield RawSpan('KR_LOCATION', kw, i, i+len(kw), 0.95, source=self.source)

def guard(union):
    p = DetectionPipeline(ner_backend='gazetteer')
    d = KoreanNerDetector.__new__(KoreanNerDetector)
    d.backend = Stub(); d.location_union = union and d.backend_name != 'gazetteer'; d.person_union = False
    p.ner = d
    return EgressGuard(pipeline=p)

def locs(g, t):
    return {f.text for f in g.inspect(t).findings if f.entity_type == 'KR_LOCATION'}

model, union = guard(False), guard(True)
oov = '배송지를 송도국제도시로, 주소는 테헤란로 152 입니다.'
# U2: 모델이 놓친 어휘밖/도로명 주소를 유니온이 회복
u2 = (not locs(model, oov)) and {'송도국제도시', '테헤란로 152'} <= locs(union, oov)
# U3: 인명 등 다른 채널 불변(주소만 추가)
t3 = '고객 김철수 님 주소는 테헤란로 152, 주민번호 900101-1234567.'
nonloc = lambda g: sorted((f.entity_type, f.start, f.end)
                          for f in g.inspect(t3).findings if f.entity_type != 'KR_LOCATION')
u3 = nonloc(model) == nonloc(union)
# U4: gazetteer 백엔드는 유니온 no-op
gz = KoreanNerDetector(backend='gazetteer', location_union=True)
u4 = (gz.location_union is False)
print(f"U2={int(u2)} U3={int(u3)} U4={int(u4)}")
PY
)"
echo "    $MECH"
[ "$(echo "$MECH" | grep -o 'U2=1')" = "U2=1" ] && ok "U2 모델 FN(어휘밖·도로명) 규칙 유니온이 회복" || bad "U2 FN 회복 실패"
[ "$(echo "$MECH" | grep -o 'U3=1')" = "U3=1" ] && ok "U3 인명·기타 PII 채널 불변(주소만 추가)" || bad "U3 채널 격리 실패"
[ "$(echo "$MECH" | grep -o 'U4=1')" = "U4=1" ] && ok "U4 gazetteer 유니온 no-op(중복 배출 없음)" || bad "U4 no-op 실패"

hr
echo "요약: $((PASS+FAIL))개 검증 중 ${PASS} PASS, ${FAIL} FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo "✅ 주소 유니온 데모 PASS — 모델 ∪ 규칙이 설계대로 동작(주소 채널 한정)"
  exit 0
else
  echo "❌ 주소 유니온 데모 FAIL — 위 [FAIL] 항목 확인"
  exit 1
fi
