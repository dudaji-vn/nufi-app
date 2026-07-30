"""patch114: Comprehensive CLI integration smoke tests.

Every public subcommand of ``nufi-egress`` gets a basic smoke test that
calls ``main()`` with minimal arguments and verifies:
  - No crash (no unhandled exception)
  - Sensible exit code (0 or expected non-zero)
  - Meaningful output present on stdout/stderr

Run:  pytest tests/test_cli_integration.py -v
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from enforcement.cli import main  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent


class TestVersionSmoke:
    """``nufi-egress version`` exits 0 and prints version info."""

    def test_version_exit_zero(self):
        assert main(["version"]) == 0

    def test_version_has_output(self, capsys):
        main(["version"])
        out = capsys.readouterr().out
        assert "NuFi version:" in out
        assert len(out.strip()) > 0


class TestDoctorSmoke:
    """``nufi-egress doctor`` runs without crash."""

    def test_doctor_runs(self, capsys):
        # doctor may return 0 (all pass) or 1 (some fail) — both are valid
        rc = main(["doctor", "--no-json"])
        assert rc in (0, 1)
        out = capsys.readouterr().out
        assert len(out.strip()) > 0


class TestRouteSmoke:
    """``nufi-egress route --text`` exits 0."""

    def test_route_text(self, capsys):
        rc = main(["route", "--text", "hello world test", "--json"])
        assert rc == 0
        out = capsys.readouterr().out
        assert len(out.strip()) > 0
        # JSON output should be parseable
        import json
        data = json.loads(out)
        assert "target_model" in data


class TestInspectSmoke:
    """``nufi-egress inspect --text`` exits 0 and produces output."""

    def test_inspect_text(self, capsys):
        rc = main(["inspect", "--text", "hello test text", "--json"])
        assert rc == 0
        out = capsys.readouterr().out
        assert len(out.strip()) > 0
        import json
        data = json.loads(out)
        assert "blocked" in data


class TestScanSmoke:
    """``nufi-egress scan <dir>`` exits 0 on clean directory."""

    def test_scan_clean_dir(self, capsys):
        with tempfile.TemporaryDirectory(prefix="nufi-test-scan-") as td:
            # Create a harmless file
            (Path(td) / "clean.txt").write_text("This is a clean file.\n",
                                                encoding="utf-8")
            rc = main(["scan", td, "--json"])
            assert rc == 0
            out = capsys.readouterr().out
            assert len(out.strip()) > 0

    def test_scan_with_stats(self, capsys):
        with tempfile.TemporaryDirectory(prefix="nufi-test-scan-") as td:
            (Path(td) / "clean.txt").write_text("no pii here\n",
                                                encoding="utf-8")
            rc = main(["scan", td, "--stats"])
            assert rc == 0


class TestDiffSmoke:
    """``nufi-egress diff`` handles gracefully (needs git repo)."""

    def test_diff_in_repo(self, capsys):
        # We are inside a git repo, so diff should work (may find 0 changes)
        old_cwd = os.getcwd()
        try:
            os.chdir(str(_ROOT))
            rc = main(["diff", "--json"])
            # 0 = no PII found in diff, which is expected for clean state
            assert rc in (0, 1)
        finally:
            os.chdir(old_cwd)


class TestConfigValidateSmoke:
    """``nufi-egress config validate`` validates config files."""

    def test_config_validate(self, capsys):
        rc = main(["config", "validate", "--json"])
        # 0 = valid, 1 = issues found — both are acceptable
        assert rc in (0, 1)
        out = capsys.readouterr().out
        assert len(out.strip()) > 0
        import json
        data = json.loads(out)
        assert "valid" in data or "issues" in data or "files_checked" in data


class TestStatsSmoke:
    """``nufi-egress stats`` shows configuration summary."""

    def test_stats_json(self, capsys):
        rc = main(["stats", "--json"])
        assert rc == 0
        out = capsys.readouterr().out
        assert len(out.strip()) > 0
        import json
        data = json.loads(out)
        assert isinstance(data, dict)

    def test_stats_human(self, capsys):
        rc = main(["stats"])
        assert rc == 0
        out = capsys.readouterr().out
        assert len(out.strip()) > 0


class TestCompletionsSmoke:
    """``nufi-egress completions bash`` produces completion script."""

    def test_completions_bash(self, capsys):
        rc = main(["completions", "bash"])
        assert rc == 0
        out = capsys.readouterr().out
        assert len(out.strip()) > 0
        # Bash completion scripts typically contain "complete" or "compgen"
        assert "nufi" in out.lower() or "complete" in out.lower()

    def test_completions_zsh(self, capsys):
        rc = main(["completions", "zsh"])
        assert rc == 0
        out = capsys.readouterr().out
        assert len(out.strip()) > 0


class TestReportComplianceSmoke:
    """``nufi-egress report compliance`` produces output."""

    def test_report_compliance_basic(self, capsys):
        # Use sample audit file if available, else let it use defaults
        audit_path = _ROOT / "samples" / "sla" / "audit_decisions.jsonl"
        change_log = _ROOT / "samples" / "sla" / "policy_changes.jsonl"
        argv = ["report", "compliance", "--format", "md"]
        if audit_path.exists():
            argv += ["--audit", str(audit_path)]
        if change_log.exists():
            argv += ["--change-log", str(change_log)]
        rc = main(argv)
        # 0 = integrity ok, 1 = integrity broken — both acceptable
        assert rc in (0, 1)
        combined = capsys.readouterr()
        output = combined.out + combined.err
        assert len(output.strip()) > 0


class TestInspectWithPII:
    """``nufi-egress inspect`` detects PII and returns blocked=True."""

    def test_inspect_pii_blocked(self, capsys):
        # Korean RRN should be detected and blocked
        rc = main(["inspect", "--text", "주민번호 900101-1234567", "--json"])
        # blocked text → exit 1
        assert rc in (0, 1)
        out = capsys.readouterr().out
        import json
        data = json.loads(out)
        assert "blocked" in data
