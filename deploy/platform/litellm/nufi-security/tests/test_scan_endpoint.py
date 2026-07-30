"""Tests for POST /scan endpoint (patch173)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi.testclient import TestClient

from enforcement.serve_cmd import create_app


client = TestClient(create_app())


def test_scan_endpoint_basic(monkeypatch, tmp_path):
    """POST /scan returns scan results for a valid directory."""
    # Create a test file with PII
    test_file = tmp_path / "data.txt"
    test_file.write_text("전화번호: 010-1234-5678", encoding="utf-8")

    # Monkeypatch CWD so the path is allowed
    monkeypatch.chdir(tmp_path)

    resp = client.post("/scan", json={"path": str(tmp_path), "check_injection": False, "fail_on_pii": True})
    assert resp.status_code == 200
    data = resp.json()
    assert "files_scanned" in data
    assert "findings" in data
    assert "risk_level" in data
    assert data["files_scanned"] >= 1


def test_scan_endpoint_path_traversal(monkeypatch, tmp_path):
    """POST /scan rejects paths outside CWD."""
    monkeypatch.chdir(tmp_path)

    resp = client.post("/scan", json={"path": "/etc/passwd", "check_injection": False, "fail_on_pii": False})
    assert resp.status_code == 403
    assert "traversal" in resp.json()["detail"].lower()
