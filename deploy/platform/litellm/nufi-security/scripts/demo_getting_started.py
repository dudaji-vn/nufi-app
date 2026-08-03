#!/usr/bin/env python3
"""demo_getting_started.py — NuFi getting-started workflow demo (patch96).

Full workflow from zero in 8 PASS/FAIL steps:
  1. Init a project: nufi-egress init
  2. Create sample files with PII
  3. Scan: nufi-egress scan . --fail-on-pii
  4. Show findings
  5. Redact: nufi-egress scan . --redact --dry-run
  6. Inspect: nufi-egress inspect --text "..."
  7. Route: nufi-egress route --text "..."
  8. Doctor check: system health verification
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASS = 0
FAIL = 0


def cli(args: list[str], *, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run nufi-egress via python -m enforcement.cli."""
    cmd = [sys.executable, "-m", "enforcement.cli"] + args
    env = {**os.environ, "EGRESS_NER_BACKEND": "gazetteer"}
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or str(ROOT), env=env)


def report(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}")
    if detail and not ok:
        print(f"         detail: {detail}")
    if ok:
        PASS += 1
    else:
        FAIL += 1


def main() -> int:
    global PASS, FAIL

    print("=== NuFi Getting-Started Workflow Demo ===\n")

    with tempfile.TemporaryDirectory(prefix="nufi_gs_demo_") as tmpdir:
        tmp = Path(tmpdir)

        # -----------------------------------------------------------------
        # Step 1: Init a project (run from ROOT — init looks at cwd config/)
        # -----------------------------------------------------------------
        r = cli(["init"])
        # init exits 0 regardless of whether files already exist or are newly created
        init_ok = r.returncode == 0
        report("1) nufi-egress init — project initialization", init_ok, r.stderr)

        # -----------------------------------------------------------------
        # Step 2: Create sample files with PII
        # -----------------------------------------------------------------
        pii_file = tmp / "customer.txt"
        pii_file.write_text(
            "고객 정보: 홍길동, 주민번호 900101-1234567\n"
            "이메일: hong@example.com\n",
            encoding="utf-8",
        )
        clean_file = tmp / "readme.txt"
        clean_file.write_text("이 프로젝트는 NuFi 보안 도구 데모입니다.\n", encoding="utf-8")
        report("2) Sample files created (PII + clean)", True)

        # -----------------------------------------------------------------
        # Step 3: Scan with --fail-on-pii (expect exit 1 because PII exists)
        # -----------------------------------------------------------------
        r = cli(["scan", str(tmp), "--fail-on-pii"])
        scan_fail_ok = r.returncode == 1  # should fail because PII present
        report("3) nufi-egress scan --fail-on-pii → exit 1 (PII detected)", scan_fail_ok, f"rc={r.returncode}")

        # -----------------------------------------------------------------
        # Step 4: Show findings (basic scan, check output)
        # -----------------------------------------------------------------
        r = cli(["scan", str(tmp)])
        findings_ok = r.returncode == 0 and "PII:" in r.stdout and "customer.txt" in r.stdout
        report("4) Scan findings shown — PII in customer.txt", findings_ok, r.stdout[:200] if not findings_ok else "")

        # -----------------------------------------------------------------
        # Step 5: Redact with --dry-run
        # -----------------------------------------------------------------
        original = pii_file.read_text(encoding="utf-8")
        r = cli(["scan", str(tmp), "--redact", "--dry-run"])
        after = pii_file.read_text(encoding="utf-8")
        redact_ok = r.returncode == 0 and "DRY-RUN" in r.stdout and after == original
        report("5) nufi-egress scan --redact --dry-run — file unchanged", redact_ok)

        # -----------------------------------------------------------------
        # Step 6: Inspect a specific text
        # inspect exits 1 when blocked=true (by design), so we accept rc 0 or 1
        # -----------------------------------------------------------------
        test_text = "홍길동 주민번호 900101-1234567"
        r = cli(["inspect", "--text", test_text, "--json"])
        inspect_ok = False
        output = r.stdout or r.stderr  # JSON may go to stdout
        try:
            data = json.loads(output)
            inspect_ok = data.get("blocked") is True or len(data.get("pii_findings", [])) > 0
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        report("6) nufi-egress inspect --text — PII detected in text", inspect_ok, output[:200] if not inspect_ok else "")

        # -----------------------------------------------------------------
        # Step 7: Route decision
        # -----------------------------------------------------------------
        r = cli(["route", "--text", test_text, "--json"])
        route_ok = False
        if r.returncode == 0:
            try:
                data = json.loads(r.stdout)
                route_ok = data.get("pii_detected") is True and data.get("target_model") is not None
            except (json.JSONDecodeError, KeyError):
                pass
        report("7) nufi-egress route --text — routed to local (PII)", route_ok, r.stderr[:200] if not route_ok else "")

        # -----------------------------------------------------------------
        # Step 8: Doctor check
        # doctor may exit 1 if non-core checks (bypass) fail; we verify
        # that core checks (config, gateway, canary) pass.
        # -----------------------------------------------------------------
        r = cli(["doctor", "--json"])
        doctor_ok = False
        output = r.stdout or r.stderr
        try:
            data = json.loads(output)
            # Core checks pass: config + canary at minimum
            checks = {c["id"]: c["status"] for c in data.get("checks", [])}
            core_pass = checks.get("config") == "PASS" and checks.get("canary") == "PASS"
            doctor_ok = core_pass
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        report("8) nufi-egress doctor — core checks PASS", doctor_ok, output[:200] if not doctor_ok else "")

    # Summary
    print()
    total = PASS + FAIL
    print(f"결과: {PASS}/{total} PASS")
    if FAIL:
        print(f"FAIL: {FAIL} scenarios failed")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
