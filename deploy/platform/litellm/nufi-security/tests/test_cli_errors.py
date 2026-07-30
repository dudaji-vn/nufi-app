"""patch144: CLI error message quality tests.

Verify that common user mistakes produce friendly, actionable error
messages instead of raw stack traces or cryptic argparse output.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from enforcement.cli import main  # noqa: E402


class TestRouteWithoutInput:
    """``nufi-egress route`` without --text/--file/--stdin shows a helpful error."""

    def test_route_no_input_shows_error(self, capsys):
        rc = main(["route"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "Error" in err
        assert "--text" in err

    def test_route_no_input_suggests_alternatives(self, capsys):
        rc = main(["route"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "--file" in err or "--stdin" in err


class TestGlobalExceptionHandler:
    """Global exception handler catches common errors gracefully."""

    def test_keyboard_interrupt_handled(self, monkeypatch, capsys):
        """KeyboardInterrupt during command execution returns 130, no traceback."""
        def _raise_interrupt(args):
            raise KeyboardInterrupt

        rc = main.__wrapped__(["version"]) if hasattr(main, "__wrapped__") else None
        # Directly test via monkeypatching cmd_version
        import enforcement.cli as cli_mod
        original = cli_mod.cmd_version
        cli_mod.cmd_version = _raise_interrupt
        try:
            rc = main(["version"])
            assert rc == 130
            captured = capsys.readouterr()
            assert "Traceback" not in (captured.out + captured.err)
            assert "Interrupted" in captured.err
        finally:
            cli_mod.cmd_version = original

    def test_generic_exception_handled(self, monkeypatch, capsys):
        """Unexpected exceptions produce a clean error, not a traceback."""
        import enforcement.cli as cli_mod
        original = cli_mod.cmd_version

        def _raise_generic(args):
            raise RuntimeError("something went wrong")

        cli_mod.cmd_version = _raise_generic
        try:
            rc = main(["version"])
            assert rc == 1
            captured = capsys.readouterr()
            assert "Traceback" not in (captured.out + captured.err)
            assert "something went wrong" in captured.err
        finally:
            cli_mod.cmd_version = original
