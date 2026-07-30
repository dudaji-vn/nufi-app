"""Tests for enforcement/dashboard_cmd.py (patch174)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from enforcement.dashboard_cmd import render_dashboard


def test_dashboard_contains_expected_sections():
    """Dashboard output must include header, grade, activity, injection sections."""
    output = render_dashboard()

    # Box-drawing characters present
    assert "\u2554" in output  # top-left corner
    assert "\u255a" in output  # bottom-left corner
    assert "\u2560" in output  # mid-left separator

    # Key sections
    assert "NuFi Security Dashboard" in output
    assert "Grade:" in output
    assert "Doctor:" in output
    assert "Recent Activity:" in output
    assert "Injection:" in output


def test_dashboard_json_mode():
    """JSON mode returns valid JSON with expected keys."""
    output = render_dashboard(json_mode=True)
    data = json.loads(output)
    assert "version" in data
    assert "summary" in data
    assert "posture" in data
