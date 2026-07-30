"""CMP-119 수용기준 1 — 기존 OpenAI 호출을 NuFi 경유로 3~5줄 전환.

Before (직접 OpenAI):
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(model="gpt-4o-mini", messages=msgs)

After (NuFi 경유 — import 1줄 + 생성 1줄만 교체):
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # 소스 실행용(pip 설치 시 불필요)

from nufi_client import NuFi                                   # ← 1줄 교체

client = NuFi()                                                # ← 1줄 교체
resp = client.chat.completions.create(                        # 호출부는 그대로
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "회사 행동강령 3줄 요약해줘"}])
print(resp.choices[0].message.content)                        # OpenAI 와 동일
print("outcome:", resp.outcome, "| audit:", resp.audit_id)
