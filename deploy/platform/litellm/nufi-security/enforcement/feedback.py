"""drop 피드백 루프 (CMP-94 트랙 B · 스펙 §8.1-4, §4.3).

커널 drop 로그(``nufi-egress-block `` prefix, nft ``log`` 액션)를 파싱해:
  1. ``blocked_attempts`` 카운터를 증가(감사 증적·대시보드, A3).
  2. flow 호환 레코드(``kind=flow``, ``bypass=true``, ``blocked=true``)로 변환해
     P1/P2 flow 디렉터리에 재유입 → "막힌 시도"도 감사에 남는다.

입력은 journald/dmesg 라인 iterable(파일·스트림·테스트 픽스처). 호스트 무관·root 불요
파싱이므로 CI 에서 골든 검증 가능.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .rule_builder import LOG_PREFIX

_ROOT = Path(__file__).resolve().parent.parent
_PREFIX = LOG_PREFIX.strip()       # "nufi-egress-block"


@dataclass
class BlockedAttempt:
    src_ip: Optional[str]
    dst_ip: Optional[str]
    dst_port: Optional[int]
    proto: Optional[str]
    raw: str

    def to_flow_record(self) -> Dict[str, Any]:
        """P1/P2 가 읽는 flow 레코드로 변환(막힌 우회 = high-sev, blocked)."""
        return {
            "flow_id": str(uuid.uuid4()),
            "kind": "flow",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "src_ip": self.src_ip,
            "dst_ip": self.dst_ip,
            "dst_host": None,
            "dst_port": self.dst_port,
            "bypass": True,            # drop 된 건 정의상 비-게이트웨이 우회
            "blocked": True,           # enforcement 가 실제 drop
            "severity": "high",
            "source": "egress_enforcement_drop",
        }


def parse_drop_line(line: str) -> Optional[BlockedAttempt]:
    """nft log 한 줄에서 우리 prefix 의 drop 만 파싱. 무관 라인은 None."""
    if _PREFIX not in line:
        return None
    tail = line.split(_PREFIX, 1)[1]
    fields: Dict[str, str] = {}
    for tok in tail.split():
        if "=" in tok:
            k, _, v = tok.partition("=")
            fields[k.upper()] = v
    dpt = fields.get("DPT")
    return BlockedAttempt(
        src_ip=fields.get("SRC"),
        dst_ip=fields.get("DST"),
        dst_port=int(dpt) if dpt and dpt.isdigit() else None,
        proto=fields.get("PROTO"),
        raw=line.strip(),
    )


def parse_drops(lines: Iterable[str]) -> List[BlockedAttempt]:
    out: List[BlockedAttempt] = []
    for ln in lines:
        a = parse_drop_line(ln)
        if a is not None:
            out.append(a)
    return out


class DropFeedback:
    """drop 로그 → blocked_attempts 카운터 + flow 재유입."""

    def __init__(self, counter_path: Optional[str] = None,
                 flow_dir: Optional[str] = None):
        cp = Path(counter_path or (_ROOT / "logs" / "blocked_attempts.json"))
        self.counter_path = cp if cp.is_absolute() else (_ROOT / cp)
        fd = Path(flow_dir or (_ROOT / "logs" / "packets" / "public"))
        self.flow_dir = fd if fd.is_absolute() else (_ROOT / fd)

    def _load_counter(self) -> Dict[str, Any]:
        if self.counter_path.exists():
            try:
                return json.loads(self.counter_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        return {"blocked_attempts": 0, "by_dst": {}}

    def _save_counter(self, c: Dict[str, Any]) -> None:
        self.counter_path.parent.mkdir(parents=True, exist_ok=True)
        self.counter_path.write_text(json.dumps(c, ensure_ascii=False, indent=2),
                                     encoding="utf-8")

    def ingest(self, lines: Iterable[str], *, reinject: bool = True) -> Dict[str, Any]:
        """drop 라인 배치 처리: 카운터 증가 + (옵션) flow 재유입.

        반환: {parsed, blocked_attempts(누적), reinjected}.
        """
        attempts = parse_drops(lines)
        counter = self._load_counter()
        counter["blocked_attempts"] += len(attempts)
        by_dst = counter.setdefault("by_dst", {})
        for a in attempts:
            key = f"{a.dst_ip}:{a.dst_port}"
            by_dst[key] = by_dst.get(key, 0) + 1
        self._save_counter(counter)

        reinjected = 0
        if reinject and attempts:
            day = time.strftime("%Y%m%d")
            self.flow_dir.mkdir(parents=True, exist_ok=True)
            out = self.flow_dir / f"flow-{day}.jsonl"
            with open(out, "a", encoding="utf-8") as f:
                for a in attempts:
                    f.write(json.dumps(a.to_flow_record(), ensure_ascii=False) + "\n")
                    reinjected += 1
        return {
            "parsed": len(attempts),
            "blocked_attempts": counter["blocked_attempts"],
            "reinjected": reinjected,
        }

    def count(self) -> int:
        return int(self._load_counter().get("blocked_attempts", 0))
