"""우회 차단 제어점 (Enforcement control point).

CMP-85 S4 강화 (CMP-92 CPO 확정, 보드 입력 2026-06-24):
- **트랙 A (CMP-89, 본 모듈):** flow tap 은 **관찰 전용**(연결 메타데이터; TLS 본문·
  인라인 drop 불가). 따라서 게이트웨이 우회(bypass) high-sev 알림에 대해 enforcement
  **결정**(`action=BLOCK`)을 내리고, "여기서 차단 규칙이 적용된다"는 **차단 제어점**을
  명시적으로 시연한다. PoC 데모는 실제 패킷을 drop 하지 않으며 `mode=SIMULATED` 로
  정직하게 라벨한다(--simulate·root 불요 원칙).
- **트랙 B (CMP-93, 신규 빌드):** 실제 egress drop(`mode=ENFORCED`)은 P0~P2 감사 범위를
  넘는 신규 enforcement 기능 — nftables/iptables egress 허용목록(MVP 권고)·투명 프록시·
  eBPF. 별도 설계·빌드 이슈 + **신규 CMP-58 승인** 필요. 본 모듈의 ``apply()`` 가 그
  연결 seam 이다(ENFORCED 는 아직 NotImplementedError).

온프렘 로컬 파일(NFR1). 외부 호출 0.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent

SIMULATED = "SIMULATED"
ENFORCED = "ENFORCED"

# 차단 제어점(트랙 B 에서 실제 구현). 권고 우선순위는 SPEC §P3.
CONTROL_POINT = "egress_firewall(nftables allowlist) [stub — track-B]"


class EnforcementPoint:
    """우회 알림 → 차단 결정 + 제어점 스텁.

    mode=SIMULATED(기본): 결정만 기록(실제 drop 없음). mode=ENFORCED: 미구현(트랙 B).
    """

    def __init__(self, mode: str = SIMULATED, log_path: Optional[str] = None):
        if mode not in (SIMULATED, ENFORCED):
            raise ValueError(f"mode must be SIMULATED|ENFORCED, got {mode!r}")
        self.mode = mode
        raw = log_path or os.environ.get("EGRESS_ENFORCEMENT_LOG") or "logs/enforcement.jsonl"
        p = Path(raw)
        self.log_path = p if p.is_absolute() else (_ROOT / p)

    # ---- 결정: 우회 레코드(알림/ finding/flow) → BLOCK 결정 -----------------
    def decide(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        """게이트웨이 우회 1건에 대한 차단 결정을 만든다(실제 적용 전)."""
        span = {}
        spans = rec.get("spans")
        if isinstance(spans, list) and spans:
            span = spans[0] or {}
        dest = (span.get("dst") or rec.get("dst_host") or rec.get("dst_ip") or "unknown")
        dest_port = span.get("dst_port") or rec.get("dst_port") or 443
        src = (span.get("src") or rec.get("src_host") or rec.get("src_ip") or "unknown")
        src_proc = (span.get("src_process") or rec.get("process")
                    or rec.get("src_process"))
        src_pid = span.get("src_pid") or rec.get("pid")
        flow_id = rec.get("flow_id") or rec.get("source_id") or str(uuid.uuid4())
        now_ms = int(time.time() * 1000)
        return {
            "enforce_id": str(uuid.uuid4()),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "epoch_ms": now_ms,
            "action": "BLOCK",
            "reason": "gateway_bypass",          # 정규 파이프라인 미경유 egress
            "dest": dest,
            "dest_port": int(dest_port),
            "src": src,
            "src_process": src_proc,
            "src_pid": src_pid,
            "flow_id": flow_id,
            "mode": self.mode,                   # SIMULATED(데모) | ENFORCED(트랙 B)
            "control_point": CONTROL_POINT,      # 어디서 drop 되는지(제어점)
            "applied": False,                    # decide 단계 = 미적용
            "followup": "track B: mode=ENFORCED, nftables MVP (미구현)",
        }

    # ---- 적용: 차단 제어점 스텁 ------------------------------------------
    def apply(self, decision: Dict[str, Any]) -> bool:
        """차단 제어점. SIMULATED=실제 drop 없음(결정만), ENFORCED=미구현(트랙 B).

        반환: 실제 패킷이 drop 되었는지(applied). SIMULATED 는 항상 False.
        """
        if self.mode == ENFORCED:
            # 트랙 B(CMP-93) 연결 seam: nftables/proxy/eBPF egress drop.
            raise NotImplementedError(
                "ENFORCED egress drop 은 트랙 B(nftables MVP) — 미구현")
        decision["applied"] = False              # 관찰 전용: 실제 drop 안 함
        return False

    # ---- 우회 알림 배치 처리 → 결정 emit ---------------------------------
    def process_alerts(self, alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """high-sev 우회 알림(kind=flow_bypass)만 골라 차단 결정을 만들고 적재."""
        bypass = [a for a in alerts if a.get("kind") == "flow_bypass"]
        decisions: List[Dict[str, Any]] = []
        for a in bypass:
            d = self.decide(a)
            self.apply(d)                        # 제어점 통과(SIMULATED=no-op)
            decisions.append(d)
        self._emit(decisions)
        return decisions

    def _emit(self, decisions: List[Dict[str, Any]]) -> None:
        if not decisions:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            for d in decisions:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def read_all(self) -> List[Dict[str, Any]]:
        if not self.log_path.exists():
            return []
        return [json.loads(ln) for ln in self.log_path.read_text(encoding="utf-8").splitlines()
                if ln.strip()]


def _load_jsonl(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="우회 차단 제어점")
    ap.add_argument("--alerts", required=True, help="우회 알림 jsonl(봇 alerts.jsonl)")
    ap.add_argument("--out", default=None, help="enforcement 결정 출력 jsonl")
    ap.add_argument("--mode", default=SIMULATED, choices=[SIMULATED, ENFORCED])
    args = ap.parse_args(argv)

    ep = EnforcementPoint(mode=args.mode, log_path=args.out)
    decisions = ep.process_alerts(_load_jsonl(args.alerts))
    for d in decisions:
        print(f"enforce: action={d['action']} dest={d['dest']}:{d['dest_port']} "
              f"src={d['src']}({d.get('src_process')}) mode={d['mode']} "
              f"applied={d['applied']} control_point={d['control_point']}")
    print(f"[enforcement] {len(decisions)} 차단 결정 → {ep.log_path} "
          f"(mode={args.mode}, 실제 drop={'예' if args.mode == ENFORCED else '아니오(SIMULATED)'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
