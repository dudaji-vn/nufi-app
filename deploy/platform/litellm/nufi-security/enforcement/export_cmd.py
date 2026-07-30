"""``nufi-egress export patterns`` — 탐지 패턴 표준 형식 내보내기 (patch122).

NuFi 의 PII + 인젝션 탐지 패턴을 YAML/JSON/regex 형식으로 내보내기.
팀 공유, 백업, 외부 도구(grep/ripgrep) 연동에 활용.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import yaml


_ROOT = Path(__file__).resolve().parent.parent


def _load_pii_patterns() -> List[Dict[str, Any]]:
    """config/patterns.yaml 에서 PII 패턴을 로드한다."""
    patterns_path = _ROOT / "config" / "patterns.yaml"
    if not patterns_path.exists():
        return []
    data = yaml.safe_load(patterns_path.read_text(encoding="utf-8"))
    entries: List[Dict[str, Any]] = []
    for rule in data.get("korean_pii", []):
        entries.append({
            "entity_type": rule["name"],
            "pattern": rule["regex"],
            "description": rule.get("desc", ""),
            "source": "pii",
        })
    return entries


def _load_injection_patterns() -> List[Dict[str, Any]]:
    """prompt_injection 모듈에서 인젝션 패턴을 로드한다."""
    from egress_audit.detectors.prompt_injection import _PATTERN_DEFS
    entries: List[Dict[str, Any]] = []
    for pattern_str, score, severity, category in _PATTERN_DEFS:
        entries.append({
            "entity_type": f"INJECTION:{category.upper()}",
            "pattern": pattern_str,
            "description": f"{category} injection pattern (score={score})",
            "severity": severity,
            "source": "injection",
        })
    return entries


def export_patterns(fmt: str = "yaml") -> str:
    """모든 PII + 인젝션 패턴을 지정 형식으로 내보낸다.

    Args:
        fmt: 출력 형식 — "yaml", "json", "regex".

    Returns:
        포맷팅된 문자열.
    """
    pii = _load_pii_patterns()
    injection = _load_injection_patterns()
    all_patterns = pii + injection

    if fmt == "regex":
        return "\n".join(p["pattern"] for p in all_patterns) + "\n"

    if fmt == "json":
        return json.dumps(all_patterns, ensure_ascii=False, indent=2) + "\n"

    # default: yaml
    return yaml.dump(all_patterns, allow_unicode=True, default_flow_style=False,
                     sort_keys=False)


def cmd_export(args) -> int:
    """CLI 진입점 — export patterns."""
    action = getattr(args, "export_action", None)
    if action != "patterns":
        import sys
        print("usage: nufi-egress export patterns [--format yaml|json|regex]",
              file=sys.stderr)
        return 2

    fmt = getattr(args, "format", "yaml") or "yaml"
    print(export_patterns(fmt), end="")
    return 0
