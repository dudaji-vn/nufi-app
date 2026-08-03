"""patch109: nufi-egress completions 서브커맨드 테스트.

검증:
  1. completions bash 출력에 모든 서브커맨드 이름이 포함된다.

실행: pytest tests/test_completions.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from enforcement.cli import main  # noqa: E402


EXPECTED_SUBCOMMANDS = [
    "scan", "route", "inspect", "diff",
    "watch", "init", "config", "doctor", "version",
    "report", "benchmark", "completions",
]


class TestCompletionsBash:
    """nufi-egress completions bash 출력 검증."""

    def test_bash_contains_all_subcommands(self, capsys):
        """bash completion 스크립트에 모든 서브커맨드 이름이 포함된다."""
        rc = main(["completions", "bash"])
        assert rc == 0
        output = capsys.readouterr().out
        for cmd in EXPECTED_SUBCOMMANDS:
            assert cmd in output, f"subcommand {cmd!r} not found in bash completion output"
