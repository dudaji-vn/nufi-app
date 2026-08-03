"""nftables 규칙 적용기 (CMP-94 트랙 B · 스펙 §8.1-2).

책임:
  - **원자적 commit:** ``nft -f`` 로 규칙 셋을 한 트랜잭션에 로드(부분 적용 불가 →
    화이트리스트 선commit 보장, A6).
  - **rollback:** 적용 전 현재 ``nft list ruleset`` 스냅샷 → 실패 시 복원.
  - **fail_mode(open|closed):** 적용 실패 시 open=테이블 제거(관찰만, A4),
    closed=패닉 셋 설치(전면 차단, A5).
  - **킬스위치:** ``disable()`` = 테이블 제거(A8).
  - **호환(A9):** ``nft`` 우선, 없으면 ``iptables-nft`` 환경 표기. 권한 부재/바이너리
    부재 시 ``dry_run`` 으로 안전 degrade(CI/에어갭).
  - **게이트웨이 식별자 해석:** policy.yaml 에 uid/cgroup 이 비면 routing.yaml 의
    ``gateway.process_names`` → 실행 중 프로세스의 uid 로 해석(런타임).

``CAP_NET_ADMIN``(또는 root)은 commit/disable 에만 필요. render/status 는 비특권.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from capture.targets import CaptureTargets, Target

from .rule_builder import (
    EnforcementConfig,
    LOG_PREFIX,
    Resolver,
    load_enforcement_config,
    render_panic,
    render_ruleset,
    render_teardown,
)

_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ApplyResult:
    ok: bool
    mode: str                 # "enforced" | "fail-open" | "fail-closed" | "dry-run"
    detail: str
    rule_text: str = ""
    backend: str = "nft"      # nft | iptables-nft | none


def _which_backend() -> str:
    if shutil.which("nft"):
        return "nft"
    if shutil.which("iptables-nft"):
        return "iptables-nft"
    return "none"


def _has_privilege() -> bool:
    # CAP_NET_ADMIN 직접 조회는 비표준 → root(uid 0) 또는 명시 환경변수로 판단.
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return True
    return os.environ.get("NUFI_EGRESS_PRIVILEGED") == "1"


def resolve_gateway_uids(routing_path: Optional[str] = None) -> List[int]:
    """routing.yaml gateway.process_names → 현재 실행 중 프로세스 uid 집합.

    ``/proc`` 스캔(런타임, 비특권 가능). 이름 부분일치(`capture.targets` 와 동일 규칙).
    """
    ct = CaptureTargets.load()
    procs = {p.lower() for p in ct.gateway.get("process_names", [])}
    if not procs:
        return []
    uids: set = set()
    proc_root = Path("/proc")
    if not proc_root.exists():
        return []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            comm = (entry / "comm").read_text(encoding="utf-8", errors="ignore").strip().lower()
        except (OSError, ValueError):
            continue
        if comm in procs or any(p in comm for p in procs):
            try:
                uids.add((entry.stat()).st_uid)
            except OSError:
                continue
    return sorted(uids)


class Applier:
    """규칙 셋 commit/rollback/disable 집행기."""

    def __init__(self, cfg: Optional[EnforcementConfig] = None,
                 *, dry_run: Optional[bool] = None,
                 routing_path: Optional[str] = None,
                 policy_path: Optional[str] = None):
        self.cfg = cfg or load_enforcement_config(policy_path)
        self.routing_path = routing_path
        self.backend = _which_backend()
        # dry_run 미지정 시: 바이너리/권한 없으면 자동 dry_run(안전 degrade).
        if dry_run is None:
            dry_run = self.backend == "none" or not _has_privilege()
        self.dry_run = dry_run

    # ---- 게이트웨이 화이트리스트 보강 ------------------------------------
    def _ensure_gateway_selectors(self) -> EnforcementConfig:
        cfg = self.cfg
        if cfg.gateway_uids or cfg.gateway_cgroups:
            return cfg
        # policy.yaml 미지정 → routing.yaml process_names 런타임 해석.
        uids = resolve_gateway_uids(self.routing_path)
        if not uids:
            raise ValueError(
                "게이트웨이 uid/cgroup 을 결정할 수 없습니다 — policy.yaml "
                "enforcement.gateway_uids 를 지정하거나 게이트웨이 프로세스를 "
                "실행한 상태에서 적용하십시오(화이트리스트 선적용 불가 시 적용 거부).")
        return EnforcementConfig(
            fail_mode=cfg.fail_mode, table=cfg.table,
            gateway_uids=uids, gateway_cgroups=list(cfg.gateway_cgroups),
            allow_extra=list(cfg.allow_extra), cgroup_level=cfg.cgroup_level)

    def _targets(self) -> List[Target]:
        return CaptureTargets.load().targets

    # ---- nft 실행 래퍼 --------------------------------------------------
    def _run_nft(self, ruleset: str) -> subprocess.CompletedProcess:
        return subprocess.run(["nft", "-f", "-"], input=ruleset,
                              text=True, capture_output=True, check=False)

    def _snapshot(self) -> Optional[str]:
        if self.dry_run or self.backend != "nft":
            return None
        r = subprocess.run(["nft", "list", "ruleset"], text=True,
                           capture_output=True, check=False)
        return r.stdout if r.returncode == 0 else None

    def _restore(self, snapshot: Optional[str]) -> None:
        # 우리 테이블만 지우고(다른 테이블 보존) 스냅샷의 우리 테이블을 복원하는 대신,
        # 안전하게 우리 테이블 제거로 롤백(원자 commit 전 상태 = 테이블 없음/이전 버전).
        if self.dry_run or self.backend != "nft":
            return
        self._run_nft(render_teardown(self.cfg.table))
        if snapshot and f"table inet {self.cfg.table}" in snapshot:
            # 이전 버전 테이블이 있었다면 스냅샷째 재적용(멱등).
            self._run_nft(snapshot)

    # ---- 공개 API -------------------------------------------------------
    def render(self, resolver: Optional[Resolver] = None) -> str:
        """집행 규칙 셋 텍스트(적용하지 않음). 비특권 가능."""
        cfg = self._ensure_gateway_selectors()
        return render_ruleset(self._targets(), cfg, resolver)

    def apply(self, resolver: Optional[Resolver] = None) -> ApplyResult:
        """규칙 셋을 원자 적용. 실패 시 fail_mode 에 따라 open/closed 폴백."""
        try:
            cfg = self._ensure_gateway_selectors()
            ruleset = render_ruleset(self._targets(), cfg, resolver)
        except ValueError as e:
            return self._fail(str(e), resolver)

        if self.dry_run:
            return ApplyResult(ok=True, mode="dry-run",
                               detail=f"backend={self.backend} (commit 생략)",
                               rule_text=ruleset, backend=self.backend)

        snapshot = self._snapshot()
        proc = self._run_nft(ruleset)
        if proc.returncode != 0:
            self._restore(snapshot)
            return self._fail(f"nft 적용 실패: {proc.stderr.strip()}", resolver)
        return ApplyResult(ok=True, mode="enforced",
                           detail="원자 commit 완료(화이트리스트 선적용)",
                           rule_text=ruleset, backend=self.backend)

    def _fail(self, reason: str, resolver: Optional[Resolver]) -> ApplyResult:
        """적용 실패 처리: fail_mode=open → 테이블 제거(관찰만), closed → 패닉 차단."""
        if self.cfg.fail_mode == "closed":
            panic = render_panic(self._targets(), self.cfg, resolver)
            if not self.dry_run and self.backend == "nft":
                self._run_nft(panic)
            return ApplyResult(ok=False, mode="fail-closed",
                               detail=f"{reason} → fail-closed 패닉 차단 설치",
                               rule_text=panic, backend=self.backend)
        # fail-open(기본): 차단 규칙 미적용 = 관찰만.
        if not self.dry_run and self.backend == "nft":
            self._run_nft(render_teardown(self.cfg.table))
        return ApplyResult(ok=False, mode="fail-open",
                           detail=f"{reason} → fail-open(차단 규칙 미적용, 탐지는 유지)",
                           backend=self.backend)

    def disable(self) -> ApplyResult:
        """킬스위치: 우리 테이블 전부 제거(A8). 트래픽 전면 통과."""
        teardown = render_teardown(self.cfg.table)
        if self.dry_run or self.backend != "nft":
            return ApplyResult(ok=True, mode="dry-run",
                               detail="disable(dry-run): 실제 nft 미실행",
                               rule_text=teardown, backend=self.backend)
        proc = self._run_nft(teardown)
        ok = proc.returncode == 0
        return ApplyResult(ok=ok, mode="enforced",
                           detail="킬스위치: 테이블 제거" if ok else f"제거 실패: {proc.stderr.strip()}",
                           rule_text=teardown, backend=self.backend)

    def status(self) -> dict:
        """현재 집행 상태(테이블 존재·규칙 수). 비특권 best-effort."""
        active = False
        rule_count = 0
        if self.backend == "nft" and (_has_privilege() or os.environ.get("NUFI_EGRESS_PRIVILEGED")):
            r = subprocess.run(["nft", "list", "table", "inet", self.cfg.table],
                               text=True, capture_output=True, check=False)
            if r.returncode == 0:
                active = True
                rule_count = sum(1 for ln in r.stdout.splitlines()
                                 if "drop" in ln or "accept" in ln)
        return {
            "backend": self.backend,
            "table": self.cfg.table,
            "fail_mode": self.cfg.fail_mode,
            "active": active,
            "rule_count": rule_count,
            "log_prefix": LOG_PREFIX.strip(),
            "privileged": _has_privilege(),
            "dry_run": self.dry_run,
        }
