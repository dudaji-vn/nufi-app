import os

import pytest


@pytest.fixture
def policy_path() -> str:
    here = os.path.dirname(__file__)
    return os.path.join(here, "..", "litellm", "guardrails", "policy.yaml")
