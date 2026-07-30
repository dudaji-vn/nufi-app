"""Tests for ``nufi-egress explain`` command (patch116)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from enforcement.explain_cmd import explain_text, render_human
from nufi import explain as sdk_explain


class TestExplainWithPII:
    """explain with PII text shows detailed breakdown."""

    def test_pii_detailed_breakdown(self):
        text = "연락처는 test@example.com 전화 010-1234-5678 입니다"
        result = explain_text(text)

        # Must have findings
        assert result["has_findings"] is True
        assert len(result["pii_findings"]) >= 1

        # Check PII finding structure
        pii = result["pii_findings"][0]
        assert "entity_type" in pii
        assert "text" in pii
        assert "start" in pii
        assert "end" in pii
        assert "detection_method" in pii
        assert "confidence" in pii
        assert isinstance(pii["confidence"], float)
        assert pii["start"] >= 0
        assert pii["end"] > pii["start"]

        # Risk should be non-clean
        assert result["risk_level"] != "clean"

        # Action should be block or pseudonymize for PII
        assert result["action"] in ("block", "pseudonymize", "log")

        # Routing should be local (PII detected)
        assert result["routing"] == "local"
        assert result["routing_reason"]  # non-empty reason

        # Summary should mention PII count
        assert "PII" in result["summary"]

        # Human rendering should contain key sections
        human = render_human(result)
        assert "PII Findings" in human
        assert "Injection Analysis" in human
        assert "Policy Decision" in human
        assert "Routing Decision" in human
        assert "Summary" in human


class TestExplainCleanText:
    """explain with clean text shows 'no findings'."""

    def test_clean_text_no_findings(self):
        text = "The weather is nice today."
        result = explain_text(text)

        assert result["has_findings"] is False
        assert result["pii_findings"] == []
        assert result["injection_findings"] == []
        assert result["risk_level"] == "clean"
        assert result["action"] == "allow"
        assert result["routing"] == "cloud"
        assert "no findings" in result["summary"].lower() or "clean" in result["summary"].lower()

        # Human rendering should still have sections
        human = render_human(result)
        assert "NuFi Explain" in human
        assert "(none)" in human  # both PII and injection show (none)


class TestSDKExplain:
    """SDK convenience function ``from nufi import explain`` (patch118)."""

    def test_sdk_explain_returns_dict_with_expected_keys(self):
        result = sdk_explain("홍길동 주민번호 900101-1234567")
        assert isinstance(result, dict)
        assert result["has_findings"] is True
        assert result["risk_level"] in ("critical", "high", "medium", "low", "clean")
        assert "action" in result
        assert "routing" in result
        assert "pii_findings" in result
        assert "injection_findings" in result
        assert "summary" in result
        assert len(result["pii_findings"]) >= 1
