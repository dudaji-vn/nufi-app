"""SLA·규정준수 리포트 데모용 픽스처 생성기 (CMP-150 C1).

결정론적·재현가능. 새 측정을 하지 않고 *이미 산출된 형태*의 측정 샘플과
감사/변경/flow 로그를 모사한다. 산출:

  samples/sla/sla_metrics.jsonl      — 주별 측정 샘플(대부분 충족 + 의도된 위반 1주)
  samples/sla/sla_metrics_multi.jsonl — 다테넌트 측정 샘플(테넌트별 충족/위반)
  samples/sla/policy_changes.jsonl   — 유효 해시체인 정책 변경 감사 로그
  samples/sla/audit_decisions.jsonl  — 차단/가명화 결정 감사(해시체인 부착)
  samples/sla/flow_bypass.jsonl      — flow tap(우회 1건 포함)

재실행: ``python3 samples/sla/_gen_fixtures.py``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from egress_audit.audit import GENESIS_HASH, _record_hash  # type: ignore
from enforcement.policy_ops import PolicyChangeAudit

# 고정 epoch_ms (2026-06, KST). 결정론.
_DAY = 86_400_000
_W = {
    "w1": 1_780_358_400_000,  # 2026-06-02 (ISO 2026-W23)
    "w2": 1_780_963_200_000,  # 2026-06-09 (ISO 2026-W24)
    "w3": 1_781_568_000_000,  # 2026-06-16 (ISO 2026-W25)
    "w4": 1_782_172_800_000,  # 2026-06-23 (ISO 2026-W26)
}


def gen_metrics() -> None:
    # 주별 측정 샘플. w3 에 recall 위반(0.86<0.90), w4 에 p95 위반(168>150)을 심는다.
    rows = [
        {"epoch_ms": _W["w1"], "pii_recall": 0.93, "latency_p95_ms": 118.0,
         "coverage_pct": 100.0, "backend": "int8", "host_class": "production",
         "note": "주간 벤치(goldset) + 온프렘 p95"},
        {"epoch_ms": _W["w1"] + _DAY, "pii_recall": 0.92, "latency_p95_ms": 126.0,
         "coverage_pct": 100.0, "backend": "int8", "note": "재측정"},
        {"epoch_ms": _W["w2"], "pii_recall": 0.91, "latency_p95_ms": 131.0,
         "coverage_pct": 99.6, "backend": "int8", "note": "주간 벤치"},
        {"epoch_ms": _W["w3"], "pii_recall": 0.86, "latency_p95_ms": 140.0,
         "coverage_pct": 99.2, "backend": "fp32", "note": "회귀 — recall 하락(위반)"},
        {"epoch_ms": _W["w4"], "pii_recall": 0.94, "latency_p95_ms": 168.0,
         "coverage_pct": 100.0, "backend": "int8", "host_class": "dev",
         "note": "dev 호스트 — p95 초과(위반)"},
    ]
    p = _HERE / "sla_metrics.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                 encoding="utf-8")
    print(f"  wrote {p} ({len(rows)} rows)")


def gen_metrics_multi() -> None:
    # 다테넌트 측정 샘플. acme=전 항목 충족, globex=recall 위반, initech=p95 위반.
    # 플릿 집계 표에 테넌트별 충족/위반 행이 섞여 나오도록 의도적으로 구성.
    rows = [
        {"tenant": "acme", "epoch_ms": _W["w3"], "pii_recall": 0.94,
         "latency_p95_ms": 120.0, "coverage_pct": 100.0, "backend": "int8",
         "note": "acme 주간 벤치 — 충족"},
        {"tenant": "acme", "epoch_ms": _W["w4"], "pii_recall": 0.93,
         "latency_p95_ms": 128.0, "coverage_pct": 99.9, "backend": "int8",
         "note": "acme 재측정 — 충족"},
        {"tenant": "globex", "epoch_ms": _W["w3"], "pii_recall": 0.87,
         "latency_p95_ms": 132.0, "coverage_pct": 99.5, "backend": "fp32",
         "note": "globex recall 하락 — 위반"},
        {"tenant": "initech", "epoch_ms": _W["w4"], "pii_recall": 0.92,
         "latency_p95_ms": 172.0, "coverage_pct": 100.0, "backend": "int8",
         "host_class": "dev", "note": "initech dev 호스트 p95 초과 — 위반"},
    ]
    p = _HERE / "sla_metrics_multi.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                 encoding="utf-8")
    print(f"  wrote {p} ({len(rows)} rows, 3 tenants)")


def gen_policy_changes() -> None:
    p = _HERE / "policy_changes.jsonl"
    if p.exists():
        p.unlink()
    pca = PolicyChangeAudit(path=str(p))
    pca.record(action="register", profile="strict-kr-pii", actor="alice",
               note="초기 strict 프로파일 등록")
    pca.record(action="snapshot", profile="strict-kr-pii", actor="alice",
               to_version=1, fingerprint="ab12cd34", note="v1 적재")
    pca.record(action="bind", profile="strict-kr-pii", actor="bob",
               route="tenant:acme", note="acme 테넌트 묶기")
    pca.record(action="snapshot", profile="strict-kr-pii", actor="alice",
               from_version=1, to_version=2, fingerprint="ef56ab78",
               note="규정 업데이트 반영")
    pca.record(action="rollback", profile="strict-kr-pii", actor="carol",
               from_version=2, to_version=1, note="오탐 급증 — 무재기동 되돌리기")
    print(f"  wrote {p} (chain ok={pca.verify_chain()['ok']})")


def _audit_rec(seq: int, prev: str, *, epoch_ms: int, outcome: str,
               action_counts: dict, findings: list) -> dict:
    rec = {
        "id": f"demo-sla-{seq:04d}",
        "epoch_ms": epoch_ms,
        "model": "claude-3-5-sonnet",
        "provider": "anthropic",
        "is_public": True,
        "outcome": outcome,
        "decision": {"blocked": outcome == "blocked",
                     "action_counts": action_counts,
                     "finding_count": len(findings)},
        "findings": findings,
    }
    rec["chain"] = {"seq": seq, "prev_hash": prev}
    rec["chain"]["hash"] = _record_hash(rec)
    return rec


def gen_audit_decisions() -> None:
    p = _HERE / "audit_decisions.jsonl"
    specs = [
        (_W["w1"], "blocked", {"pseudonymize": 1, "block": 1},
         [{"entity_type": "KR_PERSON", "score": 0.75, "source": "ner:gazetteer"},
          {"entity_type": "KR_RRN", "score": 0.99, "source": "regex+checksum"}]),
        (_W["w2"], "blocked", {"block": 1},
         [{"entity_type": "SECRET", "score": 0.98, "source": "regex"}]),
        (_W["w2"] + _DAY, "pseudonymized", {"pseudonymize": 2},
         [{"entity_type": "KR_PERSON", "score": 0.71, "source": "ner:gazetteer"},
          {"entity_type": "KR_PHONE", "score": 0.88, "source": "regex"}]),
        (_W["w3"], "allowed", {}, []),
        (_W["w4"], "blocked", {"pseudonymize": 1, "block": 1},
         [{"entity_type": "KR_RRN", "score": 0.99, "source": "regex+checksum"}]),
    ]
    prev = GENESIS_HASH
    lines = []
    for i, (em, outcome, ac, fnd) in enumerate(specs):
        rec = _audit_rec(i, prev, epoch_ms=em, outcome=outcome,
                         action_counts=ac, findings=fnd)
        prev = rec["chain"]["hash"]
        lines.append(json.dumps(rec, ensure_ascii=False))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {p} ({len(specs)} rows, chained)")


def gen_flows() -> None:
    p = _HERE / "flow_bypass.jsonl"
    rows = [
        {"flow_id": "flow-gw-1", "ts": "2026-06-02T09:00:01+0900", "epoch_ms": _W["w1"],
         "src_ip": "127.0.0.1", "dst_host": "api.anthropic.com", "process": "litellm",
         "via_gateway": True, "bypass": False, "severity": "info"},
        {"flow_id": "flow-gw-2", "ts": "2026-06-09T10:00:01+0900", "epoch_ms": _W["w2"],
         "src_ip": "127.0.0.1", "dst_host": "api.openai.com", "process": "litellm",
         "via_gateway": True, "bypass": False, "severity": "info"},
        {"flow_id": "flow-bypass-1", "ts": "2026-06-23T11:30:00+0900", "epoch_ms": _W["w4"],
         "src_ip": "127.0.0.1", "dst_host": "api.anthropic.com", "process": "rogue_script",
         "via_gateway": False, "bypass": True, "severity": "high"},
    ]
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                 encoding="utf-8")
    print(f"  wrote {p} ({len(rows)} rows, 1 bypass)")


if __name__ == "__main__":
    print("SLA/compliance 데모 픽스처 생성:")
    gen_metrics()
    gen_metrics_multi()
    gen_policy_changes()
    gen_audit_decisions()
    gen_flows()
    print("done.")
