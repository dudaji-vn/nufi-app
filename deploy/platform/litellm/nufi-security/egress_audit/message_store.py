"""MessageStore (CMP-86 P0): private/public in·out 메시지 분리 저장.

요구사항(1)(2): 고객 요청 패킷을 저장하되 private 질의와 public 질의를 분리
저장하고, 양쪽의 in(요청)·out(응답) 메시지를 모두 동일 conversation_id 로 묶어
저장한다.

- 분리 싱크(설정 가능): logs/messages/{private|public}/YYYY-MM-DD.jsonl
- 본문 보존 정책은 config/audit_profiles.yaml 의 profiles.{class}.retain_raw 로
  외부화(NFR3). private 기본 원문 보존, public 기본 가명화 통과본 저장.

온프렘 로컬 파일(NFR1). 기존 audit.py(public 단일 egress 로거)를 일반화·확장한 것.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PROFILES = _ROOT / "config" / "audit_profiles.yaml"

VALID_CLASSES = ("private", "public")
VALID_DIRECTIONS = ("in", "out")


def _load_profiles(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class MessageStore:
    """egress_class 로 싱크를 선택해 in/out 메시지를 분리 저장한다."""

    def __init__(self, base_dir: Optional[str] = None,
                 profiles_path: Optional[str] = None):
        self.profiles_path = Path(profiles_path or os.environ.get(
            "EGRESS_AUDIT_PROFILES", str(_DEFAULT_PROFILES)))
        cfg = _load_profiles(self.profiles_path)
        ms_cfg = cfg.get("message_store", {})
        self.profiles = cfg.get("profiles", {})

        # base_dir 우선순위: 인자 > 환경변수 > 설정 파일 > 기본값.
        raw_base = (base_dir or os.environ.get("EGRESS_MESSAGE_STORE_DIR")
                    or ms_cfg.get("base_dir") or "logs/messages")
        base = Path(raw_base)
        self.base_dir = base if base.is_absolute() else (_ROOT / base)
        self._lock = threading.Lock()

    # ---- 본문 보존 정책 ----------------------------------------------------
    def retain_raw(self, egress_class: str) -> bool:
        """해당 클래스의 원문 보존 여부. 기본값: private=True, public=False."""
        prof = self.profiles.get(egress_class, {})
        return bool(prof.get("retain_raw", egress_class == "private"))

    def _apply_retention(self, egress_class: str, body: Any,
                         raw_body: Any) -> tuple[Any, str]:
        """정책에 따라 저장할 본문과 보존 모드('raw'|'sanitized')를 결정.

        body     = 기본(가명화/통과본 또는 유일 본문)
        raw_body = 원문(가명화 전). body 와 다를 때만 의미가 있다.
        """
        if self.retain_raw(egress_class):
            stored = raw_body if raw_body is not None else body
            return stored, "raw"
        # 원문 미보존: 통과본(body)을 저장. raw 와 동일하면 변환이 없었던 것.
        mode = "sanitized" if (raw_body is not None and raw_body != body) else "raw"
        return body, mode

    # ---- 적재 -------------------------------------------------------------
    def _sink_path(self, egress_class: str) -> Path:
        day = time.strftime("%Y-%m-%d", time.localtime())
        return self.base_dir / egress_class / f"{day}.jsonl"

    def record(self, *, conversation_id: str, direction: str, egress_class: str,
               model: str, provider: str, body: Any,
               raw_body: Any = None, turn: int = 1,
               inline_decision: Optional[dict] = None,
               source: str = "gateway",
               extra: Optional[dict] = None) -> str:
        """in/out 메시지 한 건을 egress_class 싱크에 적재하고 record id 반환."""
        if egress_class not in VALID_CLASSES:
            raise ValueError(f"egress_class must be one of {VALID_CLASSES}, got {egress_class!r}")
        if direction not in VALID_DIRECTIONS:
            raise ValueError(f"direction must be one of {VALID_DIRECTIONS}, got {direction!r}")

        stored_body, retained = self._apply_retention(egress_class, body, raw_body)
        record = {
            "id": str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "turn": turn,
            "direction": direction,              # in=고객→백엔드, out=백엔드→고객
            "egress_class": egress_class,        # private | public
            "model": model,
            "provider": provider,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "epoch_ms": int(time.time() * 1000),
            "body": stored_body,
            "body_retained": retained,           # raw | sanitized
            "inline_decision": inline_decision or {},
            "source": source,                    # gateway | packet_dump (P1 합류)
        }
        if extra:
            record["extra"] = extra

        path = self._sink_path(egress_class)
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return record["id"]

    # ---- 읽기(테스트·감사 봇 입력) ----------------------------------------
    def read_class(self, egress_class: str) -> list[dict]:
        """해당 클래스의 모든 날짜 싱크 레코드를 시간순으로 반환."""
        d = self.base_dir / egress_class
        if not d.exists():
            return []
        out: list[dict] = []
        for p in sorted(d.glob("*.jsonl")):
            with open(p, "r", encoding="utf-8") as f:
                out.extend(json.loads(ln) for ln in f if ln.strip())
        return out
