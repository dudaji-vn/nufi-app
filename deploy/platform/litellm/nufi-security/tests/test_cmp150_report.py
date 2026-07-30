"""CMP-150 — 규정준수 리포팅 검증.

기존 감사 로그·변경 감사를 규정준수 리포트로 묶고, 해시체인 무결성
게이트가 결정론적으로 동작하는지 확인한다. 새 측정·외부 호출 없음(픽스처만).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from enforcement import report as rpt  # noqa: E402
from enforcement.cli import main as cli_main  # noqa: E402

SDIR = _ROOT / "samples" / "sla"
AUDIT = str(SDIR / "audit_decisions.jsonl")
CHANGES = str(SDIR / "policy_changes.jsonl")
FLOW = str(SDIR / "flow_bypass.jsonl")


# --------------------------------------------------------------------------- #
# 규정준수 빌더
# --------------------------------------------------------------------------- #
def test_compliance_clean_chains_ok():
    rep = rpt.build_compliance_report(audit_path=AUDIT, change_log_path=CHANGES,
                                      flow_paths=[FLOW])
    assert rep["integrity_ok"] is True
    pa = rep["policy_change_audit"]
    assert pa["total"] == 5 and pa["chain"]["ok"] is True
    assert pa["by_action"]["snapshot"] == 2 and pa["by_action"]["rollback"] == 1
    d = rep["decisions"]
    assert d["by_outcome"]["blocked"] == 3
    assert d["action_counts"]["block"] == 3 and d["action_counts"]["pseudonymize"] == 4
    assert rep["bypass"]["bypass_count"] == 1


def test_compliance_detects_tampered_audit_chain(tmp_path):
    recs = [json.loads(l) for l in open(AUDIT, encoding="utf-8") if l.strip()]
    recs[1]["outcome"] = "allowed"  # 해시 미수정 변조
    tampered = tmp_path / "tampered.jsonl"
    tampered.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
                        encoding="utf-8")
    rep = rpt.build_compliance_report(audit_path=str(tampered), change_log_path=CHANGES)
    assert rep["integrity_ok"] is False
    assert rep["decisions"]["chain"]["ok"] is False


def test_compliance_renders_all_formats():
    rep = rpt.build_compliance_report(audit_path=AUDIT, change_log_path=CHANGES,
                                      flow_paths=[FLOW])
    md = rpt.render(rep, "md")
    assert "정책 변경 감사" in md and "우회 탐지 요약" in md and "무결성 정상" in md
    html = rpt.render(rep, "html")
    assert "<table>" in html
    obj = json.loads(rpt.render(rep, "json"))
    assert obj["kind"] == "compliance"


# --------------------------------------------------------------------------- #
# CLI 종단 — exit code 게이트
# --------------------------------------------------------------------------- #
def test_cli_compliance_clean_exit_0(capsys):
    rc = cli_main(["report", "compliance", "--audit", AUDIT,
                   "--change-log", CHANGES, "--format", "json"])
    assert rc == 0


def test_cli_compliance_tampered_exit_1(tmp_path, capsys):
    recs = [json.loads(l) for l in open(AUDIT, encoding="utf-8") if l.strip()]
    recs[0]["outcome"] = "pseudonymized"
    tampered = tmp_path / "t.jsonl"
    tampered.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
                        encoding="utf-8")
    rc = cli_main(["report", "compliance", "--audit", str(tampered),
                   "--change-log", CHANGES, "--format", "json"])
    assert rc == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
