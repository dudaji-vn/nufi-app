"""Tests for Guard context manager support (patch172)."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from egress_audit.guard import EgressGuard
import nufi


def test_guard_context_manager():
    """EgressGuard supports `with` statement and guard_context helper."""
    # Direct usage
    with EgressGuard(check_injection=False) as g:
        result = g.inspect("hello world")
        assert result.blocked is False

    # Convenience helper from nufi
    with nufi.guard_context(check_injection=False) as g:
        result = g.inspect("hello world")
        assert result.blocked is False
