"""Tests for ``nufi-egress audit verify`` (patch120).

Two tests:
1. Valid hash chain — verify returns ok=True
2. Tampered record — verify detects the break
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from egress_audit.audit import AuditLogger
from enforcement.audit_cmd import verify_audit_log


def _create_valid_log(path: str, n: int = 5) -> None:
    """Write *n* valid hash-chained records to *path*."""
    logger = AuditLogger(path=path, hash_chain=True)
    for i in range(n):
        logger.log(
            model=f"test-model-{i}",
            provider="test-provider",
            is_public=True,
            request_body=f"request body {i}",
            outcome="forwarded",
        )


def test_valid_chain():
    """A log with a properly built hash chain should pass verification."""
    with tempfile.TemporaryDirectory() as td:
        log_path = str(Path(td) / "audit.jsonl")
        _create_valid_log(log_path, n=5)

        result = verify_audit_log(log_path)

        assert result["ok"] is True
        assert result["total"] == 5
        assert result["valid"] == 5
        assert result["broken_at"] is None
        assert result["error"] is None
        assert result["date_range"] is not None
        assert result["date_range"]["first_ts"] is not None
        assert result["date_range"]["last_ts"] is not None


def test_tampered_chain():
    """Modifying a record's body should break the hash chain."""
    with tempfile.TemporaryDirectory() as td:
        log_path = str(Path(td) / "audit.jsonl")
        _create_valid_log(log_path, n=5)

        # Tamper with record at index 2 (seq=2) — change the request_body
        lines = Path(log_path).read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[2])
        rec["request_body"] = "TAMPERED BODY"
        lines[2] = json.dumps(rec, ensure_ascii=False)
        Path(log_path).write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = verify_audit_log(log_path)

        assert result["ok"] is False
        assert result["total"] == 5
        assert result["broken_at"] == 2
        assert result["error"] is not None
        assert "변조" in result["error"] or "해시" in result["error"]
