"""Injection detection benchmark 통과 여부 테스트 (patch72)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_bench_injection_passes():
    """bench_injection.py 가 recall >= 0.90, precision >= 0.90 으로 통과해야 한다."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "bench_injection.py")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, (
        f"Benchmark failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
