"""NuFi Python SDK — 파일 단위 PII 탐지·정책 평가 예시.

scan_file / guard_file / batch_detect 편의 함수를 사용합니다.
자세한 API 문서: docs/SDK.md

실행:
    python3 examples/sdk_file_scan.py
"""
import pathlib, sys, tempfile, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from nufi import scan_file, guard_file, batch_detect

# --- 임시 테스트 파일 준비 -----------------------------------------
_TMP_PII = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
_TMP_PII.write("고객 홍길동님의 주민번호 798326-3487729를 확인해 주세요.\n")
_TMP_PII.write("계좌번호 110-123-456789로 이체 바랍니다.\n")
_TMP_PII.flush()
_TMP_PII.close()

_TMP_CLEAN = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
_TMP_CLEAN.write("오늘 회의는 오후 3시 대회의실에서 진행됩니다.\n")
_TMP_CLEAN.flush()
_TMP_CLEAN.close()

try:
    # --- 1. scan_file — 파일에서 PII 찾기 ----------------------------
    print("[scan_file] PII 포함 파일")
    findings = scan_file(_TMP_PII.name)
    for f in findings:
        print(f"  → {f.entity_type}: '{f.text}' (score={f.score:.2f})")
    print(f"  총 {len(findings)}건 탐지\n")

    # --- 2. guard_file — 외부 전송 가부 판정 -------------------------
    print("[guard_file] PII 포함 파일 → 차단 여부")
    result = guard_file(_TMP_PII.name)
    if result.blocked:
        actions = [a["entity_type"] for a in result.decision.actions]
        print(f"  차단됨: {actions}")
    else:
        print("  통과: PII 없음 또는 정책 허용")

    print("\n[guard_file] 클린 파일 → 통과 여부")
    result_clean = guard_file(_TMP_CLEAN.name)
    status = "차단됨" if result_clean.blocked else "통과"
    print(f"  {status}")
    print()

    # --- 3. batch_detect — 여러 텍스트 일괄 처리 ----------------------
    print("[batch_detect]")
    texts = [
        "이메일: user@example.com / 전화: 010-1234-5678",
        "여권번호 M12345678 소지자",
        "오늘 날씨가 좋습니다.",
    ]
    all_findings = batch_detect(texts)
    for t, fs in zip(texts, all_findings):
        label = ", ".join(f"{f.entity_type}" for f in fs) if fs else "없음"
        print(f"  '{t[:35]}' → {label}")

finally:
    os.unlink(_TMP_PII.name)
    os.unlink(_TMP_CLEAN.name)
