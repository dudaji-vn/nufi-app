"""커버리지 집계 — '내 트래픽 중 X% 가 실제 게이트웨이를 통과' 상시 런타임 지표
(CMP-133 · v0.0.3 M1·O2 (a)).

nufi doctor(1회 진단, CMP-120)의 게이트웨이 통과 점검을 **상시 런타임 지표**로 연장한다.
flow_tap(capture/flow_tap.py)이 적재한 public-LLM 행 연결에서, 게이트웨이 경유
(via_gateway) 대 우회(bypass) 비율을 집계해 nftables 집행을 '측정 가능한 보증'으로
만든다(Operate '보증').

    coverage% = 게이트웨이 경유 flow / 관측된 public-LLM 행 flow × 100

설계 원칙:
  - **경량 인메모리 카운터(CoverageAggregator)** — 외부 의존 0, 핫패스 영향 최소.
    flow_tap 은 **이미 분류된** FlowRecord(via_gateway/bypass)만 적재하므로, 집계기는
    가산만 한다(재탐지 없음).
  - **선택적 경량 영속(JSON)** — 프로세스 재기동을 가로질러 누적 유지(상시 집계).
    외부 의존 없이 표준 json 만 사용.
  - **PASS/WARN/FAIL 3-상태(doctor 와 동일 어휘)** — 우회 = 보증 누수이므로 보수적으로
    강등한다. 우회 0건이어야 PASS, 임계 미만 커버리지는 FAIL, 관측 데이터 부재는 WARN.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

_ROOT = Path(__file__).resolve().parent.parent

# 3-상태 — enforcement/doctor.py 와 동일 어휘·의미를 미러(capture 층 독립 유지).
PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

# 기본 임계(보수적). 우회 0건(=100%)이어야 PASS, fail_below 미만이면 FAIL, 그 사이는 WARN.
DEFAULT_PASS_MIN = 1.0      # 커버리지 ≥ 100% → PASS (우회 0건)
DEFAULT_FAIL_BELOW = 0.90   # 커버리지 < 90% → FAIL


@dataclass
class CoverageSnapshot:
    """집계 시점의 커버리지 스냅샷(리포트 1건)."""

    total: int                       # 관측된 public-LLM 행 flow 수(captured)
    gateway: int                     # via_gateway True(게이트웨이 경유)
    bypass: int                      # bypass True(우회)
    coverage_pct: Optional[float]    # gateway/total×100. total==0 이면 None
    status: str                      # PASS | WARN | FAIL
    pass_min: float
    fail_below: float
    bypass_samples: List[Dict[str, Any]] = field(default_factory=list)
    window_started_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tool"] = "nufi-egress coverage"
        return d


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def _is_bypass(rec: Dict[str, Any]) -> Optional[bool]:
    """flow 레코드가 우회인지. flow_tap 레코드가 아니면(두 필드 모두 없음) None."""
    if "bypass" in rec:
        return bool(rec["bypass"])
    if "via_gateway" in rec:
        return not bool(rec["via_gateway"])
    return None


class CoverageAggregator:
    """public-LLM 행 flow 의 게이트웨이 커버리지 상시 집계기(경량·스레드세이프).

    flow_tap 이 적재한 FlowRecord(via_gateway/bypass)만 가산한다. 비-flow 레코드는
    집계에서 제외한다(``observe`` 가 False 반환).
    """

    def __init__(self, *, pass_min: float = DEFAULT_PASS_MIN,
                 fail_below: float = DEFAULT_FAIL_BELOW,
                 state_path: Optional[str] = None, max_samples: int = 5):
        self.pass_min = float(pass_min)
        self.fail_below = float(fail_below)
        self.max_samples = int(max_samples)
        self._lock = threading.Lock()
        self.total = 0
        self.gateway = 0
        self.bypass = 0
        self._samples: List[Dict[str, Any]] = []
        self.window_started_at = _now_iso()
        self.updated_at = self.window_started_at
        self.state_path = Path(state_path) if state_path else None
        if self.state_path and self.state_path.exists():
            self._load()

    # ---- 가산 -------------------------------------------------------------
    def observe(self, rec: Dict[str, Any]) -> bool:
        """flow 레코드 1건을 집계. flow_tap 레코드가 아니면 무시(False)."""
        byp = _is_bypass(rec)
        if byp is None:
            return False  # via_gateway/bypass 없음 → flow_tap 레코드 아님(집계 제외).
        with self._lock:
            self.total += 1
            if byp:
                self.bypass += 1
                if len(self._samples) < self.max_samples:
                    self._samples.append({
                        "src_ip": rec.get("src_ip"),
                        "process": rec.get("process"),
                        "dst_host": rec.get("dst_host") or rec.get("dst_ip"),
                        "dst_port": rec.get("dst_port"),
                        "backend": rec.get("backend"),
                        "severity": rec.get("severity", "high"),
                    })
            else:
                self.gateway += 1
            self.updated_at = _now_iso()
        return True

    def observe_many(self, recs: Iterable[Dict[str, Any]]) -> int:
        """여러 flow 레코드를 가산. 집계된 건수를 반환."""
        n = 0
        for r in recs:
            if self.observe(r):
                n += 1
        return n

    # ---- 상태 판정 --------------------------------------------------------
    def _status(self, pct: Optional[float]) -> str:
        if self.total == 0 or pct is None:
            return WARN  # 관측 데이터 부재 — 커버리지 단언 불가(강등).
        frac = pct / 100.0
        if frac >= self.pass_min:
            return PASS
        if frac < self.fail_below:
            return FAIL
        return WARN

    def snapshot(self) -> CoverageSnapshot:
        with self._lock:
            pct = (self.gateway / self.total * 100.0) if self.total else None
            return CoverageSnapshot(
                total=self.total, gateway=self.gateway, bypass=self.bypass,
                coverage_pct=(round(pct, 2) if pct is not None else None),
                status=self._status(pct),
                pass_min=self.pass_min, fail_below=self.fail_below,
                bypass_samples=list(self._samples),
                window_started_at=self.window_started_at,
                updated_at=self.updated_at,
            )

    # ---- 경량 영속(상시 집계: 재기동 가로질러 누적) ----------------------
    def persist(self) -> Optional[Path]:
        if not self.state_path:
            return None
        with self._lock:
            doc = {
                "version": 1,
                "total": self.total, "gateway": self.gateway, "bypass": self.bypass,
                "samples": self._samples,
                "window_started_at": self.window_started_at,
                "updated_at": _now_iso(),
            }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.state_path)  # 원자 교체.
        return self.state_path

    def _load(self) -> None:
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except (json.JSONDecodeError, OSError):
            return  # 손상/부재 상태는 무시하고 새로 시작.
        self.total = int(doc.get("total", 0))
        self.gateway = int(doc.get("gateway", 0))
        self.bypass = int(doc.get("bypass", 0))
        self._samples = list(doc.get("samples", []))[: self.max_samples]
        self.window_started_at = doc.get("window_started_at") or self.window_started_at
        self.updated_at = doc.get("updated_at") or self.updated_at

    def reset(self) -> None:
        with self._lock:
            self.total = self.gateway = self.bypass = 0
            self._samples = []
            self.window_started_at = _now_iso()
            self.updated_at = self.window_started_at

    # ---- 편의 생성자 ------------------------------------------------------
    @classmethod
    def from_flows(cls, flows: Iterable[Dict[str, Any]], **kw) -> "CoverageAggregator":
        agg = cls(**kw)
        agg.observe_many(flows)
        return agg


# --------------------------------------------------------------------------- 렌더
def render_coverage_human(snap: CoverageSnapshot) -> str:
    """커버리지 스냅샷을 사람읽기 리포트로(‘X% 게이트웨이 통과’)."""
    glyph = {PASS: "🟢", WARN: "🟡", FAIL: "🔴"}.get(snap.status, "·")
    lines: List[str] = []
    lines.append("nufi-egress coverage — 게이트웨이 커버리지 보증")
    lines.append("=" * 60)
    if snap.total == 0:
        lines.append("관측된 public-LLM 행 flow 없음 — 커버리지 단언 불가(WARN/강등).")
        lines.append("  ↳ python3 -m capture.flow_tap --simulate samples/flow_replay.jsonl "
                     "또는 --live 로 flow 를 먼저 캡처하십시오.")
    else:
        pct = snap.coverage_pct if snap.coverage_pct is not None else 0.0
        lines.append(f"내 트래픽 중 {pct:.1f}% 가 게이트웨이를 통과 "
                     f"(게이트웨이 {snap.gateway} / 관측 {snap.total}, 우회 {snap.bypass})")
        if snap.bypass:
            lines.append(f"  ⚠ 게이트웨이 우회 {snap.bypass}건 — 조용한 public 직결 누수(보증 미달).")
            for s in snap.bypass_samples:
                lines.append(f"    · {s.get('src_ip')}/{s.get('process')} → "
                             f"{s.get('dst_host')}:{s.get('dst_port')} ({s.get('backend')})")
    lines.append("-" * 60)
    lines.append(f"종합: {glyph} {snap.status}  "
                 f"(PASS≥{snap.pass_min*100:.0f}% · FAIL<{snap.fail_below*100:.0f}%)")
    return "\n".join(lines)
