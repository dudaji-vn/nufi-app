"""CMP-144 (v0.0.5 B1) 수용 기준 테스트 — 정책 운영 자동화(Policy Ops at Scale).

완료 기준(M1, 이슈):
  1. 프로파일 2개 동시 운영 + 경로별 묶기 1건 적용.
  2. 정책 버전 되돌리기 1건 **무재기동** 수행(가드 인스턴스 동일·generation 증가).
  3. 변경 감사 로그 1건 기록(누가·언제·무엇을) + 추가전용 해시 체인 변조탐지.
  4. 되돌리기 fail-closed(깨진 후보 거부 + 직전 룰셋·파일 원복) — CMP-124 계승.

NER 은 결정론적 gazetteer 기본(매니저). 분기 판정은 정규식 KR_PHONE 로 검증한다.
"""
import json
import shutil
from pathlib import Path

import pytest
import yaml

from enforcement.policy_ops import (
    ProfileRegistry, PolicyVersionStore, PolicyChangeAudit, PolicyOpsManager,
)

_REPO = Path(__file__).resolve().parent.parent
_CFG = _REPO / "config"

# 단일 KR_PHONE 만 트리거(인명 토큰 배제) — 전화 동작만으로 프로파일 분기를 본다.
PHONE_SAMPLE = "연락처 010-1234-5678 로 회신 바랍니다."


@pytest.fixture
def env(tmp_path) -> dict:
    """격리된 운영 상태(프로파일 정책 사본 + 버전/묶기/감사 경로)를 구성한다."""
    # 두 프로파일의 정책 파일을 tmp 로 복사(default=완화, strict=차단).
    default_pol = tmp_path / "default_policy.yaml"
    strict_pol = tmp_path / "strict_policy.yaml"
    shutil.copy(_CFG / "policy.yaml", default_pol)
    shutil.copy(_CFG / "profiles" / "strict" / "policy.yaml", strict_pol)

    routing = tmp_path / "routing.yaml"
    routing.write_text(yaml.safe_dump({
        "policy_default_profile": "default",
        "policy_profiles": {
            "default": {"policy": str(default_pol), "description": "base(완화)"},
            "strict": {"policy": str(strict_pol), "description": "strict(차단)"},
        },
        "policy_bindings": {},
    }, allow_unicode=True), encoding="utf-8")

    reg = ProfileRegistry(routing_path=str(routing),
                          bindings_overlay_path=str(tmp_path / "binds.yaml"))
    mgr = PolicyOpsManager(
        registry=reg,
        version_store=PolicyVersionStore(base_dir=str(tmp_path / "versions")),
        change_audit=PolicyChangeAudit(path=str(tmp_path / "changes.jsonl")),
    )
    return {"mgr": mgr, "reg": reg, "strict_pol": strict_pol, "tmp": tmp_path}


def test_two_profiles_concurrent_and_binding(env):
    """1. 두 프로파일 동시 운영 + 경로 묶기 1건 — 같은 입력에 다른 결정."""
    mgr = env["mgr"]
    # 묶기 전: 두 경로 모두 기본 프로파일 → 완화(차단 아님).
    assert mgr.registry.profile_for_route("tenant-acme") == "default"

    mgr.bind("tenant-acme", "strict", actor="ops@dudaji")
    assert mgr.registry.profile_for_route("tenant-acme") == "strict"
    # 묶기 영속 확인(런타임 오버레이) — 새 레지스트리도 같은 묶기를 본다.
    reg2 = ProfileRegistry(routing_path=str(mgr.registry.routing_path),
                           bindings_overlay_path=str(mgr.registry.bindings_overlay_path))
    assert reg2.profile_for_route("tenant-acme") == "strict"

    d_default = mgr.inspect("nufi-default", PHONE_SAMPLE).summary
    d_strict = mgr.inspect("tenant-acme", PHONE_SAMPLE).summary
    assert d_default["blocked"] is False           # 완화: 전화 가명화
    assert d_strict["blocked"] is True             # 차단: 전화 block
    # 두 프로파일 가드가 동시에 살아 있음(독립 인스턴스).
    assert mgr.guard("default") is not mgr.guard("strict")


def test_rollback_no_restart(env):
    """2. 버전 되돌리기 무재기동 — 동일 가드 인스턴스·generation 증가, 정책 복원."""
    mgr, strict_pol = env["mgr"], env["strict_pol"]
    mgr.bind("tenant-acme", "strict", actor="ops@dudaji")

    g = mgr.guard("strict")                          # 라이브 가드 1회 생성
    assert g.generation == 0
    assert mgr.inspect("tenant-acme", PHONE_SAMPLE).summary["blocked"] is True

    mgr.snapshot("strict", actor="ops@dudaji", note="v1 차단")   # v1

    # 정책 완화(전화 warn) 후 v2 적재 + 라이브 반영.
    cfg = yaml.safe_load(strict_pol.read_text(encoding="utf-8"))
    cfg["entities"]["KR_PHONE"] = {"action": "warn", "severity": "low"}
    strict_pol.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    mgr.snapshot("strict", actor="ops@dudaji", note="v2 완화")    # v2 (active)
    g.reload(mgr.registry.get("strict").paths)
    assert mgr.inspect("tenant-acme", PHONE_SAMPLE).summary["blocked"] is False
    gen_before = g.generation

    out = mgr.rollback("strict", actor="ops@dudaji")             # v2 → v1
    assert out.applied and out.from_version == 2 and out.to_version == 1
    assert out.generation_after == gen_before + 1                # 원자 스왑(무재기동)
    assert mgr.guard("strict") is g                              # 동일 인스턴스(재기동 없음)
    # 되돌린 정책이 라이브 결정에 반영 — 다시 차단.
    assert mgr.inspect("tenant-acme", PHONE_SAMPLE).summary["blocked"] is True
    assert yaml.safe_load(strict_pol.read_text())["entities"]["KR_PHONE"]["action"] == "block"


def test_rollback_fail_closed_on_broken_version(env):
    """4. 깨진 후보 버전으로의 되돌리기는 거부 + 직전 룰셋·파일 원복(fail-closed)."""
    mgr, strict_pol = env["mgr"], env["strict_pol"]
    g = mgr.guard("strict")
    mgr.snapshot("strict", actor="ops@dudaji", note="v1 정상")   # v1 정상

    # v2 = 깨진 정책(알 수 없는 동작) 적재.
    cfg = yaml.safe_load(strict_pol.read_text(encoding="utf-8"))
    cfg["entities"]["KR_PHONE"] = {"action": "NONSENSE", "severity": "low"}
    strict_pol.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    mgr.snapshot("strict", actor="ops@dudaji", note="v2 깨짐")    # v2 active(파일만)

    # 정상 v1 로 먼저 되돌려 라이브를 정상화(active=v1, gen+1).
    ok = mgr.rollback("strict", actor="ops@dudaji", to_version=1)
    assert ok.applied
    gen_after_ok = ok.generation_after
    live_before = strict_pol.read_text()

    # 이제 깨진 v2 로 되돌리기 시도 → fail-closed 거부.
    bad = mgr.rollback("strict", actor="ops@dudaji", to_version=2)
    assert bad.applied is False and bad.error
    assert bad.generation_after == gen_after_ok                  # 가드 유지(스왑 없음)
    assert strict_pol.read_text() == live_before                 # 라이브 파일 원복
    assert mgr.versions.active_version("strict") == 1            # active 원복
    actions = [r["action"] for r in mgr.audit.read_all()]
    assert "reload-reject" in actions


def test_change_audit_records_and_chain(env):
    """3. 변경 감사 — 누가·언제·무엇을 + 해시 체인 변조탐지."""
    mgr = env["mgr"]
    mgr.snapshot("strict", actor="alice", note="v1")
    mgr.bind("svc-billing", "strict", actor="bob")
    mgr.snapshot("strict", actor="alice", note="v2")
    mgr.rollback("strict", actor="carol")

    recs = mgr.audit.read_all()
    assert [r["action"] for r in recs] == ["snapshot", "bind", "snapshot", "rollback"]
    assert recs[1]["actor"] == "bob" and recs[1]["route"] == "svc-billing"
    assert recs[-1]["action"] == "rollback" and recs[-1]["actor"] == "carol"
    assert mgr.audit.verify_chain()["ok"] is True

    # 임의 행 변조 → 체인이 탐지.
    path = mgr.audit.path
    lines = path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[1]); rec["actor"] = "mallory"
    lines[1] = json.dumps(rec, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    verdict = mgr.audit.verify_chain()
    assert verdict["ok"] is False and verdict["broken_seq"] == 1
