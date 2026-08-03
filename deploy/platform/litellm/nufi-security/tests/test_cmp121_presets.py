"""CMP-121 인수 테스트 — 파이프라인 프리셋 + `nufi init` 템플릿.

수용 기준(binary):
  1) 3 프리셋 각각 유효 config 생성 + 게이트웨이(EgressGuard) 기동.
  2) 동일 입력에 프리셋별 결정 diff(strict 차단 vs audit-only 통과+로그).
  3) 잘못된 프리셋/오버라이드 → fail-closed 거부(파일 미생성).
  4) (문서는 docs/PRESETS.md — 별도 가드)

pytest 또는 `python3 tests/test_cmp121_presets.py` 로 실행.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from egress_audit import presets  # noqa: E402
from egress_audit.init_cli import main as init_main  # noqa: E402
from egress_audit.guard import EgressGuard  # noqa: E402
from egress_audit.pipeline import DetectionPipeline  # noqa: E402
from egress_audit.policy import PolicyEngine  # noqa: E402

ALL_PRESETS = ["strict-kr-pii", "audit-only", "pseudonymize-roundtrip"]

# 강한 PII·약한 PII·비밀이 모두 섞인 입력.
SAMPLE = ("홍길동 고객 전화 010-1234-5678, 이메일 hong@dudaji.com, "
          "AWS 키 AKIAIOSFODNN7EXAMPLE 포함.")
# PII 만(하드 비밀 없음) — 가역 가명화 통과 경로 시연용.
SAMPLE_PII_ONLY = "담당자 홍길동, 연락처 010-9876-5432, 메일 gildong@dudaji.com."


def _materialize_to(tmp_path: Path, name: str) -> Path:
    merged = presets.materialize(name)
    out = tmp_path / name
    presets.write_config(merged, out, name, force=True)
    return out


def _guard_for(out_dir: Path) -> EgressGuard:
    pe = PolicyEngine(policy_path=str(out_dir / "policy.yaml"))
    return EgressGuard(pipeline=DetectionPipeline(), policy=pe)


# ---------------------------------------------------------------- (1) 유효성
def test_all_presets_materialize_and_validate(tmp_path):
    assert sorted(presets.list_presets()) == sorted(ALL_PRESETS)
    for name in ALL_PRESETS:
        out = _materialize_to(tmp_path, name)
        # 3개 config 파일 모두 생성 + 다시 로드 가능(유효 YAML).
        for fname in presets.BASE_FILES.values():
            p = out / fname
            assert p.is_file(), f"{name}: {fname} 미생성"
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            assert isinstance(data, dict)
        # 게이트웨이 기동 가능.
        guard = _guard_for(out)
        res = guard.inspect("정상 텍스트")
        assert res is not None


# ---------------------------------------------------------------- (2) 결정 diff
def test_decision_diff_same_input(tmp_path):
    res = {}
    for name in ALL_PRESETS:
        out = _materialize_to(tmp_path, name)
        res[name] = _guard_for(out).inspect(SAMPLE)

    # strict-kr-pii: 차단.
    assert res["strict-kr-pii"].blocked is True
    # audit-only: 차단 안 함(통과) + finding 은 그대로 기록(관찰).
    assert res["audit-only"].blocked is False
    assert res["audit-only"].summary["finding_count"] > 0
    # audit-only 는 본문 무변형 통과(가시성 모드).
    assert res["audit-only"].transformed_text == SAMPLE
    # 모든 동작이 비차단(warn/allow).
    acts = res["audit-only"].summary["action_counts"]
    assert set(acts) <= {"warn", "allow"}, acts


def test_roundtrip_pseudonymizes_weak_pii(tmp_path):
    out = _materialize_to(tmp_path, "pseudonymize-roundtrip")
    r = _guard_for(out).inspect(SAMPLE_PII_ONLY)
    # 비밀 없는 PII 입력 → 차단되지 않고 가역 가명토큰으로 치환.
    assert r.blocked is False
    assert r.summary["action_counts"].get("pseudonymize", 0) >= 2
    # 원문 PII 가 변환본에 그대로 남지 않음.
    assert "홍길동" not in r.transformed_text
    assert "gildong@dudaji.com" not in r.transformed_text


def test_secret_always_blocked_in_roundtrip(tmp_path):
    out = _materialize_to(tmp_path, "pseudonymize-roundtrip")
    r = _guard_for(out).inspect(SAMPLE)  # AWS 키 포함
    # 가역 프리셋이라도 비밀은 가명화로 내보내지 않고 차단.
    assert r.blocked is True


# ---------------------------------------------------------------- (3) fail-closed
def test_unknown_preset_fail_closed(tmp_path):
    try:
        presets.materialize("does-not-exist")
        assert False, "PresetError 가 발생해야 함"
    except presets.PresetError:
        pass
    # CLI 도 비0 종료 + 파일 미생성.
    out = tmp_path / "cfg"
    rc = init_main(["does-not-exist", "--out", str(out)])
    assert rc == 2
    assert not out.exists()


def test_disallowed_override_fail_closed(tmp_path):
    try:
        presets.materialize("audit-only", overrides=["policy.entities.SECRET.action=allow"])
        assert False, "허용목록 밖 키는 거부되어야 함"
    except presets.PresetError:
        pass


def test_bad_override_value_fail_closed(tmp_path):
    try:
        presets.materialize("strict-kr-pii", overrides=["policy.enforcement.fail_mode=banana"])
        assert False, "무효 값은 거부되어야 함"
    except presets.PresetError:
        pass


def test_no_overwrite_without_force(tmp_path):
    out = tmp_path / "cfg"
    merged = presets.materialize("audit-only")
    presets.write_config(merged, out, "audit-only", force=False)  # 최초 OK
    try:
        presets.write_config(merged, out, "audit-only", force=False)  # 재실행 거부
        assert False, "기존 파일 존재 시 force 없으면 거부되어야 함"
    except presets.PresetError:
        pass
    # force 면 통과.
    presets.write_config(merged, out, "audit-only", force=True)


def test_allowed_override_applies(tmp_path):
    merged = presets.materialize(
        "pseudonymize-roundtrip", overrides=["policy.enforcement.fail_mode=closed"])
    assert merged["policy"]["enforcement"]["fail_mode"] == "closed"


# ---------------------------------------------------------------- 스탠드얼론
def _run_standalone() -> int:
    import tempfile
    failed = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        d = Path(tempfile.mkdtemp())
        try:
            t(d)
            print(f"  [PASS] {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  [FAIL] {t.__name__} — {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())
