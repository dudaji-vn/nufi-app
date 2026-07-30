"""CMP-124 수용 기준 테스트 — 무재기동 핫리로드 / 드라이런 diff / fail-closed /
retain_raw·키회전 오설정 방지.

수용 기준(이슈):
  1. 재기동 없이 룰 1건 변경 적용(드라이런 diff 증거).
  2. 잘못된 룰 fail-closed 거부 + 직전 유지.
  3. retain_raw 보존/삭제 + 키 회전 절차 문서화, 오설정 방지 검증 1건.

NER 은 끄고(rule-only) 결정성을 보장한다 — 핫리로드 대상은 정규식/사전/EDM/정책.
"""
import shutil
from pathlib import Path

import pytest

from egress_audit import (
    DetectionPipeline, PolicyEngine, EgressGuard,
    ReloadableGuard, RuleSetPaths, RuleValidationError, validate_ruleset, load_kek,
)

_REPO = Path(__file__).resolve().parent.parent
_CFG = _REPO / "config"


def _guard_no_ner() -> EgressGuard:
    pipe = DetectionPipeline(enable_ner=False)
    return EgressGuard(pipeline=pipe, policy=PolicyEngine())


def _paths(cfg_dir: Path) -> RuleSetPaths:
    return RuleSetPaths(
        patterns_path=str(cfg_dir / "patterns.yaml"),
        policy_path=str(cfg_dir / "policy.yaml"),
        confidential_path=str(cfg_dir / "confidential.yaml"),
        edm_index_path=str(cfg_dir / "edm" / "index.json"),
    )


@pytest.fixture
def cfg_copy(tmp_path) -> Path:
    """config 디렉터리 복사본(원본 불변 — 테스트가 룰을 변형)."""
    dst = tmp_path / "config"
    shutil.copytree(_CFG, dst)
    return dst


# ── 수용 기준 1: 재기동 없이 룰 1건 변경 적용 + 드라이런 diff ──────────────────
def test_hot_reload_applies_single_rule_change_without_restart(cfg_copy):
    rg = ReloadableGuard(guard=_guard_no_ner(), paths=_paths(cfg_copy))
    text = "담당자 연락처 010-1234-5678 입니다."  # KR_PHONE → 기본 pseudonymize(비차단)

    before = rg.inspect(text)
    assert before.blocked is False
    gen0 = rg.generation

    # policy.yaml 한 줄 변경: KR_PHONE pseudonymize → block (재기동 없음, 같은 프로세스)
    pol = cfg_copy / "policy.yaml"
    pol.write_text(
        pol.read_text(encoding="utf-8").replace(
            "KR_PHONE:         { action: pseudonymize, severity: medium } # 전화번호",
            "KR_PHONE:         { action: block, severity: medium } # 전화번호"),
        encoding="utf-8")

    # 드라이런: 적용 전 결정 diff 가 증거로 산출되어야 한다.
    diff = rg.dry_run()
    assert diff.valid is True
    assert diff.totals["changed"] >= 1

    res = rg.reload()
    assert res.applied is True
    assert res.generation == gen0 + 1

    after = rg.inspect(text)
    assert after.blocked is True            # 무재기동 적용 확인
    assert rg.active_fingerprint == res.fingerprint


# ── 수용 기준 2: 잘못된 룰 fail-closed 거부 + 직전 유지 ────────────────────────
def test_invalid_regex_fail_closed_keeps_previous(cfg_copy):
    rg = ReloadableGuard(guard=_guard_no_ner(), paths=_paths(cfg_copy))
    gen0, fp0 = rg.generation, rg.active_fingerprint

    pat = cfg_copy / "patterns.yaml"
    # 컴파일 불가능한 정규식 주입(짝 안 맞는 괄호)
    pat.write_text(pat.read_text(encoding="utf-8") +
                   '\n  - { name: BROKEN, regex: "(unclosed" }\n', encoding="utf-8")

    res = rg.reload()
    assert res.applied is False             # fail-closed 거부
    assert rg.generation == gen0            # 직전 룰셋 유지
    assert rg.active_fingerprint == fp0
    assert rg.last_error and "빌드 실패" in rg.last_error

    # 거부 후에도 라이브 결정 경로는 직전 룰로 정상 동작(SECRET → block 유지)
    assert rg.inspect(
        "배포키 AKIAIOSFODNN7EXAMPLE wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY").blocked is True


def test_unknown_policy_action_rejected(cfg_copy):
    pol = cfg_copy / "policy.yaml"
    pol.write_text(
        pol.read_text(encoding="utf-8").replace(
            "KR_RRN:           { action: block, severity: critical }",
            "KR_RRN:           { action: nuke, severity: critical }"),
        encoding="utf-8")
    with pytest.raises(RuleValidationError) as ei:
        validate_ruleset(_paths(cfg_copy))
    assert "알 수 없는 정책 동작" in str(ei.value)


def test_dry_run_invalid_does_not_mutate(cfg_copy):
    rg = ReloadableGuard(guard=_guard_no_ner(), paths=_paths(cfg_copy))
    pol = cfg_copy / "policy.yaml"
    pol.write_text(pol.read_text(encoding="utf-8").replace(
        "default_action: warn", "default_action: explode"), encoding="utf-8")
    diff = rg.dry_run()
    assert diff.valid is False
    assert rg.generation == 0               # 드라이런은 절대 적용하지 않음


# ── 수용 기준 3: retain_raw / Vault 키 회전 오설정 방지 검증 1건 ───────────────
def test_misconfig_prevention_retain_raw_and_kek_rotation():
    """오설정 방지: (a) retain_raw 정책 게이트, (b) Vault KEK 형식 검증.

    docs/SECURITY_RETAIN_RAW_KEYROTATION.md 의 보안 불변식을 코드로 고정한다.
    """
    # (a) retain_raw 는 명시적 옵트인이어야 한다(기본 보존 금지). content_dump 의
    #     기본 body_retained 는 "sanitized" — 즉 retain_raw 미설정 시 원문 미보존.
    from capture.content_dump import ContentDumpWriter
    import inspect
    sig = inspect.signature(ContentDumpWriter.dump)
    assert sig.parameters["body_retained"].default == "sanitized", \
        "retain_raw 기본값이 원문 보존이면 안 됨(오설정)"

    # (b) Vault KEK: 32바이트(AES-256) 가 아니면 거부되어야 한다(평문/약키 폴백 금지).
    good = load_kek("0" * 64)               # hex64 = 32B
    assert len(good) == 32
    with pytest.raises(ValueError):
        load_kek("dG9vc2hvcnQ=")            # base64 "tooshort" → 8B, 거부
    with pytest.raises(ValueError):
        load_kek("aa" * 16)                 # hex32 = 16B(AES-128), 거부


def test_validate_ruleset_baseline_passes():
    """기준 config 는 항상 검증을 통과해야 한다(회귀 가드)."""
    report = validate_ruleset(RuleSetPaths.default())
    assert report.entity_count > 0
    assert report.fingerprint
