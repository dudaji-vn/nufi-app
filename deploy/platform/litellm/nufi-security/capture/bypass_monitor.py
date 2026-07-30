"""우회 상시 모니터링/알림 — 게이트웨이 우회 outbound 준실시간 탐지 + 임계 알림
(CMP-133 · v0.0.3 M1·O2 (c)).

flow_tap(capture/flow_tap.py)의 우회 판정(bypass)을 재사용해, 게이트웨이를 우회한
public-LLM 행 연결이 **임계(threshold)** 를 넘으면 알림을 발화한다. 동일 (출처→목적지)
키의 반복 우회는 **suppression(쿨다운 디바운스)** 으로 억제해 알림 폭주를 막는다.

doctor 의 PASS/WARN/FAIL 어휘를 재사용한다:
  - FAIL : 임계 초과 우회 알림 발화(보증 누수 — 조용한 직결).
  - WARN : 우회는 관측됐으나 임계 미만(아직 알림 아님).
  - PASS : 우회 0건.

설계:
  - **준실시간**: audit_bot 과 동일한 producer/consumer — flow_tap 이 flow 로그에 append
    하면, 모니터는 그 로그를 폴(tail)하며 우회를 탐지한다(``run_forever``). 사용자 경로
    무지연.
  - **per-key 롤링 윈도**: ``window_sec`` 안에서 키별 우회 횟수가 ``threshold`` 에 도달하면
    1회 발화 후 ``cooldown_sec`` 동안 같은 키를 억제(디바운스). 쿨다운 경과 후 재발화 가능.
  - **알림 적재**: logs/alerts.jsonl 에 append(audit_bot 알림과 동일 싱크) + ``notify`` 훅
    (운영 시 webhook/메일 연결 자리). PoC 기본 훅 = 무동작.
  - **테스트 주입 가능 시계**: ``clock`` 콜러블로 쿨다운/윈도를 결정적으로 검증.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from capture.coverage import PASS, WARN, FAIL  # 동일 3-상태 어휘 재사용.

_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_THRESHOLD = 1        # 우회 1건이면 즉시 알림(보수적 기본).
DEFAULT_WINDOW_SEC = 60.0    # 임계 카운트를 누적하는 롤링 윈도.
DEFAULT_COOLDOWN_SEC = 300.0 # 발화 후 동일 키 억제(디바운스) 기간.


@dataclass
class AlertEvent:
    """발화된 우회 임계 알림 1건."""

    alert_id: str
    ts: str
    kind: str
    severity: str
    key: str
    threshold: int
    window_count: int
    src_ip: Optional[str]
    process: Optional[str]
    dst_host: Optional[str]
    dst_port: Optional[int]
    backend: Optional[str]
    flow_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if not d.get("extra"):
            d.pop("extra", None)
        return d


class BypassMonitor:
    """게이트웨이 우회 준실시간 모니터 — 임계 알림 + suppression(디바운스)."""

    def __init__(self, *, threshold: int = DEFAULT_THRESHOLD,
                 window_sec: float = DEFAULT_WINDOW_SEC,
                 cooldown_sec: float = DEFAULT_COOLDOWN_SEC,
                 alerts_path: Optional[str] = None,
                 notify: Optional[Callable[[AlertEvent], None]] = None,
                 clock: Callable[[], float] = time.time):
        self.threshold = max(1, int(threshold))
        self.window_sec = float(window_sec)
        self.cooldown_sec = float(cooldown_sec)
        self.alerts_path = (Path(alerts_path) if alerts_path
                            else (_ROOT / "logs" / "alerts.jsonl"))
        self._notify_hook = notify
        self._clock = clock
        self._lock = threading.Lock()
        # per-key 윈도(우회 타임스탬프 버퍼)와 억제 만료 시각.
        self._window: Dict[str, List[float]] = {}
        self._suppressed_until: Dict[str, float] = {}
        self.stats = {"observed": 0, "bypass": 0, "alerts": 0, "suppressed": 0}
        self._seen_flow_ids: set[str] = set()  # 로그 재폴 시 중복 방지(run_forever).

    # ---- 키(suppression 단위): 출처 프로세스/IP → 목적지 -----------------
    @staticmethod
    def _key(rec: Dict[str, Any]) -> str:
        src = rec.get("src_ip") or rec.get("src_host") or "?"
        proc = rec.get("process") or rec.get("src_process") or "?"
        dst = rec.get("dst_host") or rec.get("dst_ip") or "?"
        return f"{src}|{proc}|{dst}"

    @staticmethod
    def _is_bypass(rec: Dict[str, Any]) -> Optional[bool]:
        if "bypass" in rec:
            return bool(rec["bypass"])
        if "via_gateway" in rec:
            return not bool(rec["via_gateway"])
        return None

    # ---- 한 건 관측 → 알림(없으면 None) ----------------------------------
    def observe(self, rec: Dict[str, Any]) -> Optional[AlertEvent]:
        byp = self._is_bypass(rec)
        if byp is None:
            return None  # flow_tap 레코드 아님.
        with self._lock:
            self.stats["observed"] += 1
            if not byp:
                return None  # 정상(게이트웨이 경유) — 알림 아님.
            self.stats["bypass"] += 1
            now = self._clock()
            key = self._key(rec)

            # suppression: 쿨다운 중이면 억제(디바운스).
            if now < self._suppressed_until.get(key, 0.0):
                self.stats["suppressed"] += 1
                return None

            # per-key 롤링 윈도 갱신.
            buf = [t for t in self._window.get(key, []) if now - t <= self.window_sec]
            buf.append(now)
            self._window[key] = buf

            if len(buf) >= self.threshold:
                ev = self._fire(key, rec, len(buf), now)
                self._suppressed_until[key] = now + self.cooldown_sec
                self._window[key] = []  # 발화 후 윈도 리셋.
                return ev
            return None

    def observe_many(self, recs) -> List[AlertEvent]:
        out: List[AlertEvent] = []
        for r in recs:
            ev = self.observe(r)
            if ev is not None:
                out.append(ev)
        return out

    # ---- 발화 -------------------------------------------------------------
    def _fire(self, key: str, rec: Dict[str, Any], count: int, now: float) -> AlertEvent:
        ev = AlertEvent(
            alert_id=str(uuid.uuid4()),
            ts=time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)),
            kind="gateway_bypass_threshold",
            severity="high",
            key=key,
            threshold=self.threshold,
            window_count=count,
            src_ip=rec.get("src_ip"),
            process=rec.get("process") or rec.get("src_process"),
            dst_host=rec.get("dst_host") or rec.get("dst_ip"),
            dst_port=rec.get("dst_port"),
            backend=rec.get("backend"),
            flow_id=rec.get("flow_id"),
        )
        self.stats["alerts"] += 1
        self._write_alert(ev)
        if self._notify_hook is not None:
            self._notify_hook(ev)
        return ev

    def _write_alert(self, ev: AlertEvent) -> None:
        self.alerts_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.alerts_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())  # 내구성 보장(특수 파일/FS 는 미지원 가능 → 베스트에포트).
            except OSError:
                pass

    # ---- 상태/리포트 ------------------------------------------------------
    def status(self) -> str:
        if self.stats["alerts"] > 0:
            return FAIL
        if self.stats["bypass"] > 0:
            return WARN
        return PASS

    def report(self) -> Dict[str, Any]:
        return {
            "tool": "nufi-egress monitor",
            "threshold": self.threshold,
            "window_sec": self.window_sec,
            "cooldown_sec": self.cooldown_sec,
            "status": self.status(),
            "stats": dict(self.stats),
        }

    # ---- 준실시간 데몬(flow 로그 tail) -----------------------------------
    def run_forever(self, *, flow_tap=None, poll_interval: float = 0.25,
                    stop_event: Optional[threading.Event] = None) -> None:  # pragma: no cover
        """flow_tap 이 적재한 flow 로그를 폴하며 우회를 준실시간 탐지(데몬).

        audit_bot 과 동일한 producer/consumer: flow_tap 은 append 만, 모니터는 tail.
        flow_id 로 중복 처리 차단.
        """
        from capture.flow_tap import FlowTap
        tap = flow_tap or FlowTap()
        stop = stop_event or threading.Event()
        while not stop.is_set():
            try:
                for rec in tap.read_flows():
                    fid = rec.get("flow_id")
                    if fid and fid in self._seen_flow_ids:
                        continue
                    if fid:
                        self._seen_flow_ids.add(fid)
                    self.observe(rec)
            except Exception as exc:  # 모니터 죽어도 사용자 경로 무영향.
                print(f"[bypass_monitor] poll error: {exc}")
            stop.wait(poll_interval)


# --------------------------------------------------------------------------- 렌더
def render_monitor_human(report: Dict[str, Any], events: List[AlertEvent]) -> str:
    glyph = {PASS: "🟢", WARN: "🟡", FAIL: "🔴"}.get(report["status"], "·")
    s = report["stats"]
    lines: List[str] = []
    lines.append("nufi-egress monitor — 우회 상시 모니터링/알림")
    lines.append("=" * 60)
    lines.append(f"관측 {s['observed']} · 우회 {s['bypass']} · 알림 {s['alerts']} · "
                 f"억제(suppressed) {s['suppressed']}  "
                 f"[threshold={report['threshold']}, cooldown={report['cooldown_sec']:.0f}s]")
    for ev in events:
        lines.append(f"  🔔 ALERT {ev.severity} {ev.src_ip}/{ev.process} → "
                     f"{ev.dst_host}:{ev.dst_port} (윈도 {ev.window_count}건/임계 {ev.threshold})")
    if s["suppressed"]:
        lines.append(f"  · 동일 키 반복 우회 {s['suppressed']}건은 suppression(쿨다운)으로 억제됨.")
    lines.append("-" * 60)
    lines.append(f"종합: {glyph} {report['status']}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:  # pragma: no cover - CLI 경유는 cli.py
    ap = argparse.ArgumentParser(
        description="게이트웨이 우회 상시 모니터링/알림")
    ap.add_argument("--simulate", metavar="REPLAY.jsonl",
                    help="flow 리플레이로 우회 모니터 1회 실행(에어갭/CI)")
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    ap.add_argument("--window", type=float, default=DEFAULT_WINDOW_SEC)
    ap.add_argument("--cooldown", type=float, default=DEFAULT_COOLDOWN_SEC)
    ap.add_argument("--alerts", default=None, help="알림 출력 경로(기본 logs/alerts.jsonl)")
    ap.add_argument("--targets", default=None, help="capture_targets.yaml 경로")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    import tempfile
    from capture.flow_tap import FlowTap
    mon = BypassMonitor(threshold=args.threshold, window_sec=args.window,
                        cooldown_sec=args.cooldown, alerts_path=args.alerts)
    if args.simulate:
        with tempfile.TemporaryDirectory(prefix="nufi-monitor-") as td:
            tap = FlowTap(targets_path=args.targets, base_dir=td)
            tap.simulate(args.simulate)
            events = mon.observe_many(tap.read_flows())
    else:
        tap = FlowTap(targets_path=args.targets)
        events = mon.observe_many(tap.read_flows())
    report = mon.report()
    if args.json:
        print(json.dumps({**report, "events": [e.to_dict() for e in events]},
                         ensure_ascii=False, indent=2))
    else:
        print(render_monitor_human(report, events))
    return 1 if report["status"] == FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
