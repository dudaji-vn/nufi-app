"""Flow tap — public 목적지 연결 메타 캡처 + 게이트웨이 우회 탐지 (CMP-87 P1 (b)).

HTTPS 본문은 못 읽어도 "누가 우회해 public LLM 에 붙었나"는 연결 메타(5-튜플·SNI·
PID/프로세스·바이트수)로 확실히 탐지한다.

  - 목적지 필터: capture_targets 의 public 목적지에 가는 연결만 캡처(타 목적지 0건).
  - 우회 판정: 연결 src 가 게이트웨이(hosts/process)가 아니면 = 게이트웨이 우회
    (사람 실수/직접 호출) → high-severity 후보. P2 봇이 alert 로 승격.

두 가지 실행 모드:
  - live    : tcpdump 를 BPF=public 목적지로 띄워 캡처(root/CAP_NET_RAW 필요).
  - simulate: 미리 만든 flow 로그(jsonl)를 리플레이 — root 없이(에어갭/CI) 재현.

출력: logs/packets/public/flow-YYYY-MM-DD.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from capture.targets import CaptureTargets

_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class FlowRecord:
    """캡처된 public-LLM 행 연결 1건의 메타데이터."""
    flow_id: str
    ts: str
    epoch_ms: int
    src_ip: Optional[str]
    src_port: Optional[int]
    dst_host: Optional[str]
    dst_ip: Optional[str]
    dst_port: int
    sni: Optional[str]
    pid: Optional[int]
    process: Optional[str]
    bytes: int
    backend: str
    provider: str
    via_gateway: bool
    bypass: bool                 # src ≠ 게이트웨이 → 우회
    severity: str                # high(우회) | info(정상)
    source: str                  # flow_tap_simulate | flow_tap_live
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = self.__dict__.copy()
        if not d.get("extra"):
            d.pop("extra", None)
        return d


class FlowTap:
    """public 목적지 flow tap. 목적지 필터 + 우회 판정 + flow 로그 적재."""

    def __init__(self, targets: Optional[CaptureTargets] = None,
                 targets_path: Optional[str] = None,
                 base_dir: Optional[str] = None):
        self.targets = targets or CaptureTargets.load(targets_path)
        raw = (base_dir or os.environ.get("EGRESS_PACKET_DIR") or "logs/packets")
        base = Path(raw)
        self.base_dir = base if base.is_absolute() else (_ROOT / base)
        self._lock = threading.Lock()

    # ---- 적재 -------------------------------------------------------------
    def _sink_path(self) -> Path:
        day = time.strftime("%Y-%m-%d", time.localtime())
        return self.base_dir / "public" / f"flow-{day}.jsonl"

    def _write(self, rec: FlowRecord) -> None:
        p = self._sink_path()
        line = json.dumps(rec.to_dict(), ensure_ascii=False)
        with self._lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    # ---- 단일 연결 이벤트 → FlowRecord (목적지 필터 + 우회 판정) -----------
    def classify(self, conn: Dict[str, Any], *,
                 source: str = "flow_tap_simulate") -> Optional[FlowRecord]:
        """연결 이벤트 하나를 분류. public 목적지가 아니면 None(필터 아웃).

        conn 키(있는 것만): src_ip, src_port, dst_ip, dst_host, sni, dst_port,
        pid, process, bytes, ts.
        """
        # 목적지 식별: SNI(ClientHello) 우선, 없으면 dst_host.
        host = conn.get("sni") or conn.get("dst_host")
        port = conn.get("dst_port", 443)
        target = self.targets.match(host, port)
        if target is None:
            return None  # public LLM 목적지가 아님 → 캡처하지 않음(타 목적지 0건).

        src_ip = conn.get("src_ip")
        process = conn.get("process")
        via_gw = self.targets.is_gateway_src(src_ip=src_ip, process=process)
        bypass = not via_gw

        now_ms = int(time.time() * 1000)
        return FlowRecord(
            flow_id=str(uuid.uuid4()),
            ts=conn.get("ts") or time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            epoch_ms=int(conn.get("epoch_ms", now_ms)),
            src_ip=src_ip,
            src_port=conn.get("src_port"),
            dst_host=conn.get("dst_host") or host,
            dst_ip=conn.get("dst_ip"),
            dst_port=int(port),
            sni=conn.get("sni"),
            pid=conn.get("pid"),
            process=process,
            bytes=int(conn.get("bytes", 0)),
            backend=target.backend,
            provider=target.provider,
            via_gateway=via_gw,
            bypass=bypass,
            # 우회 = high(P2 봇이 alert 로 승격), 정상 게이트웨이 행 = info.
            severity="high" if bypass else "info",
            source=source,
        )

    # ---- simulate: 미리 만든 flow 로그 리플레이 ---------------------------
    def simulate(self, replay_path: str) -> Dict[str, int]:
        """flow 리플레이 입력(jsonl)을 읽어 목적지 필터·우회 판정 후 적재.

        반환: {seen, captured, dropped, bypass, gateway} 통계.
        """
        records = _read_jsonl(replay_path)
        return self._ingest(records, source="flow_tap_simulate")

    def _ingest(self, conns: Iterable[Dict[str, Any]], *, source: str) -> Dict[str, int]:
        stats = {"seen": 0, "captured": 0, "dropped": 0, "bypass": 0, "gateway": 0}
        for conn in conns:
            stats["seen"] += 1
            rec = self.classify(conn, source=source)
            if rec is None:
                stats["dropped"] += 1
                continue
            self._write(rec)
            stats["captured"] += 1
            if rec.bypass:
                stats["bypass"] += 1
            else:
                stats["gateway"] += 1
        return stats

    # ---- live: tcpdump 래퍼(BPF=public 목적지) -----------------------------
    def live(self, *, iface: str = "any", duration: Optional[int] = None,
             tcpdump: str = "tcpdump") -> Dict[str, int]:
        """tcpdump 를 BPF=public 목적지로 띄워 연결을 캡처(root/CAP_NET_RAW 필요).

        에어갭/CI 에서는 simulate 를 쓴다. 여기서는 tcpdump 가용성과 권한을 점검하고,
        가용 시 BPF 로 캡처해 연결 메타를 적재한다. tcpdump 가 없거나 권한이 없으면
        RuntimeError 로 안내(데모는 --simulate 로 우회).
        """
        bpf = self.targets.bpf()
        if shutil.which(tcpdump) is None:
            raise RuntimeError(
                f"'{tcpdump}' 를 찾을 수 없습니다. 에어갭/CI 는 --simulate 를 사용하세요. BPF={bpf!r}")
        cmd = [tcpdump, "-i", iface, "-l", "-n", "-q", bpf]
        if duration:
            # -G/-W 대신 타임아웃으로 단순 종료.
            pass
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except PermissionError as e:  # pragma: no cover - 환경 의존
            raise RuntimeError(
                f"tcpdump 권한 부족(root/CAP_NET_RAW 필요): {e}. 데모는 --simulate 사용.") from e
        conns: List[Dict[str, Any]] = []
        try:
            start = time.time()
            assert proc.stdout is not None
            for line in proc.stdout:  # pragma: no cover - 라이브 캡처(환경 의존)
                conn = _parse_tcpdump_line(line)
                if conn:
                    conns.append(conn)
                if duration and (time.time() - start) >= duration:
                    break
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
        return self._ingest(conns, source="flow_tap_live")

    # ---- 읽기(테스트·감사 봇 입력) ----------------------------------------
    def read_flows(self) -> List[dict]:
        d = self.base_dir / "public"
        if not d.exists():
            return []
        out: List[dict] = []
        for p in sorted(d.glob("flow-*.jsonl")):
            with open(p, "r", encoding="utf-8") as f:
                out.extend(json.loads(ln) for ln in f if ln.strip())
        return out


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _parse_tcpdump_line(line: str) -> Optional[Dict[str, Any]]:  # pragma: no cover
    """tcpdump -q -n 한 줄에서 5-튜플 근사치 추출(베스트에포트).

    형식 예: 'IP 10.0.0.5.54321 > 93.184.216.34.443: tcp 0'
    SNI/PID 보강은 환경 의존(ss/eBPF) — 라이브 모드의 최소 파서.
    """
    parts = line.split()
    try:
        i = parts.index(">")
    except ValueError:
        return None
    src = parts[i - 1]
    dst = parts[i + 1].rstrip(":")

    def split_ipport(s: str) -> tuple[Optional[str], Optional[int]]:
        if "." not in s:
            return s, None
        ip, _, port = s.rpartition(".")
        try:
            return ip, int(port)
        except ValueError:
            return s, None

    src_ip, src_port = split_ipport(src)
    dst_ip, dst_port = split_ipport(dst)
    return {"src_ip": src_ip, "src_port": src_port,
            "dst_ip": dst_ip, "dst_port": dst_port or 443,
            "bytes": 0}


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="public 목적지 flow tap + 우회 탐지")
    ap.add_argument("--simulate", metavar="REPLAY.jsonl",
                    help="미리 만든 flow 로그 리플레이(root 없이 재현 — 에어갭/CI)")
    ap.add_argument("--live", action="store_true", help="tcpdump 라이브 캡처(root 필요)")
    ap.add_argument("--iface", default="any", help="라이브 캡처 인터페이스")
    ap.add_argument("--duration", type=int, default=None, help="라이브 캡처 지속(초)")
    ap.add_argument("--targets", default=None, help="capture_targets.yaml 경로")
    ap.add_argument("--out", default=None, help="flow 로그 출력 base_dir(기본 logs/packets)")
    args = ap.parse_args(argv)

    tap = FlowTap(targets_path=args.targets, base_dir=args.out)
    print("BPF:", tap.targets.bpf())
    if args.simulate:
        stats = tap.simulate(args.simulate)
    elif args.live:
        stats = tap.live(iface=args.iface, duration=args.duration)
    else:
        ap.error("--simulate REPLAY.jsonl 또는 --live 중 하나가 필요합니다")
        return 2
    print(f"flow tap: seen={stats['seen']} captured={stats['captured']} "
          f"dropped={stats['dropped']} (gateway={stats['gateway']} bypass={stats['bypass']})")
    if stats["bypass"]:
        print(f"  ⚠ 게이트웨이 우회 의심 연결 {stats['bypass']}건 — P2 봇이 high-severity alert 로 승격")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
