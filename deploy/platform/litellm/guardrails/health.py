"""Startup reconciliation and health reporting.

A control that is switched off must be loud. The previous generation of these
guardrails sat disabled in config for two months without a single signal:
`prompt_injection` commented out of `callbacks`, Presidio's `default_on` set
to `false` — no alert, no dashboard, no startup warning. The proxy reported
itself protected while running unprotected.

This module answers two questions for every mandatory control, every time
the proxy boots: is it enabled, and if not, does anyone find out? It is
deliberately dumb — no I/O beyond what `Policy` already did, no network
calls, nothing that can itself go dark. `guardrail_status` and
`assert_controls` both take an already-loaded `Policy` and are otherwise
pure, so they can be exercised (and fail loudly) long before any guardrail
class, scanner, or LiteLLM plumbing exists.

Known gap, stated rather than papered over: this module's visibility is
bounded by what made it into a `Policy` object in the first place. A control
declared in `policy.yaml` but never wired into `config.yaml`'s `guardrails:`
block — the shape of the original two-month failure, one layer up — is
invisible to `guardrail_status` and `assert_controls` alike, because neither
function ever sees `config.yaml`. See the Task 13 report for the full
analysis of what an operator does and does not see in that case.
"""

from __future__ import annotations

import logging
from typing import Any

from guardrails import audit
from guardrails.policy import Policy

logger = logging.getLogger("nufi.guardrails")


class StrictControlViolation(RuntimeError):
    """A mandatory control is disabled while `strict_controls` is on.

    Raised at proxy-import time (see `guardrails.entrypoints`), so this is
    not a value a caller can accidentally ignore the way an ordinary return
    value can be dropped — it stops the process before it can serve a single
    request while unprotected.
    """


def guardrail_status(policy: Policy) -> dict[str, Any]:
    """A point-in-time snapshot of every control the policy declares.

    Pure function of `policy` — callable with nothing else constructed yet
    (no guardrail instance, no scanner, no metrics side effects), which is
    what makes it usable both as a startup log line and as a unit-testable
    building block independent of the rest of the proxy wiring.

    `enforcing` is `ControlConfig.enforcing`, the same property the request
    path consults through `BaseNufiGuardrail._enforcing()` — a control can be
    `enabled: true` and still not enforcing anything because it is in
    `logging_only` mode, which is a distinct, equally important fact for an
    operator to see: "on and watching" is not "on and blocking". Reading the
    shared property rather than restating its formula is deliberate: the copy
    of it that had no test was the one that was wrong for three tasks.
    """
    return {
        "policy_version": policy.version,
        "policy_digest": policy.digest(),
        "strict_controls": policy.strict_controls,
        "controls": {
            control.id: {
                "risk": control.risk,
                "enabled": control.enabled,
                "mode": control.mode,
                "mandatory": control.mandatory,
                "fail": control.fail,
                "enforcing": control.enforcing,
            }
            for control in policy.controls.values()
        },
    }


def assert_controls(policy: Policy) -> list[str]:
    """Reconcile every mandatory control against its declared state.

    Three things happen for every disabled mandatory control, independent of
    `strict_controls`:

    1. A message naming the control is added to the returned list — the
       programmatic signal a caller can act on directly.
    2. `nufi_guardrail_enabled` is (re)published for every control the
       policy declares, not only the violating ones — this is the signal
       that outlives the single log line above it, visible on `/metrics`
       for as long as the process runs, independent of anyone reading logs
       at boot time.
    3. Each violation is logged at ERROR — the signal an operator sees in
       plain-text logs without instrumenting anything, and the one a
       log-based alert can match on.

    `strict_controls` decides only whether a violation additionally raises
    `StrictControlViolation` — never whether one is recorded or logged in
    the first place. `strict_controls: true` with a clean policy must not
    raise: it is a promise about what happens when something IS wrong, not
    a blanket refusal to boot.
    """
    violations = [
        f"mandatory control {control_id} is disabled"
        for control_id in policy.mandatory_ids()
        if not policy.control(control_id).enabled
    ]

    for control in policy.controls.values():
        audit.GUARDRAIL_ENABLED.labels(control=control.id, mode=control.mode).set(
            1 if control.enforcing else 0
        )

    for message in violations:
        logger.error("guardrail policy violation: %s", message)

    if violations and policy.strict_controls:
        raise StrictControlViolation("; ".join(violations))

    return violations
