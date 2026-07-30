"""``nufi-egress config validate|show`` -- validate/show NuFi config files (patch105, patch187).

Checks policy.yaml, pii_routing.yaml, injection_patterns.yaml for:
- YAML syntax errors
- Missing required fields
- Invalid regex patterns in injection_patterns.yaml

``config show`` displays the current effective configuration with defaults applied.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ConfigIssue:
    """Single validation issue."""
    file: str
    severity: str  # "error" | "warning"
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {"file": self.file, "severity": self.severity, "message": self.message}


@dataclass
class ConfigValidationResult:
    """Aggregated validation result."""
    files_checked: int = 0
    issues: List[ConfigIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files_checked": self.files_checked,
            "total_issues": len(self.issues),
            "has_errors": self.has_errors,
            "issues": [i.to_dict() for i in self.issues],
        }


# ---------------------------------------------------------------------------
# YAML loader (with fallback)
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> Any:
    """Load a YAML file. Raises ValueError on parse error."""
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text)
    # Minimal fallback: try json (won't work for real yaml but allows testing)
    raise ImportError("PyYAML is required for config validation")


# ---------------------------------------------------------------------------
# Individual validators
# ---------------------------------------------------------------------------

def _validate_policy(path: Path, result: ConfigValidationResult) -> None:
    """Validate policy.yaml."""
    result.files_checked += 1
    try:
        data = _load_yaml(path)
    except Exception as e:
        result.issues.append(ConfigIssue(
            file=str(path), severity="error",
            message=f"YAML parse error: {e}",
        ))
        return

    if not isinstance(data, dict):
        result.issues.append(ConfigIssue(
            file=str(path), severity="error",
            message="Root must be a mapping",
        ))
        return

    # Required fields
    for req in ("version", "default_action", "entities"):
        if req not in data:
            result.issues.append(ConfigIssue(
                file=str(path), severity="error",
                message=f"Missing required field: {req}",
            ))

    # Validate entities structure
    entities = data.get("entities")
    if isinstance(entities, dict):
        valid_actions = {"block", "redact", "pseudonymize", "warn", "allow"}
        for name, cfg in entities.items():
            if not isinstance(cfg, dict):
                result.issues.append(ConfigIssue(
                    file=str(path), severity="error",
                    message=f"Entity '{name}' value must be a mapping",
                ))
                continue
            action = cfg.get("action")
            if action and action not in valid_actions:
                result.issues.append(ConfigIssue(
                    file=str(path), severity="warning",
                    message=f"Entity '{name}' has unknown action: {action}",
                ))


def _validate_pii_routing(path: Path, result: ConfigValidationResult) -> None:
    """Validate pii_routing.yaml."""
    result.files_checked += 1
    try:
        data = _load_yaml(path)
    except Exception as e:
        result.issues.append(ConfigIssue(
            file=str(path), severity="error",
            message=f"YAML parse error: {e}",
        ))
        return

    if not isinstance(data, dict):
        result.issues.append(ConfigIssue(
            file=str(path), severity="error",
            message="Root must be a mapping",
        ))
        return

    for req in ("enabled", "local_model", "cloud_model"):
        if req not in data:
            result.issues.append(ConfigIssue(
                file=str(path), severity="error",
                message=f"Missing required field: {req}",
            ))


def _validate_injection_patterns(path: Path, result: ConfigValidationResult) -> None:
    """Validate injection_patterns.yaml — checks regex validity."""
    result.files_checked += 1
    try:
        data = _load_yaml(path)
    except Exception as e:
        result.issues.append(ConfigIssue(
            file=str(path), severity="error",
            message=f"YAML parse error: {e}",
        ))
        return

    if not isinstance(data, dict):
        result.issues.append(ConfigIssue(
            file=str(path), severity="error",
            message="Root must be a mapping",
        ))
        return

    patterns = data.get("custom_patterns")
    if patterns is None:
        # custom_patterns is optional
        return

    if not isinstance(patterns, list):
        result.issues.append(ConfigIssue(
            file=str(path), severity="error",
            message="'custom_patterns' must be a list",
        ))
        return

    for idx, entry in enumerate(patterns):
        if not isinstance(entry, dict):
            result.issues.append(ConfigIssue(
                file=str(path), severity="error",
                message=f"Pattern entry [{idx}] must be a mapping",
            ))
            continue

        pat = entry.get("pattern")
        if not pat:
            result.issues.append(ConfigIssue(
                file=str(path), severity="error",
                message=f"Pattern entry [{idx}] missing 'pattern' field",
            ))
            continue

        # Validate regex
        try:
            re.compile(pat)
        except re.error as e:
            result.issues.append(ConfigIssue(
                file=str(path), severity="error",
                message=f"Pattern entry [{idx}] invalid regex '{pat}': {e}",
            ))

        if "severity" not in entry:
            result.issues.append(ConfigIssue(
                file=str(path), severity="warning",
                message=f"Pattern entry [{idx}] missing 'severity' field",
            ))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_config(
    config_dir: Optional[str | Path] = None,
) -> ConfigValidationResult:
    """Validate all NuFi config files in *config_dir*.

    Checks: policy.yaml, pii_routing.yaml, injection_patterns.yaml.

    Args:
        config_dir: Directory containing config files (default: ``config/``
            relative to project root).

    Returns:
        ConfigValidationResult with all issues found.
    """
    if config_dir is None:
        config_dir = Path(__file__).resolve().parent.parent / "config"
    else:
        config_dir = Path(config_dir)

    result = ConfigValidationResult()

    # policy.yaml
    policy_path = config_dir / "policy.yaml"
    if policy_path.is_file():
        _validate_policy(policy_path, result)
    else:
        result.issues.append(ConfigIssue(
            file=str(policy_path), severity="warning",
            message="File not found",
        ))

    # pii_routing.yaml
    routing_path = config_dir / "pii_routing.yaml"
    if routing_path.is_file():
        _validate_pii_routing(routing_path, result)
    else:
        result.issues.append(ConfigIssue(
            file=str(routing_path), severity="warning",
            message="File not found",
        ))

    # injection_patterns.yaml
    injection_path = config_dir / "injection_patterns.yaml"
    if injection_path.is_file():
        _validate_injection_patterns(injection_path, result)
    else:
        # injection_patterns.yaml is optional — just note it
        result.issues.append(ConfigIssue(
            file=str(injection_path), severity="warning",
            message="File not found (optional)",
        ))

    return result


# ---------------------------------------------------------------------------
# Config show (patch187)
# ---------------------------------------------------------------------------

# Default values applied when a config file is missing or fields are absent.
_POLICY_DEFAULTS: Dict[str, Any] = {
    "version": 1,
    "default_action": "warn",
    "blocking_actions": ["block"],
    "entities": {},
}

_PII_ROUTING_DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "local_model": "none",
    "cloud_model": "none",
}

_INJECTION_PATTERNS_DEFAULTS: Dict[str, Any] = {
    "custom_patterns": [],
}

_SCAN_PROFILES_DEFAULTS: Dict[str, Any] = {
    "profiles": {},
}


def _merge_defaults(data: Optional[Dict[str, Any]], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Merge loaded data over defaults (shallow)."""
    merged = dict(defaults)
    if data and isinstance(data, dict):
        merged.update(data)
    return merged


def show_config(
    config_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Load and return the effective configuration with defaults applied.

    Reads: policy.yaml, pii_routing.yaml, injection_patterns.yaml, scan_profiles.yaml.

    Args:
        config_dir: Directory containing config files (default: ``config/``
            relative to project root).

    Returns:
        Dictionary with effective config for each file.
    """
    if config_dir is None:
        config_dir = Path(__file__).resolve().parent.parent / "config"
    else:
        config_dir = Path(config_dir)

    effective: Dict[str, Any] = {}

    # policy.yaml
    policy_path = config_dir / "policy.yaml"
    policy_data = None
    if policy_path.is_file():
        try:
            policy_data = _load_yaml(policy_path)
        except Exception:
            policy_data = None
    effective["policy"] = _merge_defaults(policy_data, _POLICY_DEFAULTS)

    # pii_routing.yaml
    routing_path = config_dir / "pii_routing.yaml"
    routing_data = None
    if routing_path.is_file():
        try:
            routing_data = _load_yaml(routing_path)
        except Exception:
            routing_data = None
    effective["pii_routing"] = _merge_defaults(routing_data, _PII_ROUTING_DEFAULTS)

    # injection_patterns.yaml
    injection_path = config_dir / "injection_patterns.yaml"
    injection_data = None
    if injection_path.is_file():
        try:
            injection_data = _load_yaml(injection_path)
        except Exception:
            injection_data = None
    effective["injection_patterns"] = _merge_defaults(injection_data, _INJECTION_PATTERNS_DEFAULTS)

    # scan_profiles.yaml
    profiles_path = config_dir / "scan_profiles.yaml"
    profiles_data = None
    if profiles_path.is_file():
        try:
            profiles_data = _load_yaml(profiles_path)
        except Exception:
            profiles_data = None
    effective["scan_profiles"] = _merge_defaults(profiles_data, _SCAN_PROFILES_DEFAULTS)

    effective["_meta"] = {
        "config_dir": str(config_dir),
        "files_loaded": [
            str(p) for p in [policy_path, routing_path, injection_path, profiles_path]
            if p.is_file()
        ],
    }

    return effective


# ---------------------------------------------------------------------------
# CLI handler
# ---------------------------------------------------------------------------

def cmd_config(args) -> int:
    """``nufi-egress config validate|show`` CLI handler."""
    action = getattr(args, "config_action", None)

    if action == "show":
        config_dir = getattr(args, "config_dir", None)
        use_json = getattr(args, "json", False)
        effective = show_config(config_dir=config_dir)

        if use_json:
            print(json.dumps(effective, ensure_ascii=False, indent=2))
        else:
            # Human-friendly output
            print(f"Config directory: {effective['_meta']['config_dir']}")
            print(f"Files loaded: {len(effective['_meta']['files_loaded'])}")
            print()
            for section in ("policy", "pii_routing", "injection_patterns", "scan_profiles"):
                print(f"[{section}]")
                data = effective[section]
                for key, value in data.items():
                    # Truncate long values for readability
                    val_str = str(value)
                    if len(val_str) > 80:
                        val_str = val_str[:77] + "..."
                    print(f"  {key}: {val_str}")
                print()
        return 0

    if action == "validate":
        config_dir = getattr(args, "config_dir", None)
        use_json = getattr(args, "json", False)

        result = validate_config(config_dir=config_dir)

        if use_json:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            if not result.issues:
                print(f"Config validation: {result.files_checked} files checked, no issues.")
            else:
                error_count = sum(1 for i in result.issues if i.severity == "error")
                warn_count = sum(1 for i in result.issues if i.severity == "warning")
                print(f"Config validation: {result.files_checked} files checked, "
                      f"{error_count} error(s), {warn_count} warning(s).")
                print()
                for issue in result.issues:
                    tag = "ERROR" if issue.severity == "error" else "WARN"
                    print(f"  [{tag}] {issue.file}: {issue.message}")

        return 1 if result.has_errors else 0

    print("Unknown config action", file=sys.stderr)
    return 2
