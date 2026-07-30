"""감사 로거 (SPEC M1 수용기준 2): public 행 요청 100% JSONL 적재.

각 레코드: 타임스탬프·모델·프로바이더·is_public·요청본문·탐지 결정.
온프렘 로컬 파일(NFR1). 운영시 Langfuse(MIT) 사이드카로 교체 가능.

M5 §4.3: 옵션 hash_chain=True 시 추가전용 변조탐지 해시 체인을 부착하고
verify_chain() 으로 수정·삭제·재배열·시계역행을 탐지한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

_DEFAULT_LOG = Path(__file__).resolve().parent.parent / "logs" / "egress_audit.jsonl"

# 해시 체인 제네시스(이전 해시 없음).
GENESIS_HASH = "0" * 64


def _record_hash(record: dict) -> str:
    """체인 해시 = sha256(prev_hash + canonical(payload)).

    payload 는 chain.hash 를 제외한 레코드 본문(키 정렬 → 결정적 직렬화).
    """
    chain = record.get("chain", {})
    prev = chain.get("prev_hash", GENESIS_HASH)
    payload = {k: v for k, v in record.items() if k != "chain"}
    payload["_seq"] = chain.get("seq")
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev + blob).encode("utf-8")).hexdigest()


class AuditLogger:
    """public 행 요청 100% 적재 + (옵션) 추가전용 변조탐지 해시 체인(M5 §4.3).

    hash_chain=True 시 각 레코드에 chain={seq, prev_hash, hash} 를 부착한다.
    이전 해시를 포함하므로 임의 행 수정·삭제·재배열이 verify_chain() 으로 탐지된다.
    원문 PII 평문 저장 금지 — request_body 마스킹은 호출자(게이트웨이) 책임.
    """

    def __init__(self, path: Optional[str] = None, hash_chain: Optional[bool] = None):
        self.path = Path(path or os.environ.get("EGRESS_AUDIT_LOG", str(_DEFAULT_LOG)))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if hash_chain is None:
            hash_chain = os.environ.get("EGRESS_AUDIT_HASH_CHAIN", "0") == "1"
        self.hash_chain = hash_chain
        self._last_hash = None
        self._last_seq = -1
        if self.hash_chain:
            self._recover_chain_tip()

    def _recover_chain_tip(self) -> None:
        """기존 로그 끝에서 체인 상태 복구(append-only 연속성)."""
        if not self.path.exists():
            return
        last = None
        with open(self.path, "r", encoding="utf-8") as f:
            for ln in f:
                if ln.strip():
                    last = ln
        if last:
            ch = json.loads(last).get("chain")
            if ch:
                self._last_hash = ch.get("hash")
                self._last_seq = ch.get("seq", -1)

    def log(self, *, model: str, provider: str, is_public: bool, request_body,
            decision_summary: Optional[dict] = None, findings=None,
            outcome: str = "forwarded", extra: Optional[dict] = None) -> str:
        record = {
            "id": str(uuid.uuid4()),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "epoch_ms": int(time.time() * 1000),
            "model": model,
            "provider": provider,
            "is_public": is_public,
            "outcome": outcome,                      # forwarded | blocked | transformed
            "decision": decision_summary or {},
            "findings": findings or [],
            "request_body": request_body,
        }
        if extra:
            record["extra"] = extra
        with self._lock:
            if self.hash_chain:
                seq = self._last_seq + 1
                prev = self._last_hash or GENESIS_HASH
                record["chain"] = {"seq": seq, "prev_hash": prev}
                h = _record_hash(record)
                record["chain"]["hash"] = h
                self._last_hash, self._last_seq = h, seq
            line = json.dumps(record, ensure_ascii=False)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return record["id"]

    def read_all(self):
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]

    def verify_chain(self) -> dict:
        """해시 체인 무결성 검증(M5 §4.3 변조탐지).

        반환: {ok, count, error, broken_seq}. 수정·삭제·재배열·시계역행 탐지.
        """
        return verify_chain_records(self.read_all())


def verify_chain_records(records: list) -> dict:
    """이미 로드된 레코드 리스트의 해시 체인 무결성 검증(M5 §4.3 변조탐지).

    AuditLogger.verify_chain() 의 순수-검증 코어. 파일/디렉터리 생성 등 부수효과가
    없어 read-only 관측(예: dashboards 어댑터)에서 안전하게 재사용된다.
    반환: {ok, count, error, broken_seq}. 수정·삭제·재배열·시계역행 탐지.
    """
    prev = GENESIS_HASH
    last_seq = -1
    last_epoch = -1
    for i, rec in enumerate(records):
        ch = rec.get("chain")
        if not ch:
            return {"ok": False, "count": len(records), "broken_seq": i,
                    "error": "chain 필드 없음(비체인 레코드)"}
        if ch.get("seq") != last_seq + 1:
            return {"ok": False, "count": len(records), "broken_seq": ch.get("seq"),
                    "error": f"seq 불연속: {ch.get('seq')} (기대 {last_seq + 1}) — 행 삭제/재배열 의심"}
        if ch.get("prev_hash") != prev:
            return {"ok": False, "count": len(records), "broken_seq": ch.get("seq"),
                    "error": "prev_hash 불일치 — 앞선 행 변조 의심"}
        if _record_hash(rec) != ch.get("hash"):
            return {"ok": False, "count": len(records), "broken_seq": ch.get("seq"),
                    "error": "레코드 해시 불일치 — 본문 변조 의심"}
        ep = rec.get("epoch_ms", 0)
        if ep < last_epoch:
            return {"ok": False, "count": len(records), "broken_seq": ch.get("seq"),
                    "error": "타임스탬프 역행 — 시계 신뢰 위반(§4.3)"}
        prev = ch["hash"]
        last_seq = ch["seq"]
        last_epoch = ep
    return {"ok": True, "count": len(records), "error": None, "broken_seq": None}
