"""guard CLI 커맨드 테스트 (v0.7.1 / CMP-336).

각 정책별 exit code + --format json + --strict + PII 없는 입력 검증.
pytest 또는 ``python3 tests/test_guard_cmd.py`` 로 실행.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PII_TEXT = "김철수의 전화번호는 010-1234-5678"
CLEAN_TEXT = "오늘 날씨가 좋습니다."


def _args(**kwargs):
    defaults = dict(
        target=None, policy_action_guard="warn", format="text",
        output=None, strict=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── PII 없는 입력 → exit 0 ────────────────────────────────────────────────
def test_guard_clean_exit_0():
    """PII 없는 텍스트 → exit 0 (모든 정책)."""
    from enforcement.guard_cmd import cmd_guard

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(CLEAN_TEXT)
        f.flush()
        for policy in ("block", "warn", "pseudonymize"):
            rc = cmd_guard(_args(target=f.name, policy_action_guard=policy))
            assert rc == 0, f"clean text should exit 0 with policy={policy}"


# ── block 정책 + PII → exit 1 ─────────────────────────────────────────────
def test_guard_block_exit_1():
    """PII 발견 + block → exit 1."""
    from enforcement.guard_cmd import cmd_guard

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(PII_TEXT)
        f.flush()
        rc = cmd_guard(_args(target=f.name, policy_action_guard="block"))
        assert rc == 1


# ── warn 정책 + PII → exit 2 ──────────────────────────────────────────────
def test_guard_warn_exit_2():
    """PII 발견 + warn → exit 2."""
    from enforcement.guard_cmd import cmd_guard

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(PII_TEXT)
        f.flush()
        rc = cmd_guard(_args(target=f.name, policy_action_guard="warn"))
        assert rc == 2


# ── pseudonymize 정책 → 가명화 출력 + exit 0 ──────────────────────────────
def test_guard_pseudonymize_exit_0():
    """PII 발견 + pseudonymize → 가명화 완료 + exit 0."""
    from enforcement.guard_cmd import cmd_guard

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(PII_TEXT)
        f.flush()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_guard(_args(target=f.name, policy_action_guard="pseudonymize"))
        assert rc == 0
        output = buf.getvalue()
        assert "pseudonymized" in output.lower() or "guard" in output.lower()


# ── pseudonymize + --output FILE ───────────────────────────────────────────
def test_guard_pseudonymize_output_file():
    """pseudonymize 정책 + --output FILE → 파일에 가명화 결과 기록."""
    from enforcement.guard_cmd import cmd_guard

    with tempfile.TemporaryDirectory() as td:
        inp = Path(td) / "input.txt"
        out = Path(td) / "output.txt"
        inp.write_text(PII_TEXT, encoding="utf-8")

        rc = cmd_guard(_args(
            target=str(inp), policy_action_guard="pseudonymize",
            output=str(out),
        ))
        assert rc == 0
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        # Original phone number should be pseudonymized
        assert "010-1234-5678" not in content


# ── --strict: warn → block 승격 ───────────────────────────────────────────
def test_guard_strict_promotes_warn_to_block():
    """--strict + warn(기본) → block 승격 → exit 1."""
    from enforcement.guard_cmd import cmd_guard

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(PII_TEXT)
        f.flush()
        rc = cmd_guard(_args(target=f.name, strict=True))
        assert rc == 1  # warn -> block -> exit 1


# ── --format json 출력 검증 ────────────────────────────────────────────────
def test_guard_format_json_clean():
    """--format json + clean text → valid JSON with status=clean."""
    from enforcement.guard_cmd import cmd_guard

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(CLEAN_TEXT)
        f.flush()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_guard(_args(target=f.name, format="json"))
        assert rc == 0
        data = json.loads(buf.getvalue())
        assert data["status"] == "clean"
        assert data["pii_found"] is False


def test_guard_format_json_block():
    """--format json + block policy + PII → valid JSON with status=blocked."""
    from enforcement.guard_cmd import cmd_guard

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(PII_TEXT)
        f.flush()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_guard(_args(
                target=f.name, policy_action_guard="block", format="json",
            ))
        assert rc == 1
        data = json.loads(buf.getvalue())
        assert data["status"] == "blocked"
        assert data["pii_found"] is True
        assert len(data["findings"]) >= 1


def test_guard_format_json_warn():
    """--format json + warn policy + PII → valid JSON with status=warn."""
    from enforcement.guard_cmd import cmd_guard

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(PII_TEXT)
        f.flush()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_guard(_args(
                target=f.name, policy_action_guard="warn", format="json",
            ))
        assert rc == 2
        data = json.loads(buf.getvalue())
        assert data["status"] == "warn"
        assert data["pii_found"] is True


def test_guard_format_json_pseudonymize():
    """--format json + pseudonymize policy + PII → valid JSON with session_id."""
    from enforcement.guard_cmd import cmd_guard

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(PII_TEXT)
        f.flush()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_guard(_args(
                target=f.name, policy_action_guard="pseudonymize", format="json",
            ))
        assert rc == 0
        data = json.loads(buf.getvalue())
        assert data["status"] == "pseudonymized"
        assert "session_id" in data
        assert data["pseudonymized_count"] >= 0
        assert "text" in data


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
