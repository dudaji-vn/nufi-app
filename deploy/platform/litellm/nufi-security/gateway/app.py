"""standalone Egress-Audit 게이트웨이 (FastAPI). LiteLLM 미설치 환경에서 PoC를 실행·검증.

OpenAI 호환 /v1/chat/completions 엔드포인트. 의사결정은 gateway.core.Gateway 가 담당:
  1. 라우팅: 기본 private, private 불가(EGRESS_PRIVATE_DOWN=1) 시 public 폴백.
  2. public 경로면 송신 직전 EgressGuard 탐지(pre_call): block/redact/pseudonymize/warn.
  3. public 행 요청은 100% 감사 로그(JSONL)에 적재(SPEC M1 기준 2).

프로덕션 경로는 LiteLLM Proxy + gateway/litellm_hook.py (config/litellm_config.yaml).
기동: uvicorn gateway.app:app --port 4000
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gateway.core import Gateway

app = FastAPI(title="NuFi Egress-Audit Gateway (PoC)")
gateway = Gateway()


@app.get("/health")
def health():
    return {"status": "ok", "ner_backend": gateway.ner_backend}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    resp = gateway.process(body)
    headers = {}
    if resp.latency_ms is not None:
        headers["X-NuFi-Latency-Ms"] = str(round(resp.latency_ms, 1))
    return JSONResponse(status_code=resp.status, content=resp.body, headers=headers)
