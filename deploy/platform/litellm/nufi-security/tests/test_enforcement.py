"""Egress Enforcement 단위 테스트 (CMP-94 트랙 B · 스펙 §8.3 유닛/CI, root 불요).

골든 텍스트 비교(rule_builder) + 결정 로그 스키마 승격 + drop 피드백 파싱 +
수용 기준 A3·A6·A7·A8 의 root-불요 부분을 검증한다. A1·A2·A4·A5·A9 의 실집행은
``scripts/enforcement_integration.sh`` (root/netns) 가 담당.

실행: ``pytest tests/test_enforcement.py`` 또는 ``python3 tests/test_enforcement.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from capture.targets import Target, derive_targets
from enforcement.rule_builder import (
    EnforcementConfig,
    LOG_PREFIX,
    render_ruleset,
    render_panic,
    render_teardown,
    resolve_targets,
)
from enforcement.decision import EnforcedDecisionLog
from enforcement.applier import Applier
from enforcement.feedback import DropFeedback, parse_drop_line, parse_drops
from egress_audit.enforcement import EnforcementPoint, SIMULATED, ENFORCED

GOLDEN = ROOT / "tests" / "golden"

# 결정론적 픽스처 resolver(에어갭/CI: DNS 불요).
_FIXTURE_IPS = {
    "api.anthropic.com": ["203.0.113.10"],
    "api.openai.com": ["203.0.113.20"],
}
_resolver = lambda h: _FIXTURE_IPS.get(h, [])


def _cfg(**kw) -> EnforcementConfig:
    base = dict(fail_mode="open", gateway_uids=[1000],
                gateway_cgroups=["system.slice/nufi-gateway.service"])
    base.update(kw)
    return EnforcementConfig(**base)


def _targets():
    return derive_targets(str(ROOT / "config" / "routing.yaml"))


# ---- 골든 텍스트(A7 단일 출처, 결정성) ---------------------------------------
def test_golden_ruleset_matches():
    got = render_ruleset(_targets(), _cfg(), _resolver)
    expected = (GOLDEN / "egress_ruleset.nft").read_text(encoding="utf-8")
    assert got == expected, "rule_builder 출력이 골든과 다름 (정책/포맷 드리프트)"


def test_golden_panic_matches():
    got = render_panic(_targets(), _cfg(), _resolver)
    assert got == (GOLDEN / "egress_panic.nft").read_text(encoding="utf-8")


def test_golden_teardown_matches():
    assert render_teardown("nufi_egress") == (GOLDEN / "egress_teardown.nft").read_text(encoding="utf-8")


# ---- A6: 화이트리스트 선commit·원자성 ---------------------------------------
def test_whitelist_precedes_drop():
    txt = render_ruleset(_targets(), _cfg(), _resolver)
    accept_idx = txt.index("accept")
    drop_idx = txt.index("drop")
    assert accept_idx < drop_idx, "화이트리스트 accept 가 drop 보다 먼저여야 함(게이트웨이 자살 방지)"


def test_atomic_recreate_idiom():
    txt = render_ruleset(_targets(), _cfg(), _resolver)
    # add → delete → table {...} : 멱등 재생성 1 트랜잭션(부분 적용 불가).
    assert txt.index("add table inet nufi_egress") < txt.index("delete table inet nufi_egress")
    assert txt.index("delete table inet nufi_egress") < txt.index("table inet nufi_egress {")


def test_missing_gateway_selector_rejected():
    # uid/cgroup 둘 다 없으면 drop-only 가 게이트웨이까지 막으므로 거부(안전 불변식).
    try:
        render_ruleset(_targets(), _cfg(gateway_uids=[], gateway_cgroups=[]), _resolver)
        assert False, "화이트리스트 셀렉터 부재 시 ValueError 가 나야 함"
    except ValueError:
        pass


# ---- A7: 정책 단일 출처(routing.yaml 변경 → 규칙 반영) -----------------------
def test_single_source_new_backend(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        "version: 1\nbackends:\n"
        "  c:\n    provider: anthropic\n    egress_class: public\n    api_base: https://api.anthropic.com\n"
        "  g:\n    provider: google\n    egress_class: public\n    api_base: https://generativelanguage.googleapis.com\n",
        encoding="utf-8")
    targets = derive_targets(str(routing))
    res = lambda h: {**_FIXTURE_IPS,
                     "generativelanguage.googleapis.com": ["203.0.113.30"]}.get(h, [])
    txt = render_ruleset(targets, _cfg(), res)
    assert "203.0.113.30 . 443" in txt, "routing.yaml 신규 public 백엔드가 set 에 반영돼야 함"


def test_resolve_targets_dedup_and_v6():
    targets = [Target("api.anthropic.com", 443), Target("api.anthropic.com", 443)]
    res = lambda h: ["203.0.113.10", "2001:db8::1"]
    out = resolve_targets(targets, res)
    # 중복 제거 + v4/v6 분리.
    assert len(out) == 2
    assert any(r.ip == "2001:db8::1" for r in out)


# ---- 결정 로그 승격(스펙 §4.2, 스키마 보존) ----------------------------------
def test_decision_promotion_schema(tmp_path):
    # 트랙 A SIMULATED 결정 한 줄 생성.
    pt = EnforcementPoint(mode=SIMULATED, log_path=str(tmp_path / "sim.jsonl"))
    decision = pt.decide({"kind": "flow_bypass", "dst_host": "api.anthropic.com",
                          "dst_port": 443, "src_ip": "10.0.0.5", "process": "python"})
    assert decision["mode"] == SIMULATED and decision["applied"] is False

    # dry-run applier 로 ENFORCED 승격(실제 nft 미실행).
    applier = Applier(cfg=_cfg(), dry_run=True)
    log = EnforcedDecisionLog(applier=applier,
                              point=EnforcementPoint(mode=ENFORCED, log_path=str(tmp_path / "enf.jsonl")))
    promoted = log.promote(decision, resolver=_resolver)

    # 원본 스키마 보존 + mode 승격 + rule_id 기록.
    for k in ("action", "reason", "dest", "src", "flow_id"):
        assert k in promoted, f"트랙 A 필드 {k} 가 보존돼야 함"
    assert promoted["action"] == "BLOCK"
    assert promoted["mode"] == ENFORCED
    assert promoted["rule_id"] == "inet/nufi_egress/public_dst/203.0.113.10.443"
    assert promoted["applied"] is True   # dry-run 은 set add 를 성공 처리


def test_s4_enforced_demo_contract(tmp_path):
    """S4 ENFORCED 데모 계약(CMP-95): scripts/demo_bypass_enforcement.sh 가 적재하는 산출물 ↔
    scripts/demo_audit_separation.sh --enforce 검증기의 enf_ok 술어가 일치하는지 root 불요로 보장.

    하니스와 동일 경로(EnforcementPoint.decide → EnforcedDecisionLog.process →
    DropFeedback)로 enforcement.jsonl·blocked_attempts·s4_enforced.json 을 만들고,
    검증기의 ENFORCED 술어를 그대로 재현해 PASS 임을 확인한다(스크립트 간 드리프트 차단).
    """
    import json

    # 1) 우회 알림 → ENFORCED 결정 승격(하니스의 netns 내부 호출과 동일 API).
    enf_log = tmp_path / "enforcement.jsonl"
    ep = EnforcementPoint(mode=ENFORCED, log_path=str(enf_log))
    decision = ep.decide({"kind": "flow_bypass", "dst_host": "api.anthropic.com",
                          "dst_port": 443, "src_ip": "127.0.0.1",
                          "src_process": "rogue_sdk", "flow_id": "s4-enforced-bypass"})
    log = EnforcedDecisionLog(applier=Applier(cfg=_cfg(), dry_run=True), point=ep)
    log.process([decision], resolver=_resolver)      # enforcement.jsonl 로 emit
    enforce = [json.loads(l) for l in enf_log.read_text(encoding="utf-8").splitlines() if l.strip()]
    enf_block = [e for e in enforce if e.get("action") == "BLOCK"]

    # 2) 관측된 drop → blocked_attempts 증가(A3).
    fb = DropFeedback(counter_path=str(tmp_path / "blocked_attempts.json"),
                      flow_dir=str(tmp_path / "packets" / "public"))
    fb.ingest([_DROP_LINE])
    blocked = json.loads((tmp_path / "blocked_attempts.json").read_text(encoding="utf-8"))

    # 3) 하니스 요약(netns 프로브 결과).
    s4enf = {"host": "api.anthropic.com", "mode": "ENFORCED", "applied": True,
             "rule_id": enf_block[0]["rule_id"], "a1_pass": True, "a2_drop": True,
             "blocked_attempts": blocked["blocked_attempts"]}

    # 4) demo_audit_separation.sh --enforce 검증기의 enf_ok 술어(ENFORCED 분기)를 그대로 재현.
    enf_ok = (
        bool(enf_block)
        and all(e.get("mode") == "ENFORCED" for e in enf_block)
        and all(e.get("applied") is True for e in enf_block)
        and all(e.get("rule_id") for e in enf_block)
        and bool(s4enf) and s4enf.get("a2_drop") is True
        and s4enf.get("a1_pass") is True
        and int(blocked.get("blocked_attempts", 0)) >= 1
    )
    assert enf_ok, "ENFORCED 데모 계약 위반 — 하니스 산출물이 검증기 술어를 만족하지 않음"
    assert enf_block[0]["rule_id"] == "inet/nufi_egress/public_dst/203.0.113.10.443"


# ---- drop 피드백(A3 감사 증적·blocked_attempts) ------------------------------
_DROP_LINE = ("Jun 25 14:00:01 host kernel: nufi-egress-block "
              "IN= OUT=eth0 SRC=10.0.0.5 DST=203.0.113.10 LEN=60 "
              "PROTO=TCP SPT=44512 DPT=443 ")


def test_parse_drop_line():
    a = parse_drop_line(_DROP_LINE)
    assert a is not None
    assert a.src_ip == "10.0.0.5" and a.dst_ip == "203.0.113.10"
    assert a.dst_port == 443 and a.proto == "TCP"


def test_parse_ignores_unrelated():
    assert parse_drop_line("Jun 25 kernel: something else DPT=443") is None


def test_feedback_counter_and_reinject(tmp_path):
    fb = DropFeedback(counter_path=str(tmp_path / "c.json"),
                      flow_dir=str(tmp_path / "flow"))
    lines = [_DROP_LINE, _DROP_LINE, "unrelated line"]
    stats = fb.ingest(lines)
    assert stats["parsed"] == 2
    assert stats["blocked_attempts"] == 2   # A3: 누적 카운터
    assert stats["reinjected"] == 2
    # 누적 검증(2차 유입).
    stats2 = fb.ingest([_DROP_LINE])
    assert stats2["blocked_attempts"] == 3
    # 재유입 flow 레코드가 bypass+blocked high-sev.
    flows = list((tmp_path / "flow").glob("flow-*.jsonl"))
    assert flows, "flow 재유입 파일이 생성돼야 함"
    import json
    rec = json.loads(flows[0].read_text(encoding="utf-8").splitlines()[0])
    assert rec["bypass"] is True and rec["blocked"] is True and rec["severity"] == "high"


# ---- A8 킬스위치(render 레벨) + dry-run 안전 degrade --------------------------
def test_killswitch_teardown_text():
    txt = render_teardown("nufi_egress")
    assert "delete table inet nufi_egress" in txt
    assert "drop" not in txt and "accept" not in txt   # 규칙 0 = 전면 통과


def test_applier_dry_run_safe_without_root():
    # nft/권한 없으면 자동 dry-run — apply 가 예외 없이 텍스트만 반환.
    ap = Applier(cfg=_cfg(), dry_run=True)
    res = ap.apply(resolver=_resolver)
    assert res.ok and res.mode == "dry-run"
    assert "table inet nufi_egress" in res.rule_text


def test_fail_open_default_no_drop():
    # 적용 실패(_fail) → fail-open 폴백: 차단 규칙 미적용(관찰만). /proc 무관·결정적.
    ap = Applier(cfg=EnforcementConfig(fail_mode="open", gateway_uids=[1000]), dry_run=True)
    res = ap._fail("forced failure", _resolver)
    assert res.mode == "fail-open" and res.ok is False
    assert res.rule_text == ""   # 차단 규칙 미적용


def test_fail_closed_opt_in_panic():
    ap = Applier(cfg=EnforcementConfig(fail_mode="closed", gateway_uids=[1000]), dry_run=True)
    res = ap._fail("forced failure", _resolver)
    assert res.mode == "fail-closed" and res.ok is False
    # 패닉 셋 = 화이트리스트(skuid) accept 없는 전면 drop. ('policy accept' 는 체인 기본값).
    assert "drop" in res.rule_text
    assert "skuid" not in res.rule_text and "@public_dst accept" not in res.rule_text


def _run_all() -> int:
    import traceback
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    import tempfile
    for name, fn in fns:
        try:
            # tmp_path 픽스처 흉내.
            if "tmp_path" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            print(f"  [PASS] {name}")
        except Exception:
            failed += 1
            print(f"  [FAIL] {name}")
            traceback.print_exc()
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
