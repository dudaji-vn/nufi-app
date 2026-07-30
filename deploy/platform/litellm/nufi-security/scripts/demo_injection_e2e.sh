#!/usr/bin/env bash
# patch77: End-to-end injection pipeline integration test wrapper.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Injection E2E Integration Test ==="
if python3 -m pytest tests/test_injection_e2e.py -v; then
    echo ""
    echo "PASS: All injection E2E tests passed."
    exit 0
else
    echo ""
    echo "FAIL: Some injection E2E tests failed."
    exit 1
fi
