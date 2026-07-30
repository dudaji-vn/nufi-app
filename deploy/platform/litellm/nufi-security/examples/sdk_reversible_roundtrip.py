"""CMP-119 수용기준 3 — 가역 가명화 라운드트립 1건.

원문 → pseudonymize(surrogate 치환) → (LLM 왕복 가정) → restore(원복) → 원문.
세션 매핑은 with 종료 시 폐기된다.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # 소스 실행용(pip 설치 시 불필요)

from nufi_client import NuFi

client = NuFi()
original = "고객 홍길동님(010-1234-5678, hong@example.com)께 환불 안내 부탁드립니다."

with client.pseudonymize(original) as rt:
    print("원문   :", original)
    print("가명화 :", rt.masked, f"(치환 {rt.pseudonymized}건, blocked={rt.blocked})")

    # 가명화 텍스트만 외부 LLM 으로 나간다. 응답에 surrogate 가 그대로 실려온다고 가정.
    llm_response = f"네, {rt.masked} 내용 확인했습니다. 환불 처리하겠습니다."

    restored = rt.restore(llm_response)
    print("응답복원:", restored)

    assert "홍길동" in restored and "010-1234-5678" in restored
    assert "hong@example.com" in restored
    assert rt.masked != original and rt.pseudonymized >= 1
    print("OK — 가역 가명화 라운드트립 통과")
