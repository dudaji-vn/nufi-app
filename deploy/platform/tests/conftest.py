import os

import pytest

# `guardrails.entrypoints` builds its module-level `g1_injection = G1Injection()`
# (and its G2-G4 siblings) at IMPORT time, which loads policy.yaml through
# `Policy.load(POLICY_PATH)` immediately. A fixture can't help here: fixtures
# only run once a test function requests them, long after collection has
# already imported the test module (and, transitively, `guardrails.entrypoints`
# itself). The env var must be set here, at conftest module scope, which
# pytest imports before collecting any test module in this directory.
# `setdefault` so a real deployment's own `GUARDRAIL_POLICY_PATH` (set in the
# container per the Dockerfile) is never overridden by this test-only default.
_POLICY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "litellm", "guardrails", "policy.yaml"
)
os.environ.setdefault("GUARDRAIL_POLICY_PATH", _POLICY_PATH)


@pytest.fixture
def policy_path() -> str:
    return _POLICY_PATH
