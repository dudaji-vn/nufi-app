"""Tests for enforcement/export_cmd.py (patch122)."""
from __future__ import annotations

import json

import yaml

from enforcement.export_cmd import export_patterns


def test_export_yaml_contains_pii_and_injection():
    """YAML 내보내기에 PII + 인젝션 패턴이 모두 포함된다."""
    out = export_patterns("yaml")
    data = yaml.safe_load(out)
    assert isinstance(data, list)
    assert len(data) > 0
    sources = {p["source"] for p in data}
    assert "pii" in sources, "PII 패턴이 포함되어야 한다"
    assert "injection" in sources, "인젝션 패턴이 포함되어야 한다"
    # 모든 엔트리에 필수 필드가 있어야 한다
    for p in data:
        assert "entity_type" in p
        assert "pattern" in p
        assert "description" in p


def test_export_json_roundtrip():
    """JSON 내보내기가 유효한 JSON 이고, regex 내보내기가 라인별 패턴이다."""
    json_out = export_patterns("json")
    data = json.loads(json_out)
    assert isinstance(data, list)
    assert len(data) > 0

    # injection 엔트리에는 severity 가 있어야 한다
    injection_entries = [p for p in data if p["source"] == "injection"]
    assert all("severity" in p for p in injection_entries)

    # regex 형식: 라인별 패턴
    regex_out = export_patterns("regex")
    lines = [l for l in regex_out.strip().split("\n") if l]
    assert len(lines) == len(data), "regex 라인 수가 전체 패턴 수와 일치해야 한다"
