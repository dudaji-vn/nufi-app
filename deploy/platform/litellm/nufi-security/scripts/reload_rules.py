#!/usr/bin/env python3
"""룰 핫리로드 운영 CLI (CMP-124 · v0.0.2 M2·D2).

서브커맨드
  validate  후보 룰셋 검증(정규식/YAML/정책 액션/스모크). 통과 시 exit 0, 실패 시 1.
  dry-run   현재 대비 후보 룰셋의 **결정 diff** 산출(적용하지 않음). exit 0/1(검증)/3(diff 있음, --fail-on-change).
  apply     로컬 ReloadableGuard 인스턴스로 검증→스왑(데모/검증용; 라이브 게이트웨이는 SIGHUP 사용).

라이브 게이트웨이에서의 실제 무재기동 적용은 ``kill -HUP <gateway_pid>`` 로 한다
(ReloadableGuard.install_sighup_handler 등록 시). 검증 실패 시 직전 룰셋 유지(fail-closed).

스코프: 운영/설정 — 신규 차단 규칙/게이트웨이 결정 로직 변경 없음.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress_audit.reload import (  # noqa: E402
    RuleSetPaths, RuleValidationError, validate_ruleset, ReloadableGuard,
)


def _paths_from_args(a) -> RuleSetPaths:
    d = RuleSetPaths.default()
    return RuleSetPaths(
        patterns_path=a.patterns or d.patterns_path,
        policy_path=a.policy or d.policy_path,
        confidential_path=a.confidential or d.confidential_path,
        edm_index_path=a.edm or d.edm_index_path,
    )


def cmd_validate(a) -> int:
    paths = _paths_from_args(a)
    try:
        report = validate_ruleset(paths)
    except RuleValidationError as e:
        print(f"[REJECT] 룰셋 검증 실패 (fail-closed — 직전 룰셋 유지): {e}", file=sys.stderr)
        return 1
    print("[OK] 룰셋 검증 통과")
    print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))
    return 0


def cmd_dry_run(a) -> int:
    paths = _paths_from_args(a)
    # 현재(=기본 config) 가드 대비 후보(paths) diff. 동일 경로면 무변경 확인용.
    rg = ReloadableGuard()
    diff = rg.dry_run(paths)
    if not diff.valid:
        print(f"[REJECT] 후보 룰셋 검증 실패: {diff.error}", file=sys.stderr)
        return 1
    out = {
        "fingerprint_before": diff.fingerprint_before,
        "fingerprint_after": diff.fingerprint_after,
        "totals": diff.totals,
        "changed": diff.changed,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if a.fail_on_change and diff.totals.get("changed", 0) > 0:
        return 3
    return 0


def cmd_apply(a) -> int:
    paths = _paths_from_args(a)
    rg = ReloadableGuard()
    res = rg.reload(paths)
    if not res.applied:
        print(f"[REJECT] 적용 거부(fail-closed): {res.error}", file=sys.stderr)
        return 1
    print(f"[OK] 적용됨 generation={res.generation} fingerprint={res.fingerprint}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NuFi 룰 핫리로드 CLI")
    ap.add_argument("--patterns", default=None, help="patterns.yaml 경로(미지정 시 기본)")
    ap.add_argument("--policy", default=None, help="policy.yaml 경로")
    ap.add_argument("--confidential", default=None, help="confidential.yaml 경로")
    ap.add_argument("--edm", default=None, help="edm/index.json 경로")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("validate", help="후보 룰셋 검증")
    dr = sub.add_parser("dry-run", help="현재 대비 결정 diff 산출(미적용)")
    dr.add_argument("--fail-on-change", action="store_true",
                    help="diff 가 1건 이상이면 exit 3")
    sub.add_parser("apply", help="로컬 인스턴스에 검증→스왑(데모/검증용)")

    a = ap.parse_args(argv)
    return {"validate": cmd_validate, "dry-run": cmd_dry_run, "apply": cmd_apply}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
