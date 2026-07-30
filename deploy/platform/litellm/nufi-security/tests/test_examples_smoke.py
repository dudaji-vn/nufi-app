"""examples/ 디렉터리 예시 스크립트 스모크 테스트 — 9종.

검증 항목:
  1. examples/library_detect.py — 오류 없이 실행 완료 (exit 0), KR_RRN·KR_PERSON 탐지.
  2. examples/sdk_quickstart.py — 오류 없이 실행 완료 (exit 0).
  3. examples/sdk_block_and_audit.py — 오류 없이 실행 완료 (exit 0), 403 차단 확인.
  4. examples/sdk_reversible_roundtrip.py — 오류 없이 실행 완료 (exit 0), 가역 라운드트립 확인.
  5. examples/sdk_streaming.py — 오류 없이 실행 완료 (exit 0).
  6. examples/sdk_file_scan.py — 오류 없이 실행 완료 (exit 0), scan_file·guard_file·batch_detect.
  7. examples/sdk_compliance_report.py — 오류 없이 실행 완료 (exit 0), 통제·충족 커버리지 출력.
  8. examples/sdk_security_report.py — 오류 없이 실행 완료 (exit 0), 보안 리포트 생성.
  9. examples/sdk_ci_integration.py — PII·인젝션 탐지로 exit 1, CI 결과 출력.

실행: EGRESS_NER_BACKEND=gazetteer python3 -m pytest tests/test_examples_smoke.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

results: list[tuple[str, bool, str]] = []


def check(crit: str, ok: bool, detail: str = ""):
    results.append((crit, ok, detail))
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {crit}" + (f" — {detail}" if detail else ""))


print("=== examples/ 스모크 테스트 ===\n")

# 1. library_detect.py
script = ROOT / "examples" / "library_detect.py"
proc = subprocess.run(
    [sys.executable, str(script)],
    capture_output=True,
    text=True,
    env={"EGRESS_NER_BACKEND": "gazetteer", "PATH": "/usr/bin:/bin"},
)
check(
    "library_detect.py exit 0",
    proc.returncode == 0,
    f"rc={proc.returncode}" + (f" stderr={proc.stderr[:200]}" if proc.returncode != 0 else ""),
)
if proc.returncode == 0:
    check(
        "library_detect.py KR_RRN 탐지 출력 포함",
        "KR_RRN" in proc.stdout,
        "stdout에 KR_RRN 없음" if "KR_RRN" not in proc.stdout else "",
    )
    check(
        "library_detect.py KR_PERSON 탐지 출력 포함",
        "KR_PERSON" in proc.stdout,
        "stdout에 KR_PERSON 없음" if "KR_PERSON" not in proc.stdout else "",
    )

def _run_example(name: str) -> subprocess.CompletedProcess:
    import os as _os
    env = {**_os.environ, "EGRESS_NER_BACKEND": "gazetteer"}
    return subprocess.run(
        [sys.executable, str(ROOT / "examples" / name)],
        capture_output=True,
        text=True,
        env=env,
    )


# 2. sdk_quickstart.py
proc2 = _run_example("sdk_quickstart.py")
check(
    "sdk_quickstart.py exit 0",
    proc2.returncode == 0,
    f"rc={proc2.returncode}" + (f" stderr={proc2.stderr[:200]}" if proc2.returncode != 0 else ""),
)

# 3. sdk_block_and_audit.py
proc3 = _run_example("sdk_block_and_audit.py")
check(
    "sdk_block_and_audit.py exit 0",
    proc3.returncode == 0,
    f"rc={proc3.returncode}" + (f" stderr={proc3.stderr[:200]}" if proc3.returncode != 0 else ""),
)
if proc3.returncode == 0:
    check(
        "sdk_block_and_audit.py 403 차단 확인",
        "403" in proc3.stdout or "차단" in proc3.stdout,
        "stdout에 차단 신호 없음" if ("403" not in proc3.stdout and "차단" not in proc3.stdout) else "",
    )

# 4. sdk_reversible_roundtrip.py
proc4 = _run_example("sdk_reversible_roundtrip.py")
check(
    "sdk_reversible_roundtrip.py exit 0",
    proc4.returncode == 0,
    f"rc={proc4.returncode}" + (f" stderr={proc4.stderr[:200]}" if proc4.returncode != 0 else ""),
)
if proc4.returncode == 0:
    check(
        "sdk_reversible_roundtrip.py 라운드트립 확인",
        "OK" in proc4.stdout or "라운드트립" in proc4.stdout,
        "stdout에 OK 없음" if ("OK" not in proc4.stdout and "라운드트립" not in proc4.stdout) else "",
    )

# 5. sdk_streaming.py
proc5 = _run_example("sdk_streaming.py")
check(
    "sdk_streaming.py exit 0",
    proc5.returncode == 0,
    f"rc={proc5.returncode}" + (f" stderr={proc5.stderr[:200]}" if proc5.returncode != 0 else ""),
)

# 6. sdk_file_scan.py
proc6 = _run_example("sdk_file_scan.py")
check(
    "sdk_file_scan.py exit 0",
    proc6.returncode == 0,
    f"rc={proc6.returncode}" + (f" stderr={proc6.stderr[:200]}" if proc6.returncode != 0 else ""),
)
if proc6.returncode == 0:
    check(
        "sdk_file_scan.py scan_file 탐지 출력 포함",
        "KR_RRN" in proc6.stdout or "KR_PERSON" in proc6.stdout,
        "stdout에 탐지 결과 없음" if ("KR_RRN" not in proc6.stdout and "KR_PERSON" not in proc6.stdout) else "",
    )

# 7. sdk_compliance_report.py
proc7 = _run_example("sdk_compliance_report.py")
check(
    "sdk_compliance_report.py exit 0",
    proc7.returncode == 0,
    f"rc={proc7.returncode}" + (f" stderr={proc7.stderr[:200]}" if proc7.returncode != 0 else ""),
)
if proc7.returncode == 0:
    check(
        "sdk_compliance_report.py 카탈로그 출력 포함",
        "통제" in proc7.stdout and ("충족" in proc7.stdout or "ISMS" in proc7.stdout),
        "stdout에 통제 커버리지 없음",
    )

# 결과 집계
print()
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
print(f"결과: {passed} PASS / {failed} FAIL")
if failed:
    sys.exit(1)


# --- pytest 수집용 래퍼 ---

import os as _os  # noqa: E402


def test_library_detect_runs():
    """examples/library_detect.py 가 오류 없이 실행되는지 검증."""
    env = {**_os.environ, "EGRESS_NER_BACKEND": "gazetteer"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "library_detect.py")],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"exit {result.returncode}: {result.stderr[:300]}"
    assert "KR_RRN" in result.stdout
    assert "KR_PERSON" in result.stdout


def test_sdk_quickstart_runs():
    """examples/sdk_quickstart.py 가 오류 없이 실행되는지 검증."""
    env = {**_os.environ, "EGRESS_NER_BACKEND": "gazetteer"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "sdk_quickstart.py")],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"exit {result.returncode}: {result.stderr[:300]}"


def test_sdk_block_and_audit_runs():
    """examples/sdk_block_and_audit.py 가 오류 없이 실행되고 403 차단을 확인."""
    env = {**_os.environ, "EGRESS_NER_BACKEND": "gazetteer"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "sdk_block_and_audit.py")],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"exit {result.returncode}: {result.stderr[:300]}"
    assert "403" in result.stdout or "차단" in result.stdout


def test_sdk_reversible_roundtrip_runs():
    """examples/sdk_reversible_roundtrip.py 가 오류 없이 실행되고 가역 라운드트립을 확인."""
    env = {**_os.environ, "EGRESS_NER_BACKEND": "gazetteer"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "sdk_reversible_roundtrip.py")],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"exit {result.returncode}: {result.stderr[:300]}"
    assert "OK" in result.stdout or "라운드트립" in result.stdout


def test_sdk_streaming_runs():
    """examples/sdk_streaming.py 가 오류 없이 실행되는지 검증."""
    env = {**_os.environ, "EGRESS_NER_BACKEND": "gazetteer"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "sdk_streaming.py")],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"exit {result.returncode}: {result.stderr[:300]}"


def test_sdk_file_scan_runs():
    """examples/sdk_file_scan.py 가 오류 없이 실행되고 scan_file 탐지를 확인."""
    env = {**_os.environ, "EGRESS_NER_BACKEND": "gazetteer"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "sdk_file_scan.py")],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"exit {result.returncode}: {result.stderr[:300]}"
    assert "KR_RRN" in result.stdout or "KR_PERSON" in result.stdout


def test_sdk_compliance_report_runs():
    """examples/sdk_compliance_report.py 가 오류 없이 실행되고 통제 커버리지를 출력한다."""
    env = {**_os.environ, "EGRESS_NER_BACKEND": "gazetteer"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "sdk_compliance_report.py")],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"exit {result.returncode}: {result.stderr[:300]}"
    assert "통제" in result.stdout
    assert "충족" in result.stdout or "ISMS" in result.stdout


def test_sdk_security_report_runs():
    """examples/sdk_security_report.py 가 오류 없이 실행되고 리포트를 출력한다."""
    env = {**_os.environ, "EGRESS_NER_BACKEND": "gazetteer"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "sdk_security_report.py")],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"exit {result.returncode}: {result.stderr[:300]}"
    assert "보안 리포트" in result.stdout or "Security" in result.stdout
    assert "risk_level" in result.stdout


def test_sdk_ci_integration_runs():
    """examples/sdk_ci_integration.py 가 오류 없이 실행되고 CI 결과를 출력한다."""
    env = {**_os.environ, "EGRESS_NER_BACKEND": "gazetteer"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "sdk_ci_integration.py")],
        capture_output=True,
        text=True,
        env=env,
    )
    # Exit code 1 is expected (PII + injection detected in demo files)
    assert result.returncode == 1, f"exit {result.returncode}: {result.stderr[:300]}"
    assert "PASS" in result.stdout
    assert "FAIL" in result.stdout
    assert "Exit code: 1" in result.stdout
