"""캡처 대상(public LLM 목적지) 파생·캐시·BPF 빌드 (CMP-87 P1).

목적지 집합은 config/routing.yaml 의 egress_class: public 백엔드 호스트/포트에서
자동 파생한다. 파생 결과는 config/capture_targets.yaml 로 캐시·갱신하며(NFR3),
운영자가 직접 호스트/포트를 추가·수정할 수도 있다.

핵심 사용처:
  - flow_tap 의 목적지 필터(타 목적지 0건 — 수용기준 1).
  - 게이트웨이 우회 판정(src 가 gateway.hosts/process 가 아니면 우회 — 수용기준 3).
  - tcpdump BPF 필터 문자열 생성(라이브 캡처).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _ROOT / "config"
_DEFAULT_ROUTING = _CONFIG_DIR / "routing.yaml"
_DEFAULT_TARGETS = _CONFIG_DIR / "capture_targets.yaml"

# 게이트웨이로 인정하는 기본 출처(우회 판정 기준). capture_targets.yaml 로 덮어쓴다.
_DEFAULT_GATEWAY = {
    "hosts": ["127.0.0.1", "::1", "localhost", "0.0.0.0"],
    "process_names": ["litellm", "gateway", "uvicorn", "egress-gateway"],
}


@dataclass
class Target:
    host: str
    port: int
    backend: str = ""
    provider: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"host": self.host, "port": self.port,
                "backend": self.backend, "provider": self.provider}


def _host_port(api_base: Optional[str], default_port: int = 443) -> Optional[tuple[str, int]]:
    """api_base URL 에서 host/port 추출. https 기본 443, http 기본 80."""
    if not api_base:
        return None
    u = urlparse(api_base if "://" in api_base else "https://" + api_base)
    host = u.hostname
    if not host:
        return None
    if u.port:
        port = u.port
    else:
        port = 80 if u.scheme == "http" else default_port
    return host, port


def derive_targets(routing_path: Optional[str] = None) -> List[Target]:
    """routing.yaml 의 egress_class == public 백엔드에서 (host, port) 목적지를 파생."""
    path = Path(routing_path or _DEFAULT_ROUTING)
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    backends = cfg.get("backends", {})
    provider_egress = cfg.get("provider_egress", {})

    seen: set[tuple[str, int]] = set()
    targets: List[Target] = []
    for name, b in backends.items():
        provider = b.get("provider", "unknown")
        egress = b.get("egress_class") or provider_egress.get(provider, "public")
        if egress != "public":
            continue
        hp = _host_port(b.get("api_base"))
        if hp is None:
            continue
        if hp in seen:
            continue
        seen.add(hp)
        targets.append(Target(host=hp[0], port=hp[1], backend=name, provider=provider))
    return targets


def build_bpf(targets: List[Target]) -> str:
    """public 목적지에만 거는 tcpdump BPF 필터 문자열.

    예: tcp and (dst host api.anthropic.com or dst host api.openai.com) and (dst port 443)
    """
    if not targets:
        # 목적지가 없으면 아무것도 매치하지 않는 필터(안전: 전 트래픽 캡처 방지).
        return "tcp and dst port 0"
    hosts = sorted({t.host for t in targets})
    ports = sorted({t.port for t in targets})
    host_expr = " or ".join(f"dst host {h}" for h in hosts)
    port_expr = " or ".join(f"dst port {p}" for p in ports)
    return f"tcp and ({host_expr}) and ({port_expr})"


@dataclass
class CaptureTargets:
    """capture_targets.yaml 로드/저장 + 목적지 매칭 + 우회 판정."""

    targets: List[Target] = field(default_factory=list)
    gateway: Dict[str, Any] = field(default_factory=lambda: dict(_DEFAULT_GATEWAY))
    path: Optional[Path] = None

    # ---- 로드/갱신 --------------------------------------------------------
    @classmethod
    def load(cls, path: Optional[str] = None) -> "CaptureTargets":
        p = Path(path or _DEFAULT_TARGETS)
        if not p.exists():
            # 캐시 부재 시 routing.yaml 에서 즉석 파생(에어갭/CI 친화).
            return cls(targets=derive_targets(), path=p)
        with open(p, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        targets = [Target(host=t["host"], port=int(t.get("port", 443)),
                          backend=t.get("backend", ""), provider=t.get("provider", ""))
                   for t in cfg.get("targets", [])]
        gw = dict(_DEFAULT_GATEWAY)
        gw.update(cfg.get("gateway", {}) or {})
        return cls(targets=targets, gateway=gw, path=p)

    @classmethod
    def refresh(cls, routing_path: Optional[str] = None,
                out_path: Optional[str] = None) -> "CaptureTargets":
        """routing.yaml 에서 목적지를 재파생해 capture_targets.yaml 로 기록(NFR3).

        기존 파일의 gateway 섹션(운영자 커스터마이즈)은 보존한다.
        """
        out = Path(out_path or _DEFAULT_TARGETS)
        gw = dict(_DEFAULT_GATEWAY)
        if out.exists():
            with open(out, "r", encoding="utf-8") as f:
                prev = yaml.safe_load(f) or {}
            gw.update(prev.get("gateway", {}) or {})
        ct = cls(targets=derive_targets(routing_path), gateway=gw, path=out)
        ct.save()
        return ct

    def save(self) -> Path:
        assert self.path is not None, "save() 에는 path 가 필요합니다"
        doc = {
            "version": 1,
            "gateway": self.gateway,
            "targets": [t.to_dict() for t in self.targets],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "# 캡처 대상(public LLM 목적지).\n"
            "# routing.yaml 의 egress_class: public 백엔드에서 파생(NFR3).\n"
            "# 갱신: python3 -m capture.targets --refresh\n"
            "# gateway 섹션 = 우회 판정 기준(이 출처가 아니면 우회로 본다).\n"
        )
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(header)
            yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
        return self.path

    # ---- 매칭 / 우회 판정 --------------------------------------------------
    def bpf(self) -> str:
        return build_bpf(self.targets)

    def match(self, host: Optional[str], port: Optional[int]) -> Optional[Target]:
        """(host, port) 가 public LLM 목적지에 해당하면 Target, 아니면 None.

        host 는 dst host 또는 TLS SNI(ClientHello) 양쪽을 받는다.
        """
        if host is None:
            return None
        for t in self.targets:
            if t.host == host and (port is None or int(port) == t.port):
                return t
        return None

    def is_gateway_src(self, *, src_ip: Optional[str] = None,
                       process: Optional[str] = None) -> bool:
        """연결 출처가 게이트웨이(프로세스/호스트)이면 True. 아니면 우회 후보."""
        hosts = {h.lower() for h in self.gateway.get("hosts", [])}
        procs = {p.lower() for p in self.gateway.get("process_names", [])}
        if src_ip and src_ip.lower() in hosts:
            return True
        if process:
            pl = process.lower()
            # 프로세스명은 경로/인자 포함 가능 → 부분일치 허용.
            if pl in procs or any(p in pl for p in procs):
                return True
        return False


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="capture_targets.yaml 파생/조회")
    ap.add_argument("--refresh", action="store_true",
                    help="routing.yaml 에서 목적지를 재파생해 capture_targets.yaml 기록")
    ap.add_argument("--routing", default=None, help="routing.yaml 경로")
    ap.add_argument("--out", default=None, help="capture_targets.yaml 출력 경로")
    ap.add_argument("--bpf", action="store_true", help="BPF 필터 문자열 출력")
    args = ap.parse_args(argv)

    if args.refresh:
        ct = CaptureTargets.refresh(args.routing, args.out)
        print(f"갱신: {ct.path} — 목적지 {len(ct.targets)}건")
    else:
        ct = CaptureTargets.load(args.out)
    for t in ct.targets:
        print(f"  public 목적지: {t.host}:{t.port} ({t.backend}/{t.provider})")
    if args.bpf:
        print("BPF:", ct.bpf())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
