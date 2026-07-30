"""점검항목 커버리지(control coverage) 검증 — v0.0.9 P0 컴플라이언스 매핑 리포트.

카탈로그(금융보안원 안내서·망분리 평가기준 ↔ NuFi 통제)와 기존 compliance
리포트 증빙을 결합해, direct 항목 status 가 **양방향(충족/미충족)** 으로 결정론적
자동판정되고, md/html/json 롤업이 정확하며, 무결성 종료코드가 회귀하지 않는지
확인한다. 새 측정·외부 호출 없음(픽스처만).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

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
# 카탈로그
# --------------------------------------------------------------------------- #
# 한국 규제 증빙 팩 확장 후 총계(fsec-ai + net-sep + pipa + cia + isms-p).
# v1.2: C-11 partial→direct 승격, CIA-19 → CIA-19-INTEG(direct)+CIA-19-IDS(partial) 분리,
#        PIPA-15/34·CIA-33-2/20-2·ISMS-2.5/2.7/3.5 신규 추가.
EXPECT_DIRECT = 25
EXPECT_PARTIAL = 10
EXPECT_OOS = 13


def test_catalog_has_all_direct_and_partial():
    cat = rpt.load_catalog()
    by_type = {}
    for c in cat["controls"]:
        by_type.setdefault(c["coverage_type"], []).append(c["id"])
    # 한국 규제 증빙 팩: direct 23 · partial 9 · out_of_scope 8.
    assert len(by_type[rpt.COV_DIRECT]) == EXPECT_DIRECT
    assert len(by_type[rpt.COV_PARTIAL]) == EXPECT_PARTIAL
    assert len(by_type[rpt.COV_OUT_OF_SCOPE]) == EXPECT_OOS
    # 핵심 direct 항목이 카탈로그에 존재(매핑표 전사).
    direct = set(by_type[rpt.COV_DIRECT])
    assert {"C-07", "C-26", "C-24", "M-1.2", "M-2.4", "M-2.5", "M-3.1", "M-2.7"} <= direct
    # 모든 direct 항목은 eval 규칙을 가진다(자동판정 대상).
    for c in cat["controls"]:
        if c["coverage_type"] == rpt.COV_DIRECT:
            assert c.get("eval"), f"{c['id']} direct 인데 eval 규칙 없음"


def test_every_control_has_framework():
    """하위호환·확장 불변: 모든 항목은 알려진 framework 에 속한다."""
    cat = rpt.load_catalog()
    known = set(rpt.FRAMEWORK_META)
    for c in cat["controls"]:
        assert c.get("framework") in known, f"{c['id']} framework 누락/미지정"


def test_maps_to_references_existing_control():
    """maps_to 교차참조는 카탈로그에 실재하는 원천 통제를 가리킨다."""
    cat = rpt.load_catalog()
    ids = {c["id"] for c in cat["controls"]}
    for c in cat["controls"]:
        mt = c.get("maps_to")
        if mt is not None:
            assert mt in ids, f"{c['id']} maps_to {mt} 미존재"
    # 신규 규제 행이 기존 통제를 재사용함을 명시(대표 케이스).
    by_id = {c["id"]: c for c in cat["controls"]}
    assert by_id["PIPA-23"]["maps_to"] == "C-07"
    assert by_id["CIA-XBORDER"]["maps_to"] == "C-26"
    assert by_id["ISMS-2.9.4"]["maps_to"] == "M-1.2"


# --------------------------------------------------------------------------- #
# direct 자동판정 — 충족 방향(실 픽스처)
# --------------------------------------------------------------------------- #
def test_direct_met_from_real_evidence():
    rep = rpt.build_compliance_report(audit_path=AUDIT, change_log_path=CHANGES,
                                      flow_paths=[FLOW])
    cc = rep["control_coverage"]
    s = cc["summary"]
    # 동봉 픽스처: 차단/가명화 결정 + 무결 체인 → 모든 direct 충족.
    assert s["direct"] == EXPECT_DIRECT and s["direct_met"] == EXPECT_DIRECT \
        and s["direct_unmet"] == 0
    items = {i["id"]: i for i in cc["items"]}
    assert items["C-07"]["status"] == rpt.COV_MET
    assert items["M-2.7"]["status"] == rpt.COV_MET
    # 신규 한국 규제 direct 항목도 동일 증빙으로 자동 충족판정.
    for cid in ("PIPA-23", "PIPA-24", "PIPA-28-2", "CIA-PII", "ISMS-3.3"):
        assert items[cid]["status"] == rpt.COV_MET, cid
    # 충족 항목엔 증빙 문자열이 채워진다.
    assert items["C-26"]["evidence"] and "block=" in items["C-26"]["evidence"]
    # 신규 direct 항목 증빙출처 표기(eval 경로).
    assert "pseudonymize=" in items["PIPA-28-2"]["evidence"]
    assert items["PIPA-29-INTEG"]["evidence"] == "integrity_ok=True"
    # v1.2 승격 항목: C-11 모니터링·보고(partial→direct), CIA-19-INTEG 위변조방지.
    assert items["C-11"]["status"] == rpt.COV_MET
    assert "decisions.total=" in items["C-11"]["evidence"]
    assert "policy_change_audit.records" in items["C-11"]["evidence"]
    assert items["CIA-19-INTEG"]["status"] == rpt.COV_MET
    assert items["CIA-19-INTEG"]["evidence"] == "integrity_ok=True"
    # 증빙 출처(evidence_source) 필드 — 충족 direct 항목에 포함.
    ev_src = items["C-07"]["evidence_source"]
    assert ev_src is not None
    assert "audit_log" in ev_src and ev_src["audit_log"]["records"] > 0
    # partial/OOS 항목엔 evidence_source 없음.
    assert items["CIA-19-IDS"]["evidence_source"] is None


# --------------------------------------------------------------------------- #
# direct 자동판정 — 미충족 방향(증빙 부재 합성 모델)
# --------------------------------------------------------------------------- #
def _empty_report() -> dict:
    """증빙이 비어있는 compliance 리포트 모델(직접 항목이 모두 미충족이어야 함)."""
    return {
        "integrity_ok": False,
        "decisions": {"total": 0, "action_counts": {},
                      "blocked_by_entity": {}, "chain": {"ok": None}},
        "policy_change_audit": {"log": None, "total": 0, "records": [],
                                "chain": {"ok": False}},
    }


def test_direct_unmet_when_no_evidence():
    cc = rpt.build_control_coverage(_empty_report())
    s = cc["summary"]
    assert s["direct"] == EXPECT_DIRECT and s["direct_met"] == 0 \
        and s["direct_unmet"] == EXPECT_DIRECT
    items = {i["id"]: i for i in cc["items"]}
    # 기존 + 신규 한국 규제 direct 항목 모두 증빙 부재 시 미충족.
    for cid in ("C-07", "C-11", "M-2.7", "PIPA-23", "PIPA-29-LOG",
                "CIA-20", "CIA-19-INTEG", "ISMS-3.1"):
        assert items[cid]["status"] == rpt.COV_UNMET, cid


def test_partial_and_oos_are_static_na():
    cc = rpt.build_control_coverage(_empty_report())
    items = {i["id"]: i for i in cc["items"]}
    # partial/out_of_scope 는 증빙과 무관하게 정적 n/a(자동판정 비대상).
    assert items["C-12"]["status"] == rpt.COV_NA
    assert items["C-12"]["remediation_ref"]   # 보강 트랙 링크 존재
    assert items["CIA-19-IDS"]["status"] == rpt.COV_NA
    assert items["OOS-SBOM"]["status"] == rpt.COV_NA


# --------------------------------------------------------------------------- #
# 롤업·렌더 3종
# --------------------------------------------------------------------------- #
def test_rollup_counts_consistent():
    cc = rpt.build_control_coverage(rpt.build_compliance_report(
        audit_path=AUDIT, change_log_path=CHANGES))
    s = cc["summary"]
    n_direct = sum(1 for i in cc["items"] if i["coverage_type"] == rpt.COV_DIRECT)
    assert s["direct"] == n_direct
    assert s["direct_met"] + s["direct_unmet"] == s["direct"]
    assert len(cc["items"]) == s["direct"] + s["partial"] + s["out_of_scope"]


def test_renderers_include_coverage_section():
    rep = rpt.build_compliance_report(audit_path=AUDIT, change_log_path=CHANGES)
    md = rpt.render(rep, "md")
    html = rpt.render(rep, "html")
    js = json.loads(rpt.render(rep, "json"))
    assert "점검항목 커버리지" in md and f"직접 {EXPECT_DIRECT}" in md
    assert "C-07" in md and "PIPA-23" in md
    # 프레임워크별 소계 + 표시명 + maps_to 교차참조.
    assert "프레임워크별 소계" in md and "개인정보보호법" in md
    assert "(←C-07)" in md
    assert "점검항목 커버리지" in html and "<table>" in html
    assert "프레임워크별 소계" in html and "신용정보법" in html
    assert "control_coverage" in js
    assert js["control_coverage"]["summary"]["direct"] == EXPECT_DIRECT
    assert js["control_coverage"]["summary"]["by_framework"]["pipa"]["direct"] == 6


# --------------------------------------------------------------------------- #
# 프레임워크 롤업·필터 — 한국 규제 증빙 팩
# --------------------------------------------------------------------------- #
def test_by_framework_rollup_counts():
    cc = rpt.build_control_coverage(rpt.build_compliance_report(
        audit_path=AUDIT, change_log_path=CHANGES, flow_paths=[FLOW]))
    bf = cc["summary"]["by_framework"]
    assert bf["fsec-ai"]["direct"] == 4 and bf["fsec-ai"]["partial"] == 5 \
        and bf["fsec-ai"]["out_of_scope"] == 5
    assert bf["net-sep"]["direct"] == 5
    assert bf["pipa"]["direct"] == 6 and bf["pipa"]["partial"] == 2 \
        and bf["pipa"]["out_of_scope"] == 2
    assert bf["cia"]["direct"] == 5 and bf["cia"]["partial"] == 1 \
        and bf["cia"]["out_of_scope"] == 2
    assert bf["isms-p"]["direct"] == 5 and bf["isms-p"]["partial"] == 2 \
        and bf["isms-p"]["out_of_scope"] == 4
    # 소계 합 == 전체 롤업(불변).
    s = cc["summary"]
    for key in ("direct", "partial", "out_of_scope", "direct_met", "direct_unmet"):
        assert sum(r[key] for r in bf.values()) == s[key]


def test_framework_filter_subsets_catalog():
    full = rpt.build_control_coverage(rpt.build_compliance_report(
        audit_path=AUDIT, change_log_path=CHANGES))
    cc = rpt.build_control_coverage(rpt.build_compliance_report(
        audit_path=AUDIT, change_log_path=CHANGES), frameworks=["pipa", "cia"])
    # 필터된 집합만 — 다른 규제 행은 없다.
    fws = {i["framework"] for i in cc["items"]}
    assert fws == {"pipa", "cia"}
    assert cc["frameworks_filter"] == ["cia", "pipa"]
    # 롤업도 필터 기준(pipa direct 6 + cia direct 5 = 11).
    assert cc["summary"]["direct"] == 11
    assert set(cc["summary"]["by_framework"]) == {"pipa", "cia"}
    # 전체보다 항목 수가 적다(부분집합).
    assert len(cc["items"]) < len(full["items"])


def test_framework_filter_via_cli_exit_code_unchanged(tmp_path):
    """--framework 필터는 정보성 — 종료코드(무결성 게이트)에 영향 없음."""
    rc = cli_main(["report", "compliance", "--audit", AUDIT,
                   "--change-log", CHANGES, "--framework", "pipa",
                   "--format", "json", "--out", str(tmp_path / "f.json")])
    assert rc == 0
    js = json.loads((tmp_path / "f.json").read_text(encoding="utf-8"))
    assert js["control_coverage"]["frameworks_filter"] == ["pipa"]
    assert {i["framework"] for i in js["control_coverage"]["items"]} == {"pipa"}


# --------------------------------------------------------------------------- #
# 종료코드 회귀 — 커버리지는 정보성(무결성 게이트만 종료코드 결정)
# --------------------------------------------------------------------------- #
def test_exit_code_unchanged_by_coverage(tmp_path, capsys):
    # 정상 감사 로그 → 미충족 direct 가 있어도 무결성 정상이면 exit 0.
    rc = cli_main(["report", "compliance", "--audit", AUDIT,
                   "--change-log", CHANGES, "--format", "json"])
    assert rc == 0


def test_tampered_audit_still_exits_1(tmp_path):
    recs = [json.loads(l) for l in open(AUDIT, encoding="utf-8") if l.strip()]
    recs[2]["outcome"] = "allowed"   # 한 행 변조 → 체인 깨짐
    tampered = tmp_path / "tampered.jsonl"
    tampered.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs),
                        encoding="utf-8")
    rc = cli_main(["report", "compliance", "--audit", str(tampered),
                   "--change-log", CHANGES, "--format", "json"])
    assert rc == 1


def test_no_controls_suppresses_section():
    rep = rpt.build_compliance_report(audit_path=AUDIT, change_log_path=CHANGES,
                                      controls=False)
    assert "control_coverage" not in rep
    assert "점검항목 커버리지" not in rpt.render(rep, "md")
