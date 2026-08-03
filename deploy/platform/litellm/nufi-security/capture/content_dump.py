"""게이트웨이 출구 평문 content dump (CMP-87 P1 (a)).

public LLM 은 TLS 라서 와이어에서 본문을 읽을 수 없다. 따라서 게이트웨이가 public 으로
내보내기 **직전**(TLS 적용 전)의 직렬화된 HTTP 요청을 "패킷 단위 입도"로 dump 한다.
P2 비동기 감사 봇의 본문 감사 입력이 된다.

출력: logs/packets/public/dump-YYYY-MM-DD.jsonl
온프렘 로컬 파일(NFR1). 본문 보존 정책은 호출측(gateway/core)이 결정해 넘긴다
(public 기본 = 가명화 통과본; retain_raw 시 원문).
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent


def _serialize_http(method: str, host: str, path: str,
                    headers: Dict[str, str], body: Any) -> str:
    """TLS 직전 직렬화된 HTTP 요청 평문(request line + headers + body)."""
    body_str = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    lines = [f"{method} {path} HTTP/1.1", f"Host: {host}"]
    for k, v in (headers or {}).items():
        lines.append(f"{k}: {v}")
    lines.append("")
    lines.append(body_str)
    return "\r\n".join(lines)


class ContentDumpWriter:
    """게이트웨이 출구 평문 본문 dump writer."""

    def __init__(self, base_dir: Optional[str] = None):
        raw = (base_dir or os.environ.get("EGRESS_PACKET_DIR") or "logs/packets")
        base = Path(raw)
        self.base_dir = base if base.is_absolute() else (_ROOT / base)
        self._lock = threading.Lock()

    def _sink_path(self) -> Path:
        day = time.strftime("%Y-%m-%d", time.localtime())
        return self.base_dir / "public" / f"dump-{day}.jsonl"

    def dump(self, *, conversation_id: str, dst_host: str, dst_port: int,
             backend: str, provider: str, body: Any,
             method: str = "POST", path: str = "/",
             headers: Optional[Dict[str, str]] = None,
             body_retained: str = "sanitized",
             extra: Optional[dict] = None) -> str:
        """게이트웨이 출구 평문 요청 1건을 dump 하고 dump id 반환."""
        headers = headers or {}
        http_request = _serialize_http(method, dst_host, path, headers, body)
        record = {
            "id": str(uuid.uuid4()),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "epoch_ms": int(time.time() * 1000),
            "conversation_id": conversation_id,
            "dst_host": dst_host,
            "dst_port": dst_port,
            "backend": backend,
            "provider": provider,
            "method": method,
            "path": path,
            "headers": headers,
            "http_request": http_request,   # TLS 직전 평문 직렬화(패킷 입도)
            "body": body,                   # 정책 적용본(가명화/원문)
            "body_retained": body_retained,
            "source": "gateway_egress",
        }
        if extra:
            record["extra"] = extra
        line = json.dumps(record, ensure_ascii=False)
        p = self._sink_path()
        with self._lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return record["id"]

    def read_all(self) -> list[dict]:
        """적재된 모든 content dump 레코드를 시간순으로 반환(테스트·감사 봇 입력)."""
        d = self.base_dir / "public"
        if not d.exists():
            return []
        out: list[dict] = []
        for p in sorted(d.glob("dump-*.jsonl")):
            with open(p, "r", encoding="utf-8") as f:
                out.extend(json.loads(ln) for ln in f if ln.strip())
        return out
