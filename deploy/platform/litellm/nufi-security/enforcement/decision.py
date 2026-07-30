"""결정 로그 승격: SIMULATED → ENFORCED (CMP-94 트랙 B · 스펙 §8.1-3, §4.2).

트랙 A(``egress_audit.enforcement.EnforcementPoint``)가 내는 차단 결정 한 줄을
**그대로 승계**하고 ``mode`` 만 ``ENFORCED`` 로 바꾼다. 스키마를 새로 만들지 않는다
(스펙 §4.2). 동적·사후 차단(§4.1-2)에 해당: P2 alert 가 잡은 우회 dst 를 실행 중
``public_dst`` set 에 추가하고, 그 식별자를 ``rule_id`` 로 기록한다.

정적·사전 차단(§4.1-1)은 :class:`enforcement.applier.Applier.apply` 가 시작 시
전체 규칙 셋을 선적용하는 경로다. 본 모듈은 그 위의 동적 보강.
"""
from __future__ import annotations

import ipaddress
import socket
import subprocess
from typing import Any, Dict, List, Optional

from egress_audit.enforcement import ENFORCED, EnforcementPoint

from .applier import Applier
from .rule_builder import Resolver


def _rule_id(table: str, setname: str, ip: str, port: int) -> str:
    """동적 set 원소 식별자(nft 핸들 대용 — 멱등·역참조 가능)."""
    return f"inet/{table}/{setname}/{ip}.{port}"


def _resolve_one(host: str, port: int, resolver: Optional[Resolver]) -> List[tuple]:
    out: List[tuple] = []
    candidates: List[str]
    if resolver:
        candidates = resolver(host)
    else:
        try:
            ipaddress.ip_address(host)
            candidates = [host]
        except ValueError:
            candidates = []
            try:
                for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
                    ip = info[4][0]
                    if ip not in candidates:
                        candidates.append(ip)
            except socket.gaierror:
                candidates = []
    for ip in candidates:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        setname = "public_dst6" if addr.version == 6 else "public_dst"
        out.append((str(addr), setname))
    return out


class EnforcedDecisionLog:
    """트랙 A 결정 → ENFORCED 승격 + 동적 set 보강 + rule_id 기록."""

    def __init__(self, applier: Optional[Applier] = None,
                 point: Optional[EnforcementPoint] = None):
        self.applier = applier or Applier()
        # ENFORCED 모드 EnforcementPoint(로그 emit 재사용; apply 는 본 클래스가 담당).
        self.point = point or EnforcementPoint(mode=ENFORCED)

    def _add_element(self, setname: str, ip: str, port: int) -> bool:
        """실행 중 set 에 원소 추가(동적 사후 차단). dry-run/비특권은 no-op True."""
        if self.applier.dry_run or self.applier.backend != "nft":
            return True
        elem = f"{{ {ip} . {port} }}"
        proc = subprocess.run(
            ["nft", "add", "element", "inet", self.applier.cfg.table, setname, elem],
            text=True, capture_output=True, check=False)
        return proc.returncode == 0

    def promote(self, decision: Dict[str, Any],
                resolver: Optional[Resolver] = None) -> Dict[str, Any]:
        """트랙 A 결정 dict 를 ENFORCED 로 승격(원본 스키마 보존, 필드 추가만)."""
        dst = decision.get("dest") or decision.get("dst") or "unknown"
        port = int(decision.get("dest_port") or decision.get("dst_port") or 443)
        resolved = _resolve_one(dst, port, resolver)

        rule_ids: List[str] = []
        applied = False
        for ip, setname in resolved:
            if self._add_element(setname, ip, port):
                rule_ids.append(_rule_id(self.applier.cfg.table, setname, ip, port))
                applied = True

        out = dict(decision)               # 트랙 A 스키마 그대로 승계
        out["mode"] = ENFORCED
        out["applied"] = applied
        out["rule_id"] = rule_ids[0] if rule_ids else None
        out["rule_ids"] = rule_ids
        out["control_point"] = f"nftables inet/{self.applier.cfg.table} (ENFORCED)"
        out["enforcement_backend"] = self.applier.backend
        out["dry_run"] = self.applier.dry_run
        return out

    def process(self, decisions: List[Dict[str, Any]],
                resolver: Optional[Resolver] = None) -> List[Dict[str, Any]]:
        """결정 배치를 승격하고 enforcement 로그에 적재(트랙 A emit 경로 재사용)."""
        promoted = [self.promote(d, resolver) for d in decisions]
        self.point._emit(promoted)
        return promoted
