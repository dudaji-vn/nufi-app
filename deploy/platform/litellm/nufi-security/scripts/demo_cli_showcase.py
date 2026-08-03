#!/usr/bin/env python3
"""CLI showcase demo -- quick validation of key CLI commands (patch148).

Runs 5 PASS/FAIL scenarios exercising:
  1. playground --text (non-interactive)
  2. summary --json
  3. pipeline --text --json
  4. mask --text
  5. redact --text
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

PASS = 0
FAIL = 0


def run(label: str, argv: list[str], check_fn) -> bool:
    """Run a CLI command and validate with check_fn.  Returns True on PASS."""
    global PASS, FAIL
    try:
        result = subprocess.run(
            [sys.executable, "-m", "enforcement.cli"] + argv,
            capture_output=True, text=True, timeout=60,
            cwd=str(_ROOT),
            env={**__import__("os").environ, "EGRESS_NER_BACKEND": "gazetteer"},
        )
        stdout = result.stdout
        stderr = result.stderr
        rc = result.returncode

        ok = check_fn(rc, stdout, stderr)
        if ok:
            PASS += 1
            print(f"  PASS  {label}")
        else:
            FAIL += 1
            print(f"  FAIL  {label}")
            print(f"        rc={rc}")
            if stdout.strip():
                print(f"        stdout: {stdout[:200]}")
            if stderr.strip():
                print(f"        stderr: {stderr[:200]}")
        return ok
    except Exception as e:
        FAIL += 1
        print(f"  FAIL  {label} -- exception: {e}")
        return False


def main() -> int:
    print("=== CLI Showcase Demo (patch148) ===")
    print()

    # 1. playground --text (non-interactive inspect mode)
    run(
        "playground --text (inspect)",
        ["playground", "--text", "홍길동 전화번호 010-1234-5678"],
        lambda rc, out, err: rc == 0 and "[PII]" in out,
    )

    # 2. summary --json
    run(
        "summary --json",
        ["summary", "--json"],
        lambda rc, out, err: rc == 0 and _is_json_with_key(out, "version"),
    )

    # 3. pipeline --text --json
    run(
        "pipeline --text --json",
        ["pipeline", "--text", "김민수님 주민번호 900101-1234568", "--json"],
        lambda rc, out, err: rc == 0 and _is_json_with_key(out, "detect"),
    )

    # 4. mask --text
    run(
        "mask --text",
        ["mask", "--text", "이메일 hong@dudaji.com 입니다"],
        lambda rc, out, err: rc == 0 and "***" in out,
    )

    # 5. redact --text
    run(
        "redact --text",
        ["redact", "--text", "전화번호 010-9876-5432 알려드립니다"],
        lambda rc, out, err: rc == 0 and "[" in out,
    )

    print()
    print(f"결과: PASS={PASS}  FAIL={FAIL}")
    if FAIL:
        print("FAIL")
    else:
        print("ALL PASS")
    return 1 if FAIL else 0


def _is_json_with_key(text: str, key: str) -> bool:
    try:
        data = json.loads(text)
        return key in data
    except (json.JSONDecodeError, TypeError):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
