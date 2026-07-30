"""Tests for ``nufi-egress history`` activity log (patch141)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from enforcement.history_cmd import read_history, render_human, cmd_history


class TestReadHistory:
    """read_history with mock log data."""

    def test_mixed_events_and_filter(self, tmp_path: Path):
        """Reads audit log, classifies events, filters by type."""
        audit = tmp_path / "audit.jsonl"
        records = [
            {"ts": "2026-07-05T10:00:00", "outcome": "blocked", "findings": [{"entity_type": "PERSON"}]},
            {"ts": "2026-07-05T10:01:00", "outcome": "allowed", "routed_to_local": False, "target_model": "cloud"},
            {"ts": "2026-07-05T10:02:00", "outcome": "allowed", "findings": [{"entity_type": "SSN"}], "finding_count": 1},
        ]
        audit.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")

        # All events
        all_events = read_history(last=20, event_type="all", audit_path=str(audit))
        assert len(all_events) == 3

        # Filter block only
        blocks = read_history(last=20, event_type="block", audit_path=str(audit))
        assert len(blocks) == 1
        assert blocks[0]["_type"] == "block"

        # Filter route only
        routes = read_history(last=20, event_type="route", audit_path=str(audit))
        assert len(routes) == 1
        assert routes[0]["_type"] == "route"

    def test_no_logs_shows_empty(self, tmp_path: Path):
        """When no log files exist, returns empty list and renders message."""
        events = read_history(
            last=20,
            event_type="all",
            audit_path=str(tmp_path / "nonexistent.jsonl"),
            cache_path=str(tmp_path / "nonexistent.json"),
        )
        assert events == []
        text = render_human(events)
        assert "No activity recorded yet" in text


class TestCmdHistory:
    """CLI handler integration."""

    def test_json_output(self, tmp_path: Path, monkeypatch, capsys):
        """--json produces valid JSON output."""
        audit = tmp_path / "audit.jsonl"
        records = [
            {"ts": "2026-07-05T11:00:00", "outcome": "blocked", "findings": []},
            {"ts": "2026-07-05T11:01:00", "outcome": "allowed", "routed_to_local": True, "target_model": "local"},
        ]
        audit.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")

        # Monkey-patch read_history to use our temp audit path
        import enforcement.history_cmd as hmod
        orig = hmod.read_history

        def patched_read(last=20, event_type="all", audit_path=None, cache_path=None):
            return orig(last=last, event_type=event_type,
                        audit_path=str(audit), cache_path=str(tmp_path / "no.json"))

        monkeypatch.setattr(hmod, "read_history", patched_read)

        class Args:
            last = 20
            type = "all"
            json = True

        rc = cmd_history(Args())
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == 2
        # Each entry should have "type" and "source" fields
        assert all("type" in e for e in data)
        assert all("source" in e for e in data)
