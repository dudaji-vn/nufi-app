"""Tests for nufi-egress mask / redact text transform commands (patch124)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from enforcement.transform_cmd import _transform_text


class TestMaskReplacesWithAsterisks:
    """mask mode replaces PII with asterisks."""

    def test_mask_person_and_account(self):
        text = "김민수님 계좌 110-123-456789"
        result = _transform_text(text, mode="mask")
        # Person name should be masked (asterisks)
        assert "김민수" not in result
        assert "*" in result
        # Account number should be masked
        assert "110-123-456789" not in result

    def test_mask_no_pii(self):
        text = "오늘 날씨가 좋습니다."
        result = _transform_text(text, mode="mask")
        assert result == text


class TestRedactReplacesWithTypeTags:
    """redact mode replaces PII with [TYPE] tags."""

    def test_redact_person_and_account(self):
        text = "김민수님 계좌 110-123-456789"
        result = _transform_text(text, mode="redact")
        # Person name should be tagged
        assert "김민수" not in result
        assert "[KR_PERSON]" in result or "[PERSON]" in result
        # Account number should be tagged
        assert "110-123-456789" not in result
        assert "[KR_ACCOUNT]" in result or "[ACCOUNT]" in result

    def test_redact_no_pii(self):
        text = "오늘 날씨가 좋습니다."
        result = _transform_text(text, mode="redact")
        assert result == text


class TestFileMode:
    """File input mode reads a file, transforms each line, outputs result."""

    def test_mask_file_roundtrip(self):
        content = "김민수님 계좌 110-123-456789\n일반 텍스트\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                          encoding="utf-8") as f:
            f.write(content)
            src = Path(f.name)

        try:
            lines = src.read_text(encoding="utf-8").splitlines()
            transformed = [_transform_text(line, mode="mask") for line in lines]
            result = "\n".join(transformed)
            # First line should have PII masked
            assert "김민수" not in transformed[0]
            assert "*" in transformed[0]
            # Second line should be unchanged
            assert transformed[1] == "일반 텍스트"
        finally:
            src.unlink(missing_ok=True)
