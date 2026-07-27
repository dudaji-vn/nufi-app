"""The only place a guardrail decision is made.

Scanners report `Finding`s; this module turns them into a `Decision` using
`policy.yaml`. Pure — no I/O beyond reading the policy file once at load.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Any

import yaml

from guardrails.types import Action, Decision, Finding, SpanSource

_MODES = frozenset({"pre_call", "post_call", "during_call", "logging_only"})
_FAIL = frozenset({"open", "closed"})


@dataclass(frozen=True)
class ControlConfig:
    id: str
    risk: str
    enabled: bool
    mandatory: bool
    mode: str
    fail: str
    action: Action
    thresholds: dict[SpanSource, float]
    # Optional per-detector overrides, keyed by Finding.detector. A detector
    # that doesn't report a likelihood on the same 0-1 scale as a classifier
    # score — coverage_gap, for instance — needs its own threshold rather
    # than being compared against a per-source score threshold it does not
    # share. Absent for a given detector, `decide` falls back to `thresholds`.
    detector_thresholds: dict[str, float]
    options: dict[str, Any]

    def with_mode(self, mode: str) -> ControlConfig:
        return replace(self, mode=mode)

    def with_enabled(self, enabled: bool) -> ControlConfig:
        return replace(self, enabled=enabled)

    @property
    def fails_closed(self) -> bool:
        return self.fail == "closed"


class Policy:
    def __init__(self, raw: str) -> None:
        self._raw = raw
        data = yaml.safe_load(raw) or {}
        self.version: int = int(data.get("version", 1))
        self.strict_controls: bool = bool(data.get("strict_controls", False))
        self.controls: dict[str, ControlConfig] = {
            control_id: _parse_control(control_id, body)
            for control_id, body in (data.get("controls") or {}).items()
        }

    @classmethod
    def load(cls, path: str) -> Policy:
        with open(path, encoding="utf-8") as handle:
            return cls(handle.read())

    def control(self, control_id: str) -> ControlConfig:
        if control_id not in self.controls:
            known = sorted(self.controls)
            raise KeyError(f"unknown control {control_id!r}; policy declares {known}")
        return self.controls[control_id]

    def mandatory_ids(self) -> tuple[str, ...]:
        return tuple(sorted(c.id for c in self.controls.values() if c.mandatory))

    def digest(self) -> str:
        return hashlib.sha256(self._raw.encode("utf-8")).hexdigest()[:12]


def _parse_control(control_id: str, body: dict[str, Any]) -> ControlConfig:
    """Parse one control, refusing anything ambiguous.

    Every error names the control, because a policy file that loads with a
    silently-inert control is the exact failure this whole design exists to
    prevent: the previous generation of these guardrails sat disabled in config
    for two months with no signal. A typo must stop the proxy, not neuter a
    control while the dashboard still reports it enabled.
    """
    if "risk" not in body:
        raise ValueError(f"{control_id}: missing required key 'risk'")

    mode = str(body.get("mode", "logging_only"))
    if mode not in _MODES:
        raise ValueError(
            f"{control_id}: unknown mode {mode!r}, expected one of {sorted(_MODES)}"
        )
    fail = str(body.get("fail", "open"))
    if fail not in _FAIL:
        raise ValueError(f"{control_id}: fail must be open or closed, got {fail!r}")

    action_raw = str(body.get("action", "log"))
    try:
        action = Action(action_raw)
    except ValueError as exc:
        valid = sorted(item.value for item in Action)
        raise ValueError(
            f"{control_id}: unknown action {action_raw!r}, expected one of {valid}"
        ) from exc

    thresholds_raw = body.get("thresholds") or {}
    known = {source.value for source in SpanSource}
    unknown = sorted(set(thresholds_raw) - known)
    if unknown:
        raise ValueError(
            f"{control_id}: unknown threshold key(s) {unknown}, expected {sorted(known)}"
        )
    missing = sorted(known - set(thresholds_raw))
    if missing:
        raise ValueError(
            f"{control_id}: missing threshold(s) for {missing}. "
            f"Use 1.01 to exclude a source deliberately — omitting it is not the same thing."
        )
    thresholds = {source: float(thresholds_raw[source.value]) for source in SpanSource}

    detector_raw = body.get("detector_thresholds") or {}
    detector_thresholds = {str(name): float(value) for name, value in detector_raw.items()}

    return ControlConfig(
        id=control_id,
        risk=str(body["risk"]),
        enabled=bool(body.get("enabled", True)),
        mandatory=bool(body.get("mandatory", False)),
        mode=mode,
        fail=fail,
        action=action,
        thresholds=thresholds,
        detector_thresholds=detector_thresholds,
        options=dict(body.get("options") or {}),
    )


def decide(
    control: ControlConfig, findings: list[Finding], grounded: bool
) -> Decision:
    if not control.enabled:
        return _allow(control, "control disabled")

    crossed = tuple(
        finding
        for finding in findings
        if finding.score
        >= control.detector_thresholds.get(finding.detector, control.thresholds[finding.source])
    )
    if not crossed:
        return _allow(control, "no finding crossed threshold")

    if grounded and control.options.get("respect_grounded_hint"):
        return _allow(control, "grounded hint honoured")

    top = max(crossed, key=lambda f: f.score)
    return Decision(
        action=control.action,
        control=control.id,
        risk=control.risk,
        findings=crossed,
        reason=f"{top.detector}={top.score:.2f} on {top.source} span",
    )


def _allow(control: ControlConfig, reason: str) -> Decision:
    return Decision(
        action=Action.ALLOW,
        control=control.id,
        risk=control.risk,
        findings=(),
        reason=reason,
    )
