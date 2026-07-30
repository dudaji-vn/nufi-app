"""patch81: nufi-egress version 서브커맨드 테스트.

검증:
  1. version 서브커맨드가 exit 0 반환
  2. 출력에 NuFi version, Python, KoELECTRA ONNX, Injection patterns 포함
  3. --version 플래그가 SystemExit(0) 발생

실행: pytest tests/test_cli_version.py -v
"""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from enforcement.cli import main, cmd_version  # noqa: E402


class TestVersionSubcommand:
    """nufi-egress version 서브커맨드."""

    def test_version_subcommand_exit_zero(self):
        """version 서브커맨드가 exit 0 반환."""
        rc = main(["version"])
        assert rc == 0

    def test_version_subcommand_output(self, capsys):
        """version 출력에 핵심 정보 포함."""
        main(["version"])
        captured = capsys.readouterr()
        assert "NuFi version:" in captured.out
        assert "Python:" in captured.out
        assert "KoELECTRA ONNX:" in captured.out
        assert "Injection patterns:" in captured.out

    def test_version_flag(self):
        """--version 플래그가 SystemExit(0) 발생."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
