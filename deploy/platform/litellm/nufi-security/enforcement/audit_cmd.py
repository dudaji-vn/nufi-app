"""``nufi-egress audit verify`` -- verify audit log hash chain integrity (patch120).

Reads a JSONL audit log and verifies that each record's hash chain is intact.
Returns total records, valid count, first broken record (if any), and date range.

SDK usage::

    from enforcement.audit_cmd import verify_audit_log
    result = verify_audit_log("logs/egress_audit.jsonl")
    # result: {"total": 10, "valid": 10, "broken_at": None, "date_range": {...}, "ok": True}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from egress_audit.audit import verify_chain_records, GENESIS_HASH, _record_hash


def verify_audit_log(log_path: str) -> Dict[str, Any]:
    """Read a JSONL audit log and verify the hash chain integrity.

    Returns a dict with:
        total       -- number of records
        valid       -- number of valid (chain-verified) records
        broken_at   -- seq of first broken record, or None if all valid
        error       -- error description if chain is broken, else None
        date_range  -- {first_ts, last_ts} or None if empty
        ok          -- True if all records are valid
    """
    path = Path(log_path)
    if not path.exists():
        return {
            "total": 0,
            "valid": 0,
            "broken_at": None,
            "error": "log file not found",
            "date_range": None,
            "ok": False,
        }

    records: List[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        return {
            "total": 0,
            "valid": 0,
            "broken_at": None,
            "error": None,
            "date_range": None,
            "ok": True,
        }

    # Use the core verifier from egress_audit.audit
    chain_result = verify_chain_records(records)

    # Count valid records
    if chain_result["ok"]:
        valid = len(records)
        broken_at = None
        error = None
    else:
        broken_at = chain_result.get("broken_seq")
        error = chain_result.get("error")
        # Valid records = everything before the broken one
        if broken_at is not None and isinstance(broken_at, int):
            valid = broken_at
        else:
            valid = 0

    # Date range
    first_ts = None
    last_ts = None
    for rec in records:
        ts = rec.get("ts")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts

    date_range = None
    if first_ts or last_ts:
        date_range = {"first_ts": first_ts, "last_ts": last_ts}

    return {
        "total": len(records),
        "valid": valid,
        "broken_at": broken_at,
        "error": error,
        "date_range": date_range,
        "ok": chain_result["ok"],
    }


def cmd_audit_verify(args) -> int:
    """CLI handler for ``nufi-egress audit verify``."""
    log_path = getattr(args, "log_path", None) or "logs/egress_audit.jsonl"
    result = verify_audit_log(log_path)
    use_json = getattr(args, "json", False)

    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Audit log: {log_path}")
        print(f"  Total records: {result['total']}")
        print(f"  Valid records: {result['valid']}")
        if result["date_range"]:
            dr = result["date_range"]
            print(f"  Date range:    {dr['first_ts']} ~ {dr['last_ts']}")
        if result["ok"]:
            print("  Hash chain:    OK — all records verified")
        else:
            print(f"  Hash chain:    BROKEN at record {result['broken_at']}")
            print(f"  Error:         {result['error']}")

    return 0 if result["ok"] else 1
