"""SDK 전송 계층 (CMP-119).

두 가지 모드로 게이트웨이 `/v1/chat/completions` 를 재사용한다:

- `InProcessTransport`  : 같은 프로세스에서 `gateway.core.Gateway` 직접 호출.
  서버 기동 없이 예제·테스트가 동작하고, 감사 id/outcome 등 메타를 그대로 노출.
- `HttpTransport`       : 실행 중인 게이트웨이(`uvicorn gateway.app:app`)로 HTTP POST.
  기존 OpenAI 클라이언트의 `base_url` 만 바꾸는 심과 동일한 경로.

두 전송 모두 `complete(body) -> CompletionResult` 를 구현한다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class CompletionResult:
    status: int                         # 200 정상 / 403 차단
    body: Dict[str, Any]
    audit_id: Optional[str] = None      # in-process 에서만 채워짐
    outcome: Optional[str] = None       # forwarded | transformed | blocked | private
    entities: Optional[List[str]] = None

    @property
    def blocked(self) -> bool:
        return self.status == 403


class InProcessTransport:
    """서버 없이 `gateway.core.Gateway` 를 직접 호출(기본값).

    `audit_log` 을 주면 격리된 감사 로그 경로로 `Gateway` 를 구성한다(데모/테스트용).
    이미 만들어진 `gateway` 인스턴스를 주입할 수도 있다.
    """

    def __init__(self, gateway: Any = None, audit_log: Optional[str] = None):
        if gateway is None:
            # 게이트웨이 의존(fastapi 등)은 in-process 사용 시에만 로드.
            from gateway.core import Gateway
            if audit_log is not None:
                from egress_audit import AuditLogger
                gateway = Gateway(audit=AuditLogger(path=audit_log))
            else:
                gateway = Gateway()
        self.gateway = gateway

    def complete(self, body: Dict[str, Any]) -> CompletionResult:
        resp = self.gateway.process(body)
        return CompletionResult(status=resp.status, body=resp.body,
                                audit_id=resp.audit_id, outcome=resp.outcome,
                                entities=list(resp.blocked_entities or []))


class HttpTransport:
    """실행 중인 게이트웨이로 HTTP POST. `base_url` 은 `/v1` 접미 유무 모두 허용."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        base = base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        self.endpoint = f"{base}/v1/chat/completions"
        self.timeout = timeout

    def complete(self, body: Dict[str, Any]) -> CompletionResult:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint, data=data, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                payload = json.loads(r.read().decode("utf-8"))
                status = r.status
        except urllib.error.HTTPError as e:               # 403 등은 본문 보존
            payload = json.loads(e.read().decode("utf-8"))
            status = e.code
        entities = None
        if status == 403:
            err = payload.get("error", {}) or {}
            entities = err.get("entities")
        return CompletionResult(status=status, body=payload, outcome=None,
                                entities=entities)
