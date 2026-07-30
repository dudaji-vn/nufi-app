"""CMP-245 — 한국 규제 증빙 팩 확장 검증.

개인정보보호법(PIPA)·신용정보법(CIA)·ISMS-P 커버리지 완성도를 검증한다.
카탈로그 항목 수·eval 규칙 정확성·프레임워크별 소계·report compliance 반영을 확인.
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

SDIR = _ROOT / "samples" / "sla"
AUDIT = str(SDIR / "audit_decisions.jsonl")
CHANGES = str(SDIR / "policy_changes.jsonl")
FLOW = str(SDIR / "flow_bypass.jsonl")


# --------------------------------------------------------------------------- #
# 카탈로그 구조 검증
# --------------------------------------------------------------------------- #
def _load_catalog():
    return rpt.load_catalog()


def test_catalog_version_1_2():
    cat = _load_catalog()
    assert cat["version"] == "1.2"


def test_catalog_has_all_frameworks():
    cat = _load_catalog()
    frameworks = {c["framework"] for c in cat["controls"]}
    assert frameworks == {"fsec-ai", "net-sep", "pipa", "cia", "isms-p"}


@pytest.mark.parametrize("fw,min_count", [
    ("pipa", 10),    # 6 direct + 2 partial + 2 oos = 10
    ("cia", 7),      # 4 direct + 1 partial + 2 oos = 7
    ("isms-p", 11),  # 5 direct + 2 partial + 4 oos = 11
])
def test_framework_item_count(fw, min_count):
    """각 규제 프레임워크의 최소 항목 수를 보장한다."""
    cat = _load_catalog()
    items = [c for c in cat["controls"] if c["framework"] == fw]
    assert len(items) >= min_count, (
        f"{fw}: expected >= {min_count} items, got {len(items)}")


def test_no_duplicate_ids():
    """카탈로그 내 id 중복이 없어야 한다."""
    cat = _load_catalog()
    ids = [c["id"] for c in cat["controls"]]
    assert len(ids) == len(set(ids)), f"Duplicate ids: {[x for x in ids if ids.count(x) > 1]}"


def test_direct_items_have_eval():
    """모든 direct 항목은 eval 규칙이 있어야 한다."""
    cat = _load_catalog()
    for c in cat["controls"]:
        if c["coverage_type"] == "direct":
            assert c.get("eval"), f"{c['id']}: direct item missing eval rule"


def test_partial_items_have_remediation():
    """모든 partial 항목은 remediation_ref 가 있어야 한다."""
    cat = _load_catalog()
    for c in cat["controls"]:
        if c["coverage_type"] == "partial":
            assert c.get("remediation_ref"), (
                f"{c['id']}: partial item missing remediation_ref")


# --------------------------------------------------------------------------- #
# eval 규칙 — direct 항목이 샘플 증빙으로 올바르게 판정되는지
# --------------------------------------------------------------------------- #
def _build_report():
    return rpt.build_compliance_report(
        audit_path=AUDIT, change_log_path=CHANGES, flow_paths=[FLOW])


@pytest.mark.parametrize("fw", ["pipa", "cia", "isms-p"])
def test_all_direct_items_met(fw):
    """샘플 증빙(audit/changes/flow)으로 모든 direct 항목이 met 판정된다."""
    rep = _build_report()
    cc = rep["control_coverage"]
    items = [i for i in cc["items"] if i["framework"] == fw
             and i["coverage_type"] == "direct"]
    assert items, f"No direct items for {fw}"
    for it in items:
        assert it["status"] == rpt.COV_MET, (
            f"{it['id']}: expected met, got {it['status']} "
            f"(evidence: {it.get('evidence')})")


@pytest.mark.parametrize("fw", ["pipa", "cia", "isms-p"])
def test_non_direct_items_na(fw):
    """partial/out_of_scope 항목은 n/a(자동판정 비대상) 상태여야 한다."""
    rep = _build_report()
    cc = rep["control_coverage"]
    items = [i for i in cc["items"] if i["framework"] == fw
             and i["coverage_type"] != "direct"]
    for it in items:
        assert it["status"] == rpt.COV_NA, (
            f"{it['id']}: expected n/a, got {it['status']}")


# --------------------------------------------------------------------------- #
# 프레임워크별 소계 (by_framework)
# --------------------------------------------------------------------------- #
def test_by_framework_summary_contains_all():
    """소계에 pipa/cia/isms-p 프레임워크가 모두 포함되어야 한다."""
    rep = _build_report()
    bf = rep["control_coverage"]["summary"]["by_framework"]
    for fw in ("pipa", "cia", "isms-p"):
        assert fw in bf, f"{fw} missing from by_framework summary"


def test_by_framework_counts_consistent():
    """프레임워크별 소계가 개별 항목과 일치해야 한다."""
    rep = _build_report()
    cc = rep["control_coverage"]
    bf = cc["summary"]["by_framework"]
    for fw in ("pipa", "cia", "isms-p"):
        items = [i for i in cc["items"] if i["framework"] == fw]
        r = bf[fw]
        assert r["direct"] + r["partial"] + r["out_of_scope"] == len(items), (
            f"{fw}: rollup sum {r} != item count {len(items)}")
        met = sum(1 for i in items
                  if i["coverage_type"] == "direct" and i["status"] == rpt.COV_MET)
        assert r["direct_met"] == met, f"{fw}: direct_met mismatch"


# --------------------------------------------------------------------------- #
# report compliance 렌더에 신규 규제가 반영되는지
# --------------------------------------------------------------------------- #
def test_compliance_md_contains_new_regulations():
    """Markdown 렌더 출력에 PIPA/CIA/ISMS-P 섹션이 존재해야 한다."""
    rep = _build_report()
    md = rpt.render_compliance_md(rep)
    assert "개인정보보호법 (pipa)" in md
    assert "신용정보법 (cia)" in md
    assert "ISMS-P 인증기준 (isms-p)" in md


def test_compliance_html_contains_new_regulations():
    """HTML 렌더 출력에 세 규제 프레임워크가 모두 포함되어야 한다."""
    rep = _build_report()
    html = rpt.render_compliance_html(rep)
    assert "개인정보보호법" in html
    assert "신용정보법" in html
    assert "ISMS-P" in html


def test_compliance_json_has_all_framework_items():
    """JSON 출력의 control_coverage.items 에 세 규제 항목이 모두 존재해야 한다."""
    rep = _build_report()
    obj = json.loads(rpt.render(rep, "json"))
    cc = obj["control_coverage"]
    frameworks = {i["framework"] for i in cc["items"]}
    assert {"pipa", "cia", "isms-p"}.issubset(frameworks)


# --------------------------------------------------------------------------- #
# 프레임워크 필터
# --------------------------------------------------------------------------- #
def test_framework_filter_isolates():
    """--framework 필터가 지정 규제 항목만 포함하는지 확인."""
    rep = rpt.build_compliance_report(
        audit_path=AUDIT, change_log_path=CHANGES,
        frameworks=["pipa"])
    cc = rep["control_coverage"]
    frameworks = {i["framework"] for i in cc["items"]}
    assert frameworks == {"pipa"}


# --------------------------------------------------------------------------- #
# CLI 종단
# --------------------------------------------------------------------------- #
def test_cli_compliance_with_framework_filter(capsys):
    from enforcement.cli import main as cli_main
    rc = cli_main(["report", "compliance", "--audit", AUDIT,
                   "--change-log", CHANGES, "--framework", "pipa",
                   "--format", "json"])
    assert rc == 0  # 무결성 정상 → exit 0
    out = capsys.readouterr().out
    obj = json.loads(out)
    items = obj["control_coverage"]["items"]
    assert all(i["framework"] == "pipa" for i in items)
    assert len(items) >= 10  # PIPA 최소 10항목


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
