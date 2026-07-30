"""NuFi Python SDK — 라이브러리 직접 임포트 예시.

게이트웨이 없이 엔진을 인프로세스로 사용하는 방법을 보여줍니다.
자세한 API 문서: docs/SDK.md

실행:
    python3 examples/library_detect.py
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from nufi import (
    detect,           # 즉시 탐지 (기본 Detector 지연 로딩)
    Detector,         # 재사용 가능한 탐지 인스턴스
    pseudonymize,     # 비가역 토큰화
    mask,             # 마스킹
    Guard,            # 정책 평가 (외부로 보내도 되나?)
    batch_detect,     # 여러 텍스트 일괄 탐지
    __version__,
)

print(f"NuFi SDK v{__version__}\n")

# --- 1. 즉시 탐지 (한 줄) -------------------------------------------
text = "고객 홍길동님의 주민번호 798326-3487729를 확인해 주세요."
findings = detect(text)
print(f"[탐지] '{text}'")
for f in findings:
    print(f"  → {f.entity_type}: '{f.text}' (score={f.score:.2f})")
print()

# --- 2. Detector 재사용 (모델 한 번만 로딩) --------------------------
det = Detector()
texts = [
    "계좌번호 110-123-456789로 이체 부탁드립니다.",
    "이메일은 user@example.com 입니다.",
    "오늘 날씨가 맑습니다.",   # PII 없음
]
print("[일괄 탐지]")
for t in texts:
    fs = det.analyze(t)
    label = ", ".join(f"{f.entity_type}({f.text})" for f in fs) if fs else "없음"
    print(f"  '{t}' → {label}")
print()

# --- 3. 가명화 (비가역) ---------------------------------------------
print("[가명화]")
token = pseudonymize("KR_PERSON", "홍길동")
print(f"  홍길동 → {token}")
masked = mask("798326-3487729", keep_tail=4)
print(f"  798326-3487729 → {masked}")
print()

# --- 4. 정책 평가 (외부 전송 가부) ----------------------------------
print("[정책 평가]")
result = Guard().inspect(text)
if result.blocked:
    blocked_types = list({a["entity_type"] for a in result.decision.actions})
    print(f"  차단됨: {blocked_types}")
else:
    print("  통과: PII 없음 또는 정책 허용")
print()

# --- 5. batch_detect -------------------------------------------------
print("[batch_detect]")
all_findings = batch_detect(texts)
for t, fs in zip(texts, all_findings):
    print(f"  '{t[:30]}...' → {len(fs)}건")
