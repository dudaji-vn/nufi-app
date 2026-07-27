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
        return self.controls[control_id]

    def mandatory_ids(self) -> tuple[str, ...]:
        return tuple(sorted(c.id for c in self.controls.values() if c.mandatory))

    def digest(self) -> str:
        return hashlib.sha256(self._raw.encode("utf-8")).hexdigest()[:12]


def _parse_control(control_id: str, body: dict[str, Any]) -> ControlConfig:
    mode = str(body.get("mode", "logging_only"))
    if mode not in _MODES:
        raise ValueError(f"{control_id}: unknown mode {mode!r}")
    fail = str(body.get("fail", "open"))
    if fail not in _FAIL:
        raise ValueError(f"{control_id}: fail must be open or closed, got {fail!r}")

    thresholds_raw = body.get("thresholds") or {}
    thresholds = {
        source: float(thresholds_raw.get(source.value, 1.01)) for source in SpanSource
    }

    return ControlConfig(
        id=control_id,
        risk=str(body["risk"]),
        enabled=bool(body.get("enabled", True)),
        mandatory=bool(body.get("mandatory", False)),
        mode=mode,
        fail=fail,
        action=Action(str(body.get("action", "log"))),
        thresholds=thresholds,
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
        if finding.score >= control.thresholds[finding.source]
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
