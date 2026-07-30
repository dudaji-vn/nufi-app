"""NuFi Egress Enforcement (트랙 B · CMP-94) — 모델 (a) nftables egress 허용목록.

설계 스펙: ``docs/history/SPEC_EGRESS_ENFORCEMENT.md`` (CMP-93). 거버넌스: 신규 CMP-58 승인
``43dd134b`` (트랙 A 감사 승인 ``3053e076`` 과 별개) — 보드 approved.

구성:
  - :mod:`enforcement.rule_builder` — routing.yaml/policy.yaml → nftables 규칙 셋
    (게이트웨이 화이트리스트 선적용 + public_dst drop). 정책 사본 금지: 목적지는
    ``capture.targets`` 파생을 재사용.
  - :mod:`enforcement.applier` — 원자적 commit/rollback, fail_mode(open|closed),
    킬스위치, CAP_NET_ADMIN 분리.
  - :mod:`enforcement.decision` — 트랙 A SIMULATED 결정 라인의 ``mode=ENFORCED`` 승격
    + ``rule_id``(nft 핸들/동적 set 원소) 기록.
  - :mod:`enforcement.feedback` — 커널 drop 로그(``nufi-egress-block`` prefix) →
    P1/P2 재유입 + ``blocked_attempts`` 카운터.
  - :mod:`enforcement.cli` — ``nufi-egress`` CLI (render/apply/disable/status/feedback).

온프렘 로컬(NFR1). 외부 호출 0.
"""
from __future__ import annotations

from .rule_builder import (
    TABLE,
    LOG_PREFIX,
    EnforcementConfig,
    ResolvedTarget,
    load_enforcement_config,
    render_ruleset,
    render_panic,
    render_teardown,
    resolve_targets,
)

__all__ = [
    "TABLE",
    "LOG_PREFIX",
    "EnforcementConfig",
    "ResolvedTarget",
    "load_enforcement_config",
    "render_ruleset",
    "render_panic",
    "render_teardown",
    "resolve_targets",
]
