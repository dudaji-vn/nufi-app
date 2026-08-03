"""CMP-133 v0.0.3 M1·O2 — 커버리지 보증 단위 테스트 (root 불요, 에어갭/CI).

수용 기준(binary) 검증:
  ① 커버리지 리포트 1건이 'X% 게이트웨이 통과' 형태로 산출(nufi-egress coverage).
  ② 우회 시나리오 1건에서 임계 알림이 실제 발화(suppression 동작 포함).

추가로 집계 산식·임계 PASS/WARN/FAIL·영속·CLI exit code 를 검증한다.

실행: ``pytest tests/test_cmp133_coverage.py`` 또는 ``python3 tests/test_cmp133_coverage.py``.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from capture.flow_tap import FlowTap                       # noqa: E402
from capture.coverage import (                             # noqa: E402
    CoverageAggregator, render_coverage_human, PASS, WARN, FAIL,
)
from capture.bypass_monitor import BypassMonitor           # noqa: E402
from enforcement import cli                                # noqa: E402

SAMPLES = ROOT / "samples"
REPLAY = SAMPLES / "flow_replay.jsonl"
BURST = SAMPLES / "flow_bypass_burst.jsonl"


def _flows_from(replay: Path) -> list:
    """리플레이를 격리 디렉터리로 분류·적재 후 FlowRecord 리스트로 읽는다."""
    with tempfile.TemporaryDirectory() as td:
        tap = FlowTap(base_dir=td)
        tap.simulate(str(replay))
        return tap.read_flows()


# ---------------------------------------------------------------- 집계 산식
def test_coverage_aggregator_math():
    """flow_replay: captured 4 = gateway 2 + bypass 2 → 커버리지 50%."""
    agg = CoverageAggregator.from_flows(_flows_from(REPLAY))
    snap = agg.snapshot()
    assert snap.total == 4
    assert snap.gateway == 2
    assert snap.bypass == 2
    assert snap.coverage_pct == 50.0
    # 50% < fail_below(0.90) → FAIL(보증 미달).
    assert snap.status == FAIL, snap
    assert snap.bypass_samples  # 우회 샘플 첨부.


def test_coverage_human_report_says_x_percent():
    """① 사람읽기 리포트가 'X% 가 게이트웨이를 통과' 문장을 포함."""
    snap = CoverageAggregator.from_flows(_flows_from(REPLAY)).snapshot()
    text = render_coverage_human(snap)
    assert "게이트웨이를 통과" in text
    assert "50.0%" in text


def test_coverage_status_thresholds():
    """PASS(100%)·FAIL(<90%)·WARN(그 사이)·WARN(데이터 없음) 경계."""
    gw = {"via_gateway": True, "bypass": False}
    bp = {"via_gateway": False, "bypass": True}

    # 100% → PASS
    s = CoverageAggregator.from_flows([gw, gw, gw]).snapshot()
    assert s.coverage_pct == 100.0 and s.status == PASS

    # 50% → FAIL
    s = CoverageAggregator.from_flows([gw, bp]).snapshot()
    assert s.status == FAIL

    # 95% (>fail_below, <pass_min) → WARN: 19 gw + 1 bypass
    s = CoverageAggregator.from_flows([gw] * 19 + [bp]).snapshot()
    assert s.coverage_pct == 95.0 and s.status == WARN

    # 관측 없음 → WARN(강등)
    s = CoverageAggregator(state_path=None).snapshot()
    assert s.total == 0 and s.coverage_pct is None and s.status == WARN


def test_coverage_ignores_non_flow_records():
    """via_gateway/bypass 가 없는 레코드는 집계 제외."""
    agg = CoverageAggregator()
    assert agg.observe({"foo": "bar"}) is False
    assert agg.observe({"bypass": True}) is True
    assert agg.snapshot().total == 1


def test_coverage_persist_roundtrip():
    """경량 영속(JSON) 누적: 재기동을 가로질러 카운터 복원."""
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "coverage_state.json"
        agg = CoverageAggregator(state_path=str(state))
        agg.observe_many(_flows_from(REPLAY))  # total4 gw2 bp2
        agg.persist()
        assert state.exists()

        agg2 = CoverageAggregator(state_path=str(state))  # _load 로 복원
        assert (agg2.total, agg2.gateway, agg2.bypass) == (4, 2, 2)
        # 추가 관측이 누적되는지.
        agg2.observe({"via_gateway": True})
        assert agg2.snapshot().total == 5


# ---------------------------------------------------------------- 우회 모니터
def test_monitor_threshold1_fires_and_suppresses():
    """② threshold=1 동일키 버스트 → 1회 발화 + 나머지 suppression(디바운스)."""
    with tempfile.TemporaryDirectory() as td:
        alerts = Path(td) / "alerts.jsonl"
        fired = []
        mon = BypassMonitor(threshold=1, cooldown_sec=300.0,
                            alerts_path=str(alerts), notify=fired.append)
        events = mon.observe_many(_flows_from(BURST))

        # 버스트: gw2 + 동일키 bypass5 + 다른키 bypass1.
        st = mon.stats
        assert st["bypass"] == 6
        # 동일키 5건 중 1건 발화·4건 억제 + 다른키 1건 발화 = 알림 2건, 억제 4건.
        assert st["alerts"] == 2, st
        assert st["suppressed"] == 4, st
        assert len(events) == 2
        assert mon.status() == FAIL

        # 알림이 실제 파일로 적재됐는지(재현 로그).
        lines = [json.loads(l) for l in alerts.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 2
        assert all(a["kind"] == "gateway_bypass_threshold" for a in lines)
        assert all(a["severity"] == "high" for a in lines)
        # notify 훅도 실제 호출됨.
        assert len(fired) == 2


def test_monitor_threshold_requires_count():
    """threshold=3: 동일키 우회 3건째에 발화(그 전엔 미발화)."""
    clock = {"t": 1000.0}
    mon = BypassMonitor(threshold=3, window_sec=60.0, cooldown_sec=300.0,
                        alerts_path=str(Path(tempfile.mkdtemp()) / "a.jsonl"),
                        clock=lambda: clock["t"])
    rec = {"bypass": True, "src_ip": "10.0.0.9", "process": "python3",
           "dst_host": "api.openai.com", "dst_port": 443}
    assert mon.observe(dict(rec)) is None     # 1건
    clock["t"] += 1
    assert mon.observe(dict(rec)) is None     # 2건
    clock["t"] += 1
    ev = mon.observe(dict(rec))               # 3건 → 발화
    assert ev is not None and ev.window_count == 3
    assert mon.stats["alerts"] == 1


def test_monitor_cooldown_expiry_refires():
    """suppression 쿨다운 경과 후 동일 키 재발화."""
    clock = {"t": 5000.0}
    mon = BypassMonitor(threshold=1, cooldown_sec=300.0,
                        alerts_path=str(Path(tempfile.mkdtemp()) / "a.jsonl"),
                        clock=lambda: clock["t"])
    rec = {"bypass": True, "src_ip": "10.0.0.5", "process": "curl",
           "dst_host": "api.anthropic.com", "dst_port": 443}
    assert mon.observe(dict(rec)) is not None   # 발화
    clock["t"] += 100                            # 쿨다운(300s) 내
    assert mon.observe(dict(rec)) is None        # 억제
    assert mon.stats["suppressed"] == 1
    clock["t"] += 250                            # 누적 350s > 300s → 쿨다운 만료
    assert mon.observe(dict(rec)) is not None    # 재발화
    assert mon.stats["alerts"] == 2


def test_monitor_no_bypass_is_pass():
    """우회 0건(전부 게이트웨이 경유) → PASS, 알림 없음."""
    mon = BypassMonitor(threshold=1, alerts_path=str(Path(tempfile.mkdtemp()) / "a.jsonl"))
    mon.observe_many([{"via_gateway": True, "bypass": False}] * 3)
    assert mon.stats["alerts"] == 0
    assert mon.status() == PASS


# ---------------------------------------------------------------- CLI
def test_cli_coverage_simulate_json():
    """① nufi-egress coverage --simulate → JSON 에 coverage_pct 50.0, exit 1(FAIL)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(["coverage", "--simulate", str(REPLAY), "--json"])
    out = json.loads(buf.getvalue())
    assert out["coverage_pct"] == 50.0
    assert out["status"] == "FAIL"
    assert rc == 1  # FAIL → exit 1


def test_cli_monitor_simulate_fires_alert():
    """② nufi-egress monitor --simulate burst → 알림 발화·suppression, exit 1."""
    with tempfile.TemporaryDirectory() as td:
        alerts = Path(td) / "a.jsonl"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["monitor", "--simulate", str(BURST),
                           "--threshold", "1", "--alerts", str(alerts), "--json"])
        out = json.loads(buf.getvalue())
        assert out["status"] == "FAIL"
        assert out["stats"]["alerts"] == 2
        assert out["stats"]["suppressed"] == 4
        assert rc == 1
        assert alerts.exists() and alerts.read_text(encoding="utf-8").strip()


# --------------------------------------------------------------------------- main
if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
