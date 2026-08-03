#!/usr/bin/env bash
# =============================================================================
# demo_getting_started.sh — NuFi getting-started workflow demo (patch96)
#
# Full NuFi workflow from zero:
#   1. Init a project
#   2. Create sample files with PII
#   3. Scan with --fail-on-pii
#   4. Show findings
#   5. Redact with --dry-run
#   6. Inspect a specific text
#   7. Route decision
#   8. Doctor check
#
# Usage:  ./scripts/demo_getting_started.sh
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."

export EGRESS_NER_BACKEND=gazetteer

exec python3 scripts/demo_getting_started.py
