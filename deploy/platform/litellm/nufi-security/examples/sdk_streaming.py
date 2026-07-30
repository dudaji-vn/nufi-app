"""CMP-119 수용기준 4 — 비스트리밍·스트리밍 사용법.

같은 호출을 stream=False / stream=True 로 보여준다. 스트리밍은 OpenAI 와
동일하게 청크의 delta.content 를 누적한다.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # 소스 실행용(pip 설치 시 불필요)

from nufi_client import NuFi

client = NuFi()
messages =[{"role": "user", "content": "온프렘 게이트웨이 장점 한 문장으로"}]

# --- 비스트리밍 ---------------------------------------------------------
resp = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
print("[non-stream]", resp.choices[0].message.content)

# --- 스트리밍 -----------------------------------------------------------
print("[stream]    ", end="")
buf = []
for chunk in client.chat.completions.create(
        model="gpt-4o-mini", messages=messages, stream=True):
    delta = chunk.choices[0].delta.content
    if delta:
        buf.append(delta)
        print(delta, end="", flush=True)
print()
assert "".join(buf) == resp.choices[0].message.content
print("OK — 스트리밍/비스트리밍 동일 출력 확인")
