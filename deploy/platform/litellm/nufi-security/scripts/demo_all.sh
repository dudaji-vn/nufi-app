#!/usr/bin/env bash
# =============================================================================
# NuFi 전체 데모 러너 — 모든 기능 데모를 차례로 실행하고 집계 결과를 출력한다.
#
# 특정 버전이 아니라 현재 저장소의 기능 데모 전부를 한 명령으로 재현·검증한다.
# 각 데모는 독립 PASS/FAIL 을 내고, 본 러너는 이를 모아 집계한다. 사전조건이 없는
# (모델 측정 산출물·root) 데모는 정직하게 SKIP 으로 분류한다(FAIL 아님).
#
#   demo.sh                  게이트웨이 e2e — private 라우팅·강한 PII/비밀 차단·가명화·감사
#   demo_coverage.sh         감사 커버리지 — public 전송 100% 기록 무결성
#   demo_report.sh           규정준수 리포트 — 해시체인 게이트 + 점검항목 커버리지
#   demo_compliance_mapping.sh 컴플라이언스 매핑 — 점검항목 커버리지(직접/부분/범위밖)
#   demo_policy_ops.sh       정책 운영 — 다중 프로파일·바인딩·무재기동 롤백·변경 감사
#   demo_pseudonymize.sh     가명화 품질 — 가역/비가역 지표·충돌율 0·결정성·차단 유지
#   demo_audit_separation.sh 차등 감사 — public/private 분리 + 패킷 우회 탭 + 비동기 봇
#   demo_location_union.sh   주소 유니온 — 모델 ∪ 확장규칙(P2)로 KR_LOCATION 재현율 향상
#   demo_pii_routing.sh      PII 라우팅 — PII 포함→로컬, PII 없음→클라우드(4시나리오)
#   demo_transform.sh        텍스트 변환 — mask·redact·explain(PII 마스킹/리댁션/상세설명)
#   demo_litellm_e2e.sh      LiteLLM Proxy E2E — 프록시 기동·PII 라우팅·감사(litellm 필요)
#   demo_accuracy.sh         정확도 재현 — KR_PERSON INT8 CI + 온프렘 p95 (측정 산출물 필요)
#
#   * demo_bypass_enforcement.sh(우회 실제 ENFORCED drop)는 root/nft 가 필요한
#     하위 데모로, demo_audit_separation.sh --enforce 경로에서 실행된다(여기선 제외).
#
# 집계 규칙: FAIL 이 하나라도 있으면 비-0 종료. SKIP(사전조건 부재)은 실패가 아니다.
# root 불필요 · 외부 네트워크 호출 0(stub 백엔드 + gazetteer NER + 임시 픽스처).
#
# 사용:   ./scripts/demo_all.sh
# 매뉴얼: docs/DEMO.md(데모 카탈로그) · docs/RELEASE_NOTES.md(사람 친화 요약)
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
hr() { printf '%s\n' "============================================================"; }

PASS=0 ; FAIL=0 ; SKIP=0
declare -a RESULTS=()

run_demo() {
  # run_demo <스크립트> <한 줄 설명>
  local script="$1" ; local label="$2"
  echo
  hr ; bold "데모: $script — $label" ; hr
  local out
  out=$(./scripts/"$script" 2>&1) || true
  local rc=$?
  echo "$out"
  # 데모가 exit 0 + "SKIP:" 출력 → 사전조건 부재 skip(FAIL 아님).
  if echo "$out" | head -3 | grep -q '^SKIP:'; then
    echo ">> $script SKIP" ; SKIP=$((SKIP + 1)) ; RESULTS+=("SKIP  $script")
  elif [ "$rc" -eq 0 ]; then
    echo ">> $script PASS" ; PASS=$((PASS + 1)) ; RESULTS+=("PASS  $script")
  else
    echo ">> $script FAIL" ; FAIL=$((FAIL + 1)) ; RESULTS+=("FAIL  $script")
  fi
}

skip_demo() {
  # skip_demo <스크립트> <사유>
  local script="$1" ; local reason="$2"
  echo
  hr ; bold "데모: $script — SKIP" ; hr
  echo ">> $script SKIP ($reason)" ; SKIP=$((SKIP + 1)) ; RESULTS+=("SKIP  $script ($reason)")
}

run_demo demo.sh                  "게이트웨이 e2e(private 라우팅·차단·가명화·감사)"
run_demo demo_coverage.sh         "감사 커버리지(전송 100% 기록 무결성)"
run_demo demo_report.sh           "규정준수 리포트(해시체인 + 점검항목 커버리지)"
run_demo demo_compliance_mapping.sh "컴플라이언스 매핑(점검항목 커버리지 직접/부분/범위밖)"
run_demo demo_policy_ops.sh       "정책 운영(프로파일·바인딩·롤백·변경 감사)"
run_demo demo_pseudonymize.sh     "가명화 품질(가역/비가역 지표·충돌율 0·결정성·차단 유지)"
run_demo demo_audit_separation.sh "차등 감사(분리 저장 + 우회 탭 + 비동기 봇)"
run_demo demo_location_union.sh   "주소 유니온(모델 ∪ 확장규칙 P2 · KR_LOCATION 재현율)"
run_demo demo_sdk.sh              "Python SDK(from nufi import — 탐지·가명화·정책 평가)"
run_demo demo_resilience.sh       "게이트웨이 강건성(타임아웃·방어파싱·지연추적)"
run_demo demo_sdk_helpers.sh      "SDK 편의 함수(scan_file·guard_file·batch_detect)"
run_demo demo_pii_routing.sh     "PII 라우팅(PII 포함→로컬, PII 없음→클라우드)"
run_demo demo_prompt_injection.sh "프롬프트 인젝션 탐지(한/영 패턴·Guard 차단·혼합)"
run_demo demo_bench_injection.sh "인젝션 탐지 벤치마크(재현율·정밀도 측정 30건 골드셋)"
run_demo demo_scan.sh            "파일/디렉터리 PII 스캔(CI/pre-commit · --redact · SARIF)"
run_demo demo_getting_started.sh "Getting-started 워크플로(init→scan→redact→inspect→route→doctor)"
run_demo demo_transform.sh      "텍스트 변환(mask·redact·explain — PII 마스킹/리댁션/상세설명)"
run_demo demo_litellm_e2e.sh     "LiteLLM Proxy E2E(프록시 기동→PII 라우팅→감사 검증)"
run_demo demo_cli_showcase.sh   "CLI 쇼케이스(playground·summary·pipeline·mask·redact)"
run_demo demo_injection_e2e.sh  "인젝션 E2E(탐지→차단→감사 전 구간 검증)"
# NOTE: demo_bypass_enforcement.sh 는 root/nft 권한이 필요하여 의도적으로 제외.

# 정확도 데모는 커밋된 측정 산출물(docs/reports/*.json)이 있어야 재현 가능하다.
if [ -f "$ROOT/docs/reports/recall-int8.json" ] \
   && [ -f "$ROOT/docs/reports/load-p95.json" ]; then
  run_demo demo_accuracy.sh       "정확도 재현(KR_PERSON INT8 CI + 온프렘 p95)"
else
  skip_demo demo_accuracy.sh "측정 산출물 부재 — 모델 스택으로 재측정 필요(헤더 참조)"
fi

echo
hr ; bold "전체 데모 집계" ; hr
for r in "${RESULTS[@]}"; do echo "  $r"; done
hr
echo "결과: PASS=$PASS  FAIL=$FAIL  SKIP=$SKIP"
if [ "$FAIL" -eq 0 ]; then
  bold "✅ 전체 데모 PASS (실행 $PASS · 건너뜀 $SKIP)"
else
  bold "❌ 전체 데모 FAIL — 실패 $FAIL 개"
fi
exit "$FAIL"
