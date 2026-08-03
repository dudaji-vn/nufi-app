"""patch143: Verify SDK py.typed marker and type annotations exist."""
from __future__ import annotations

import pathlib
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_py_typed_marker_exists():
    """PEP 561: nufi/py.typed marker file must exist so type checkers
    recognise the package as typed."""
    marker = _ROOT / "nufi" / "py.typed"
    assert marker.exists(), (
        f"Missing PEP 561 marker: {marker}  — "
        "IDE type checkers will not recognise nufi as a typed package"
    )
