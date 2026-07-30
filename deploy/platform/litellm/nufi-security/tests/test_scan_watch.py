"""tests/test_scan_watch.py — scan --watch 실시간 파일 모니터링 테스트 (v0.7.3).

시나리오:
1. watch 모드 시작/종료 (polling fallback)
2. 파일 변경 감지 → 스캔 실행
3. 폴링 fallback 테스트 (watchdog 미설치 시)
4. --watch-interval 옵션 테스트
5. --format json 출력
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from enforcement.scan_cmd import (
    scan_watch,
    _watch_with_polling,
    _collect_watchable_files,
    _format_watch_event,
    ScanResult,
    ScanFinding,
    load_nufiignore,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def watch_dir(tmp_path: Path) -> Path:
    """감시할 디렉터리 (초기 파일 포함)."""
    (tmp_path / "clean.txt").write_text("Hello world\n", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def pii_content() -> str:
    return "홍길동 주민번호 900101-1234567\n"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_watch_requires_directory():
    """watch 모드에 존재하지 않는 경로를 지정하면 exit code 2."""
    code = scan_watch("/nonexistent/path", _stop_after=0)
    assert code == 2


def test_watch_polling_starts_and_stops(watch_dir: Path, capsys):
    """polling 모드로 시작 후 _stop_after 로 종료."""
    code = _watch_with_polling(
        watch_dir,
        interval=0.05,
        check_injection=False,
        patterns=None,
        exclude_patterns=[],
        output_format=None,
        _stop_after=2,
    )
    assert code == 0
    captured = capsys.readouterr()
    assert "[watch] Monitoring" in captured.out
    assert "polling" in captured.out


def test_watch_detects_new_file(watch_dir: Path, pii_content: str, capsys):
    """신규 파일 생성 시 PII 를 감지한다."""
    def _create_file():
        time.sleep(0.2)
        (watch_dir / "secret.txt").write_text(pii_content, encoding="utf-8")

    t = threading.Thread(target=_create_file)
    t.start()

    _watch_with_polling(
        watch_dir,
        interval=0.1,
        check_injection=False,
        patterns=None,
        exclude_patterns=[],
        output_format=None,
        _stop_after=10,
    )
    t.join()

    captured = capsys.readouterr()
    # Should detect PII in the new file
    assert "PII:" in captured.out or "secret.txt" in captured.out


def test_watch_detects_modified_file(watch_dir: Path, pii_content: str, capsys):
    """기존 파일 수정 시 PII 를 감지한다."""
    target = watch_dir / "clean.txt"

    def _modify_file():
        time.sleep(0.2)
        target.write_text(pii_content, encoding="utf-8")

    t = threading.Thread(target=_modify_file)
    t.start()

    _watch_with_polling(
        watch_dir,
        interval=0.1,
        check_injection=False,
        patterns=None,
        exclude_patterns=[],
        output_format=None,
        _stop_after=10,
    )
    t.join()

    captured = capsys.readouterr()
    assert "PII:" in captured.out or "clean.txt" in captured.out


def test_watch_json_format(watch_dir: Path, pii_content: str, capsys):
    """--format json 시 JSON 으로 출력한다."""
    target = watch_dir / "clean.txt"

    def _modify_file():
        time.sleep(0.1)
        target.write_text(pii_content, encoding="utf-8")

    t = threading.Thread(target=_modify_file)
    t.start()

    _watch_with_polling(
        watch_dir,
        interval=0.1,
        check_injection=False,
        patterns=None,
        exclude_patterns=[],
        output_format="json",
        _stop_after=5,
    )
    t.join()

    captured = capsys.readouterr()
    # Extract JSON lines (skip the [watch] header)
    json_lines = [
        line for line in captured.out.strip().splitlines()
        if line.startswith("{")
    ]
    assert len(json_lines) >= 1, "Expected at least one JSON event line"
    event = json.loads(json_lines[0])
    assert "timestamp" in event
    assert "file" in event
    assert "findings" in event
    assert len(event["findings"]) >= 1


def test_watch_interval_respected(watch_dir: Path, capsys):
    """--watch-interval 값이 반영된다."""
    import time as _time
    start = _time.monotonic()
    _watch_with_polling(
        watch_dir,
        interval=0.1,
        check_injection=False,
        patterns=None,
        exclude_patterns=[],
        output_format=None,
        _stop_after=2,
    )
    elapsed = _time.monotonic() - start
    # Should have waited at least 2 * 0.1 = 0.2 seconds
    assert elapsed >= 0.15


def test_watch_polling_fallback(watch_dir: Path, capsys):
    """watchdog 이 없을 때 polling 으로 fallback 한다."""
    with patch.dict("sys.modules", {"watchdog": None, "watchdog.observers": None, "watchdog.events": None}):
        code = scan_watch(
            watch_dir,
            interval=0.05,
            _stop_after=1,
        )
    assert code == 0
    captured = capsys.readouterr()
    assert "polling" in captured.out


def test_collect_watchable_files(watch_dir: Path):
    """_collect_watchable_files 는 비이진 파일만 수집한다."""
    # Add a binary file
    (watch_dir / "image.bin").write_bytes(b"\x00\x01\x02\x03" * 200)
    files = _collect_watchable_files(watch_dir, patterns=None, exclude_patterns=[])
    names = {f.name for f in files}
    assert "clean.txt" in names
    assert "image.bin" not in names


def test_format_watch_event_text():
    """text 포맷 이벤트 출력 형식 확인."""
    result = ScanResult(
        files_scanned=1,
        files_with_findings=1,
        findings=[ScanFinding(
            file="/tmp/test.txt",
            line=1,
            finding_type="PII:KR_RRN",
            text="900101-1234567",
        )],
    )
    output = _format_watch_event(
        Path("/tmp/test.txt"), result, None, "2026-07-08T00:00:00Z"
    )
    assert "2026-07-08T00:00:00Z" in output
    assert "/tmp/test.txt" in output
    assert "PII:KR_RRN" in output


def test_format_watch_event_json():
    """json 포맷 이벤트 출력 형식 확인."""
    result = ScanResult(
        files_scanned=1,
        files_with_findings=1,
        findings=[ScanFinding(
            file="/tmp/test.txt",
            line=1,
            finding_type="PII:KR_RRN",
            text="900101-1234567",
        )],
    )
    output = _format_watch_event(
        Path("/tmp/test.txt"), result, "json", "2026-07-08T00:00:00Z"
    )
    event = json.loads(output)
    assert event["timestamp"] == "2026-07-08T00:00:00Z"
    assert event["file"] == "/tmp/test.txt"
    assert len(event["findings"]) == 1
    assert event["findings"][0]["finding_type"] == "PII:KR_RRN"


def test_watch_excludes_patterns(watch_dir: Path, pii_content: str, capsys):
    """exclude 패턴이 watch 모드에서도 적용된다."""
    (watch_dir / "secret.log").write_text(pii_content, encoding="utf-8")

    def _create_file():
        time.sleep(0.05)
        (watch_dir / "data.log").write_text(pii_content, encoding="utf-8")

    t = threading.Thread(target=_create_file)
    t.start()

    _watch_with_polling(
        watch_dir,
        interval=0.05,
        check_injection=False,
        patterns=None,
        exclude_patterns=["*.log"],
        output_format=None,
        _stop_after=3,
    )
    t.join()

    captured = capsys.readouterr()
    # .log files should be excluded — no PII alerts for them
    assert "data.log" not in captured.out
