"""Global pytest fixtures for NuFi test suite."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _set_egress_ner_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure EGRESS_NER_BACKEND=gazetteer for all tests."""
    monkeypatch.setenv("EGRESS_NER_BACKEND", "gazetteer")
