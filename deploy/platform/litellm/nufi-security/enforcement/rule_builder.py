"""nftables 규칙 셋 빌더 (CMP-94 트랙 B · 스펙 §8.1-1).

routing.yaml(목적지·게이트웨이 단일 출처) + policy.yaml(enforcement 토글)에서
nftables 규칙 텍스트를 **결정론적**으로 생성한다. 원칙:

  - **정책 단일 출처(A7):** public 목적지는 ``capture.targets.derive_targets`` 가
    routing.yaml 의 ``egress_class: public`` 백엔드에서 파생한 것을 재사용한다.
    별도 정책 사본을 만들지 않는다.
  - **화이트리스트 선적용(A6):** 게이트웨이(uid/cgroup) accept 규칙이 drop 규칙보다
    **항상 먼저** 나온다. 전체 셋은 ``nft -f`` 한 트랜잭션으로 원자 로드되므로
    "게이트웨이 자살"(drop 만 들어간 중간 상태)이 발생할 수 없다.
  - **게이트웨이 식별자 필수:** uid/cgroup 화이트리스트 셀렉터가 하나도 없으면
    drop-only 규칙이 게이트웨이 정규 트래픽까지 막으므로 :class:`ValueError` 로 거부한다.

DNS 이름→IP 해석은 주입 가능한 ``resolver`` 로 분리해 골든 텍스트 테스트의 결정성을
보장한다(에어갭/CI: 픽스처 resolver, 운영: socket.getaddrinfo).
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import yaml

from capture.targets import CaptureTargets, Target

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _ROOT / "config"
_DEFAULT_ROUTING = _CONFIG_DIR / "routing.yaml"
_DEFAULT_POLICY = _CONFIG_DIR / "policy.yaml"

TABLE = "nufi_egress"
LOG_PREFIX = "nufi-egress-block "   # 커널 drop 로그 prefix(피드백 루프 §4.3)

# host -> 해석된 IP 목록. 운영 기본은 DNS, 테스트는 픽스처 주입.
Resolver = Callable[[str], List[str]]


@dataclass
class EnforcementConfig:
    """policy.yaml 의 ``enforcement:`` 섹션(없으면 안전 기본값)."""

    fail_mode: str = "open"                      # open(기본) | closed(옵트인)
    table: str = TABLE
    gateway_uids: List[int] = field(default_factory=list)
    gateway_cgroups: List[str] = field(default_factory=list)
    allow_extra: List[str] = field(default_factory=list)   # "host:port" 또는 "ip:port"
    cgroup_level: int = 2

    def __post_init__(self) -> None:
        if self.fail_mode not in ("open", "closed"):
            raise ValueError(f"fail_mode must be open|closed, got {self.fail_mode!r}")


@dataclass(frozen=True)
class ResolvedTarget:
    family: int           # socket.AF_INET | socket.AF_INET6
    ip: str
    port: int


def load_enforcement_config(policy_path: Optional[str] = None) -> EnforcementConfig:
    """policy.yaml → :class:`EnforcementConfig`. ``enforcement:`` 부재 시 기본값."""
    p = Path(policy_path or _DEFAULT_POLICY)
    cfg: Dict = {}
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            cfg = (yaml.safe_load(f) or {}).get("enforcement", {}) or {}
    return EnforcementConfig(
        fail_mode=cfg.get("fail_mode", "open"),
        table=cfg.get("table", TABLE),
        gateway_uids=[int(u) for u in cfg.get("gateway_uids", []) or []],
        gateway_cgroups=list(cfg.get("gateway_cgroups", []) or []),
        allow_extra=list(cfg.get("allow_extra", []) or []),
        cgroup_level=int(cfg.get("cgroup_level", 2)),
    )


def _dns_resolver(host: str) -> List[str]:
    """운영 기본 resolver: 리터럴 IP 는 그대로, 이름은 getaddrinfo 로 해석."""
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        pass
    ips: List[str] = []
    for fam in (socket.AF_INET, socket.AF_INET6):
        try:
            for info in socket.getaddrinfo(host, None, fam, socket.SOCK_STREAM):
                ip = info[4][0]
                if ip not in ips:
                    ips.append(ip)
        except socket.gaierror:
            continue
    return ips


def resolve_targets(targets: Sequence[Target],
                    resolver: Optional[Resolver] = None) -> List[ResolvedTarget]:
    """public 목적지(host,port) → 해석된 (family, ip, port) 목록(중복 제거·정렬).

    이름 해석은 ``resolver`` 로 주입(테스트=픽스처, 운영=DNS). 해석 실패 호스트는
    조용히 건너뛰지 않고 호출자가 알 수 있도록 빈 결과로 남는다(applier 가 경고).
    """
    resolver = resolver or _dns_resolver
    out: List[ResolvedTarget] = []
    seen: set = set()
    for t in targets:
        for ip in resolver(t.host):
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            fam = socket.AF_INET6 if addr.version == 6 else socket.AF_INET
            key = (fam, str(addr), t.port)
            if key in seen:
                continue
            seen.add(key)
            out.append(ResolvedTarget(family=fam, ip=str(addr), port=t.port))
    out.sort(key=lambda r: (r.family, r.ip, r.port))
    return out


def _set_elements(resolved: Sequence[ResolvedTarget], family: int) -> List[str]:
    return [f"{r.ip} . {r.port}" for r in resolved if r.family == family]


def _allow_extra_elements(allow_extra: Sequence[str],
                          resolver: Resolver, family: int) -> List[str]:
    out: List[str] = []
    for spec in allow_extra:
        host, _, port = spec.rpartition(":")
        if not host or not port.isdigit():
            continue
        for ip in resolver(host):
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            fam = socket.AF_INET6 if addr.version == 6 else socket.AF_INET
            if fam == family:
                out.append(f"{addr} . {port}")
    return sorted(set(out))


def _whitelist_rules(cfg: EnforcementConfig, daddr: str, setref: str) -> List[str]:
    """게이트웨이 accept 규칙(선적용). uid → cgroup 순으로 결정론적 출력."""
    rules: List[str] = []
    for uid in sorted(cfg.gateway_uids):
        rules.append(
            f'\t\tmeta skuid {uid} {daddr} . th dport {setref} accept '
            f'comment "gateway uid {uid}"')
    for cg in cfg.gateway_cgroups:
        rules.append(
            f'\t\tsocket cgroupv2 level {cfg.cgroup_level} "{cg}" '
            f'{daddr} . th dport {setref} accept comment "gateway cgroup"')
    return rules


def _header(cfg: EnforcementConfig, kind: str) -> List[str]:
    return [
        "#!/usr/sbin/nft -f",
        "# NuFi Egress Enforcement — 생성물, 직접 편집 금지.",
        "# policy_src=routing.yaml+policy.yaml  source=enforcement.rule_builder",
        f"# kind={kind} fail_mode={cfg.fail_mode} table=inet/{cfg.table}",
    ]


def _validate_whitelist(cfg: EnforcementConfig) -> None:
    if not cfg.gateway_uids and not cfg.gateway_cgroups:
        raise ValueError(
            "게이트웨이 화이트리스트 셀렉터(uid/cgroup)가 비어 있습니다 — "
            "drop-only 규칙은 게이트웨이 정규 트래픽까지 차단합니다. "
            "policy.yaml enforcement.gateway_uids/gateway_cgroups 를 지정하거나 "
            "applier 가 routing.yaml process_names 를 해석해 채우십시오.")


def render_ruleset(targets: Sequence[Target], cfg: EnforcementConfig,
                   resolver: Optional[Resolver] = None) -> str:
    """집행 규칙 셋(화이트리스트 accept 선적용 + public_dst drop) — 원자 로드용.

    출력은 ``nft -f`` 입력. 빈 줄/순서가 고정되어 골든 텍스트 비교가 가능하다.
    """
    _validate_whitelist(cfg)
    resolver = resolver or _dns_resolver
    resolved = resolve_targets(targets, resolver)
    v4 = _set_elements(resolved, socket.AF_INET)
    v6 = _set_elements(resolved, socket.AF_INET6)
    x4 = _allow_extra_elements(cfg.allow_extra, resolver, socket.AF_INET)
    x6 = _allow_extra_elements(cfg.allow_extra, resolver, socket.AF_INET6)

    lines: List[str] = _header(cfg, "enforce")
    # 멱등 재생성: 있으면 지우고 새로 만든다(전체 1 트랜잭션 → 원자성 A6).
    lines.append(f"add table inet {cfg.table}")
    lines.append(f"delete table inet {cfg.table}")
    lines.append(f"table inet {cfg.table} {{")

    if v4:
        lines.append("\tset public_dst {")
        lines.append("\t\ttype ipv4_addr . inet_service")
        lines.append('\t\tcomment "public LLM 목적지 (routing.yaml egress_class: public)"')
        lines.append("\t\telements = { " + ", ".join(v4) + " }")
        lines.append("\t}")
    if v6:
        lines.append("\tset public_dst6 {")
        lines.append("\t\ttype ipv6_addr . inet_service")
        lines.append("\t\telements = { " + ", ".join(v6) + " }")
        lines.append("\t}")
    if x4:
        lines.append("\tset allow_extra {")
        lines.append("\t\ttype ipv4_addr . inet_service")
        lines.append('\t\tcomment "운영 예외 (policy.yaml allow_extra, CPO 리뷰)"')
        lines.append("\t\telements = { " + ", ".join(x4) + " }")
        lines.append("\t}")
    if x6:
        lines.append("\tset allow_extra6 {")
        lines.append("\t\ttype ipv6_addr . inet_service")
        lines.append("\t\telements = { " + ", ".join(x6) + " }")
        lines.append("\t}")

    lines.append("\tchain output {")
    lines.append("\t\ttype filter hook output priority 0; policy accept;")
    lines.append("\t\t# 1) 게이트웨이 화이트리스트 (선적용 — 항상 drop 보다 먼저)")
    if v4:
        lines += _whitelist_rules(cfg, "ip daddr", "@public_dst")
    if v6:
        lines += _whitelist_rules(cfg, "ip6 daddr", "@public_dst6")
    if x4:
        lines.append('\t\tip daddr . th dport @allow_extra accept comment "operator exception"')
    if x6:
        lines.append('\t\tip6 daddr . th dport @allow_extra6 accept comment "operator exception"')
    lines.append("\t\t# 2) 그 외 출처 → public 목적지 = 우회 → drop + 로그")
    if v4:
        lines.append(f'\t\tip daddr . th dport @public_dst log prefix "{LOG_PREFIX}" drop')
    if v6:
        lines.append(f'\t\tip6 daddr . th dport @public_dst6 log prefix "{LOG_PREFIX}" drop')
    lines.append("\t}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_panic(targets: Sequence[Target], cfg: EnforcementConfig,
                 resolver: Optional[Resolver] = None) -> str:
    """fail-closed 패닉 셋: 화이트리스트 없이 public_dst 전면 drop(게이트웨이 포함).

    applier 가 규칙 적용에 실패하고 ``fail_mode=closed`` 일 때만 설치한다(A5).
    """
    resolver = resolver or _dns_resolver
    resolved = resolve_targets(targets, resolver)
    v4 = _set_elements(resolved, socket.AF_INET)
    v6 = _set_elements(resolved, socket.AF_INET6)
    lines: List[str] = _header(cfg, "panic-fail-closed")
    lines.append(f"add table inet {cfg.table}")
    lines.append(f"delete table inet {cfg.table}")
    lines.append(f"table inet {cfg.table} {{")
    if v4:
        lines.append("\tset public_dst {")
        lines.append("\t\ttype ipv4_addr . inet_service")
        lines.append("\t\telements = { " + ", ".join(v4) + " }")
        lines.append("\t}")
    if v6:
        lines.append("\tset public_dst6 {")
        lines.append("\t\ttype ipv6_addr . inet_service")
        lines.append("\t\telements = { " + ", ".join(v6) + " }")
        lines.append("\t}")
    lines.append("\tchain output {")
    lines.append("\t\ttype filter hook output priority 0; policy accept;")
    lines.append("\t\t# fail-closed: 화이트리스트 없음 — 전 출처 public drop")
    if v4:
        lines.append(f'\t\tip daddr . th dport @public_dst log prefix "{LOG_PREFIX}" drop')
    if v6:
        lines.append(f'\t\tip6 daddr . th dport @public_dst6 log prefix "{LOG_PREFIX}" drop')
    lines.append("\t}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_teardown(table: str = TABLE) -> str:
    """킬스위치/fail-open: 우리 테이블만 제거(없어도 실패하지 않게 add 후 delete)."""
    return (f"add table inet {table}\n"
            f"delete table inet {table}\n")


def build_from_config(routing_path: Optional[str] = None,
                      policy_path: Optional[str] = None,
                      resolver: Optional[Resolver] = None) -> str:
    """편의: routing.yaml + policy.yaml 로 집행 규칙 셋 텍스트를 만든다."""
    ct = CaptureTargets.load() if routing_path is None else CaptureTargets(
        targets=_load_targets(routing_path))
    cfg = load_enforcement_config(policy_path)
    return render_ruleset(ct.targets, cfg, resolver)


def _load_targets(routing_path: str) -> List[Target]:
    from capture.targets import derive_targets
    return derive_targets(routing_path)
