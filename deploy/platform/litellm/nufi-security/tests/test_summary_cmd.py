"""Tests for ``nufi-egress summary`` project dashboard (patch147)."""
from __future__ import annotations

import json

import pytest

from enforcement.summary_cmd import collect_summary, render_human, cmd_summary


class TestCollectSummary:
    """collect_summary returns well-structured data."""

    def test_returns_expected_keys(self):
        summary = collect_summary()
        assert "version" in summary
        assert "python" in summary
        assert "config" in summary
        assert "recent_activity" in summary
        assert "doctor" in summary
        assert "ts" in summary

    def test_version_is_string(self):
        summary = collect_summary()
        assert isinstance(summary["version"], str)
        assert summary["version"] != ""


class TestRenderHuman:
    """render_human produces readable output."""

    def test_contains_header(self):
        summary = collect_summary()
        text = render_human(summary)
        assert "NuFi Project Health Dashboard" in text
        assert "[Config]" in text
        assert "[Doctor]" in text
        assert "[Recent Activity]" in text


class TestCmdSummary:
    """CLI handler integration."""

    def test_json_output(self, capsys):
        class Args:
            json = True

        rc = cmd_summary(Args())
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "version" in data
        assert "config" in data
        assert "doctor" in data

    def test_human_output(self, capsys):
        class Args:
            json = False

        rc = cmd_summary(Args())
        assert rc == 0
        out = capsys.readouterr().out
        assert "NuFi Project Health Dashboard" in out
