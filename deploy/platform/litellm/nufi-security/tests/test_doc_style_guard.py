"""문서 스타일 가드 테스트 — 명령 표기 규약(raw `python -m` 주 명령 금지).

두 가지를 검증:
  1. green-on-main — 현재 저장소에서 raw-모듈 주 명령 위반 0.
  2. 규칙 동작 — raw 모듈을 주 명령으로 쓰면 잡고, 폴백/CLI-리드/표준도구는 허용.

pytest 또는 `python3 tests/test_doc_style_guard.py` 로 실행.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_doc_style as g  # noqa: E402


def _flag(lines: list[str]) -> list[int]:
    """check_doc_style 의 주 명령 판정 로직을 임의 줄 목록에 적용(줄번호 1-base)."""
    hits: list[int] = []
    for i, line in enumerate(lines):
        if not g._RAW_MODULE.search(line):
            continue
        if any(lead in line for lead in g._CLI_LEAD):
            continue
        window = "\n".join(lines[max(0, i - 2): i + 1])
        if any(m in window for m in g._FALLBACK_MARKERS):
            continue
        hits.append(i + 1)
    return hits


# --- 1. green-on-main -----------------------------------------------------------
def test_repo_has_no_raw_module_main_command():
    """현재 main 에서 우리 모듈을 raw `python -m` 으로 주 명령 표기한 문서가 없어야 한다."""
    violations = g.scan_raw_module_commands()
    assert violations == [], (
        "raw 모듈 주 명령 표기 발견:\n"
        + "\n".join(f"{r}:{ln}: {c}" for r, ln, c in violations)
    )


# --- 2. 규칙 동작(긍정/부정) ----------------------------------------------------
def test_raw_module_main_command_is_flagged():
    assert _flag(["sudo python3 -m enforcement.cli apply"]) == [1]


def test_labeled_fallback_is_allowed():
    # 같은 줄 또는 직전 2줄의 폴백 표지가 있으면 허용.
    assert _flag(["> 비설치 동치: python3 -m enforcement.cli doctor"]) == []
    assert _flag(["설치하지 않은 환경에서는 동일 명령을",
                  "`python3 -m enforcement.cli <서브커맨드>` 로 실행."]) == []
    assert _flag(["레거시 `python3 -m egress_audit.audit_bot` 도 하위호환."]) == []


def test_cli_lead_on_same_line_is_allowed():
    assert _flag(["journalctl | nufi-egress feedback --counter x  "
                  "# 동치: python3 -m enforcement.cli feedback"]) == []


def test_standard_tools_not_flagged():
    # pip/pytest 등은 우리 모듈이 아니므로 대상 외.
    assert _flag(["python3 -m pip install -e .",
                  "python3 -m pytest tests/ -q"]) == []


if __name__ == "__main__":  # pragma: no cover
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
