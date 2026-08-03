"""Tests for ``nufi-egress pipeline`` (patch139)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from enforcement.pipeline_cmd import run_pipeline, ALL_ACTIONS


class TestRunPipeline:
    """Unit tests for run_pipeline()."""

    def test_full_pipeline_with_pii(self):
        """Full pipeline on text containing PII returns all steps."""
        text = "김민수님 주민번호 900101-1234568"
        result = run_pipeline(text)

        # All default actions should have populated keys
        assert result["input"] == text
        assert "detect" in result
        assert "block_check" in result
        assert "route" in result
        assert "transformed_text" in result

        # PII should be detected
        assert result["detect"]["pii_count"] >= 1

        # Strong PII (KR_RRN) -> critical -> blocked
        assert result["block_check"]["blocked"] is True

        # Route should be local (PII detected)
        assert result["route"]["target"] == "local"

    def test_selective_actions(self):
        """Pipeline with subset of actions only runs requested steps."""
        text = "오늘 날씨 좋네요"
        result = run_pipeline(text, actions=["detect", "route"])

        assert "detect" in result
        assert "route" in result
        # These should NOT be present since not requested
        assert "block_check" not in result
        assert "transform" not in result

        # No PII in clean text
        assert result["detect"]["pii_count"] == 0
        assert result["route"]["target"] == "cloud"


class TestPipelineCLI:
    """Integration tests for CLI entry point."""

    def test_cli_json_output(self):
        """``nufi-egress pipeline --text ... --json`` produces valid JSON."""
        from enforcement.cli import main

        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["pipeline", "--text", "김민수님 전화 010-1234-5678", "--json"])
        assert rc == 0

        output = json.loads(buf.getvalue())
        assert "detect" in output
        assert "block_check" in output
        assert output["detect"]["pii_count"] >= 1

    def test_cli_selective_actions(self):
        """``--actions detect,route`` limits pipeline steps."""
        from enforcement.cli import main

        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["pipeline", "--text", "안녕하세요", "--actions", "detect,route", "--json"])
        assert rc == 0

        output = json.loads(buf.getvalue())
        assert "detect" in output
        assert "route" in output
        assert "block_check" not in output
