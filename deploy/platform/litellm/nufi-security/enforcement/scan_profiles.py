"""Scan profile loading and resolution (patch110, v0.7.7).

Scan profiles allow users to define reusable sets of scan options
(e.g. ``development``, ``ci``, ``strict``, ``standard``, ``minimal``,
``financial``) in a YAML config file.

Profile settings serve as defaults that can be overridden by explicit
CLI flags.

Built-in profiles (v0.7.7):
- ``strict``     — 모든 엔티티 타입 스캔, score 임계 0.5, 하나라도 발견 시 exit 1
- ``standard``   — 주요 엔티티만 (KR_RRN, CREDIT_CARD, KR_ACCOUNT, EMAIL), score 임계 0.7
- ``minimal``    — KR_RRN + CREDIT_CARD만, score 임계 0.9
- ``financial``  — 금융 관련 엔티티 집중 (KR_ACCOUNT, CREDIT_CARD, KR_RRN)

Custom profiles can be defined in ``nufi.yaml`` under the ``scan_profiles`` key.

Usage::

    from enforcement.scan_profiles import load_profiles, resolve_profile

    profiles = load_profiles()              # loads config/scan_profiles.yaml
    settings = resolve_profile("ci", profiles)
    # settings == {"check_injection": True, "min_severity": "medium", ...}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PROFILES_PATH = _ROOT / "config" / "scan_profiles.yaml"

# Keys that a profile may set (whitelist for safety).
_PROFILE_KEYS = frozenset({
    "check_injection",
    "min_severity",
    "fail_on_pii",
    "parallel",
    "format",
    "pattern",
    "exclude",
    "cache",
    "stats",
    "only_types",
    "min_score",
})


@dataclass
class ScanProfile:
    """Resolved scan profile with typed fields."""

    name: str
    check_injection: bool = False
    min_severity: str = "low"
    fail_on_pii: bool = False
    parallel: int = 1
    format: Optional[str] = None
    pattern: Optional[str] = None
    exclude: Optional[str] = None
    cache: bool = False
    stats: bool = False
    only_types: Optional[str] = None
    min_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "check_injection": self.check_injection,
            "min_severity": self.min_severity,
            "fail_on_pii": self.fail_on_pii,
            "parallel": self.parallel,
            "format": self.format,
            "pattern": self.pattern,
            "exclude": self.exclude,
            "cache": self.cache,
            "stats": self.stats,
            "only_types": self.only_types,
            "min_score": self.min_score,
        }


def _load_profiles_from_file(profiles_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load and validate scan profiles from a single YAML file."""
    if not profiles_path.is_file():
        return {}

    text = profiles_path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}

    profiles = data.get("scan_profiles")
    if profiles is None:
        return {}
    if not isinstance(profiles, dict):
        raise ValueError(
            f"'scan_profiles' must be a mapping in {profiles_path}"
        )

    # Validate keys
    for name, settings in profiles.items():
        if not isinstance(settings, dict):
            raise ValueError(
                f"Profile '{name}' must be a mapping in {profiles_path}"
            )
        unknown = set(settings.keys()) - _PROFILE_KEYS
        if unknown:
            raise ValueError(
                f"Profile '{name}' has unknown keys: {', '.join(sorted(unknown))}"
            )

    return profiles


def load_profiles(path: Optional[str | Path] = None) -> Dict[str, Dict[str, Any]]:
    """Load scan profiles from YAML files.

    Loads built-in profiles from ``config/scan_profiles.yaml`` first,
    then merges custom profiles from ``nufi.yaml`` (if present in CWD
    or project root). Custom profiles override built-in ones with the
    same name.

    Args:
        path: Path to scan_profiles.yaml. Defaults to config/scan_profiles.yaml.

    Returns:
        Mapping of profile name to settings dict.

    Raises:
        FileNotFoundError: if the built-in profiles file does not exist.
        ValueError: if the YAML structure is invalid.
    """
    profiles_path = Path(path) if path else _DEFAULT_PROFILES_PATH
    if not profiles_path.is_file():
        raise FileNotFoundError(f"Scan profiles file not found: {profiles_path}")

    profiles = _load_profiles_from_file(profiles_path)
    if not profiles:
        raise ValueError(f"Missing 'scan_profiles' key in {profiles_path}")

    # Merge custom profiles from nufi.yaml (CWD or project root)
    for candidate in [Path.cwd() / "nufi.yaml", _ROOT / "nufi.yaml"]:
        custom = _load_profiles_from_file(candidate)
        if custom:
            profiles.update(custom)
            break  # only load from first found nufi.yaml

    return profiles


def resolve_profile(
    profile_name: str,
    profiles: Optional[Dict[str, Dict[str, Any]]] = None,
    profiles_path: Optional[str | Path] = None,
) -> ScanProfile:
    """Resolve a profile name to a ScanProfile.

    Args:
        profile_name: Name of the profile to resolve.
        profiles: Pre-loaded profiles dict. If None, loads from disk.
        profiles_path: Path to profiles YAML (used only if *profiles* is None).

    Returns:
        ScanProfile with the profile settings applied.

    Raises:
        KeyError: if the named profile does not exist.
    """
    if profiles is None:
        profiles = load_profiles(profiles_path)

    if profile_name not in profiles:
        available = ", ".join(sorted(profiles.keys()))
        raise KeyError(
            f"Unknown scan profile '{profile_name}'. "
            f"Available: {available}"
        )

    settings = profiles[profile_name]
    raw_min_score = settings.get("min_score")
    return ScanProfile(
        name=profile_name,
        check_injection=bool(settings.get("check_injection", False)),
        min_severity=str(settings.get("min_severity", "low")),
        fail_on_pii=bool(settings.get("fail_on_pii", False)),
        parallel=int(settings.get("parallel", 1)),
        format=settings.get("format"),
        pattern=settings.get("pattern"),
        exclude=settings.get("exclude"),
        cache=bool(settings.get("cache", False)),
        stats=bool(settings.get("stats", False)),
        only_types=settings.get("only_types"),
        min_score=float(raw_min_score) if raw_min_score is not None else None,
    )


def apply_profile_to_args(profile: ScanProfile, args) -> None:
    """Apply profile defaults to an argparse Namespace.

    Only sets values that are not already explicitly provided
    (i.e. still at their default/None/False state).
    Explicit CLI flags always win.
    """
    # check_injection: default is False
    if not getattr(args, "check_injection", False) and profile.check_injection:
        args.check_injection = True

    # fail_on_pii: default is False
    if not getattr(args, "fail_on_pii", False) and profile.fail_on_pii:
        args.fail_on_pii = True

    # parallel: default is 1
    if getattr(args, "parallel", 1) == 1 and profile.parallel > 1:
        args.parallel = profile.parallel

    # format: default is None
    if getattr(args, "format", None) is None and profile.format:
        args.format = profile.format

    # pattern: default is None
    if getattr(args, "pattern", None) is None and profile.pattern:
        args.pattern = profile.pattern

    # exclude: default is None
    if getattr(args, "exclude", None) is None and profile.exclude:
        args.exclude = profile.exclude

    # cache: default is False
    if not getattr(args, "cache", False) and profile.cache:
        args.cache = True

    # stats: default is False
    if not getattr(args, "stats", False) and profile.stats:
        args.stats = True

    # only_types: default is None (v0.7.7)
    if getattr(args, "only_types", None) is None and profile.only_types:
        args.only_types = profile.only_types

    # min_score: default is 0.0 (v0.7.7)
    if getattr(args, "min_score", 0.0) == 0.0 and profile.min_score is not None:
        args.min_score = profile.min_score
