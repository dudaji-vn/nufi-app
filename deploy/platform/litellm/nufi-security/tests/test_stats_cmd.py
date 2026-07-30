"""Tests for ``nufi-egress stats`` (patch112)."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from enforcement.stats_cmd import collect_stats, render_human, StatsResult


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with config files."""
    config = tmp_path / "config"
    config.mkdir()

    # patterns.yaml
    (config / "patterns.yaml").write_text(textwrap.dedent("""\
        version: 1
        korean_pii:
          - name: KR_RRN
            regex: 'dummy'
            checksum: rrn
          - name: KR_PHONE
            regex: 'dummy'
            checksum: none
        secrets:
          - name: AWS_ACCESS_KEY
            regex: 'dummy'
    """), encoding="utf-8")

    # injection_patterns.yaml
    (config / "injection_patterns.yaml").write_text(textwrap.dedent("""\
        custom_patterns:
          - pattern: "test pattern"
            severity: high
          - pattern: "another"
            severity: low
    """), encoding="utf-8")

    # scan_profiles.yaml
    (config / "scan_profiles.yaml").write_text(textwrap.dedent("""\
        scan_profiles:
          ci:
            check_injection: true
          strict:
            fail_on_pii: true
    """), encoding="utf-8")

    # policy.yaml
    (config / "policy.yaml").write_text("version: 1\ndefault_action: block\nentities: {}\n",
                                         encoding="utf-8")

    # .nufiignore
    (tmp_path / ".nufiignore").write_text(textwrap.dedent("""\
        # comment
        *.pyc
        __pycache__/**
        logs/**
    """), encoding="utf-8")

    # audit log
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "egress_audit.jsonl").write_text(
        '{"ts":"2026-07-01T10:00:00","outcome":"forwarded"}\n'
        '{"ts":"2026-07-03T15:30:00","outcome":"blocked"}\n',
        encoding="utf-8",
    )

    return tmp_path


class TestCollectStats:
    def test_basic_stats(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path)
        stats = collect_stats(root)

        # Config files
        assert len(stats.config_files) > 0
        policy = next(cf for cf in stats.config_files if "policy.yaml" in cf["file"])
        assert policy["exists"] is True

        # PII patterns
        assert stats.pii_pattern_count == 2
        assert stats.secret_pattern_count == 1

        # Custom injection patterns
        assert stats.custom_injection_pattern_count == 2

        # Scan profiles
        assert sorted(stats.scan_profiles) == ["ci", "strict"]

        # .nufiignore
        assert stats.nufiignore_pattern_count == 3  # excludes comment and blank lines

        # Audit log
        assert stats.audit_log_exists is True
        assert stats.audit_log_lines == 2
        assert stats.audit_log_first_ts == "2026-07-01T10:00:00"
        assert stats.audit_log_last_ts == "2026-07-03T15:30:00"

    def test_missing_files(self, tmp_path: Path) -> None:
        """Stats should work even with no config files at all."""
        stats = collect_stats(tmp_path)
        assert stats.pii_pattern_count == 0
        assert stats.audit_log_exists is False
        assert stats.nufiignore_pattern_count == 0

    def test_to_dict(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path)
        stats = collect_stats(root)
        d = stats.to_dict()

        assert "config_files" in d
        assert d["detection"]["pii_patterns"] == 2
        assert d["audit_log"]["exists"] is True
        assert d["audit_log"]["lines"] == 2
        # Ensure JSON-serializable
        json.dumps(d)

    def test_render_human(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path)
        stats = collect_stats(root)
        text = render_human(stats)

        assert "NuFi Stats" in text
        assert "PII patterns" in text
        assert "Scan Profiles" in text
        assert "ci" in text
        assert "strict" in text
        assert "Audit Log" in text
        assert "2026-07-01" in text


class TestStatsCLI:
    def test_cli_json(self, tmp_path: Path) -> None:
        """Test CLI integration via main()."""
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch as mock_patch

        root = _make_project(tmp_path)

        # Patch _ROOT so collect_stats uses our tmp project
        with mock_patch("enforcement.stats_cmd._ROOT", root):
            from enforcement.cli import main
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["stats", "--json"])
            assert rc == 0
            data = json.loads(buf.getvalue())
            assert "detection" in data
            assert "audit_log" in data
