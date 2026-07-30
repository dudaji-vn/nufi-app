"""tests for ``nufi-egress playground`` (patch145, patch215 --no-emoji)."""
from __future__ import annotations

import os
import subprocess
import sys


def test_playground_pipe_mode():
    """Non-interactive pipe mode: stdin text is analysed and output contains PII tag."""
    result = subprocess.run(
        [sys.executable, "-m", "enforcement.cli", "playground"],
        input="김민수님 주민번호 900101-1234568\n",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    out = result.stdout
    # Should contain PII findings
    assert "[PII]" in out
    assert "[Risk]" in out
    assert "[Route]" in out
    assert "[Block]" in out


def test_playground_text_flag():
    """--text flag for non-interactive single-line analysis."""
    result = subprocess.run(
        [sys.executable, "-m", "enforcement.cli", "playground",
         "--text", "이메일 test@example.com"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "[PII]" in result.stdout


def test_playground_mask_mode():
    """--mode mask replaces PII with asterisks."""
    result = subprocess.run(
        [sys.executable, "-m", "enforcement.cli", "playground",
         "--text", "김민수님 연락처", "--mode", "mask"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    # In mask mode, output should NOT contain the [PII] tag format
    # (it returns the transformed text directly)
    assert "[PII]" not in result.stdout


def test_playground_redact_mode():
    """--mode redact replaces PII with [TYPE] tags."""
    result = subprocess.run(
        [sys.executable, "-m", "enforcement.cli", "playground",
         "--text", "김민수님 연락처", "--mode", "redact"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    out = result.stdout
    # Redact mode should produce [KR_PERSON] or similar type tags
    # but not the inspect-format [PII] header
    assert "[PII]" not in out


# ---------------------------------------------------------------------------
# --no-emoji / NUFI_NO_EMOJI tests (patch215)
# ---------------------------------------------------------------------------

def test_playground_no_emoji_flag():
    """--no-emoji replaces emoji icons with text alternatives."""
    result = subprocess.run(
        [sys.executable, "-m", "enforcement.cli", "playground",
         "--text", "김민수님 주민번호 900101-1234568", "--no-emoji"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    out = result.stdout
    assert "[Route]" in out
    assert "[Block]" in out
    # Text alternatives should be present instead of emoji
    assert "[C]" in out or "[L]" in out
    assert "[OK]" in out or "[!]" in out
    # Emoji should NOT be present
    assert "\U0001f512" not in out  # 🔒
    assert "\u2601" not in out       # ☁
    assert "\u26d4" not in out       # ⛔
    assert "\u2705" not in out       # ✅


def test_playground_no_emoji_env():
    """NUFI_NO_EMOJI=1 environment variable suppresses emoji."""
    env = {**os.environ, "NUFI_NO_EMOJI": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "enforcement.cli", "playground",
         "--text", "이메일 test@example.com"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert result.returncode == 0
    out = result.stdout
    # Text alternatives should be present
    assert "[C]" in out or "[L]" in out
    assert "[OK]" in out or "[!]" in out
    # Emoji should NOT be present
    assert "\U0001f512" not in out
    assert "\u2601" not in out
    assert "\u26d4" not in out
    assert "\u2705" not in out


def test_playground_emoji_default():
    """Without --no-emoji, emoji icons should be present."""
    env = {k: v for k, v in os.environ.items() if k != "NUFI_NO_EMOJI"}
    result = subprocess.run(
        [sys.executable, "-m", "enforcement.cli", "playground",
         "--text", "김민수님 주민번호 900101-1234568"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert result.returncode == 0
    out = result.stdout
    # At least one emoji icon should be present
    has_emoji = (
        "\U0001f512" in out or "\u2601" in out
        or "\u26d4" in out or "\u2705" in out
    )
    assert has_emoji
