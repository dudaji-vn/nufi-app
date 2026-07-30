"""surrogate 델리미터 설정 가능성 검증.

기본값(⟦…⟧)은 그대로 두고, NUFI_SURROGATE_DELIMS 환경변수 또는
surrogate.set_delimiters() 로 교체할 수 있어야 한다.

배경(측정, 2026-07-29, gemini-2.5-flash, 같은 프롬프트 n=6, temperature 1.0):
모델이 토큰을 그대로 되돌려주는 비율은 ⟦E1⟧ 0/6, [[E1]] 2/6, <E1> 6/6 이었다.
기본 델리미터는 통째로 제거되어 E1 만 돌아오고, _LENIENT 는 양쪽 괄호를
요구하므로 매칭되지 않아 복원이 조용히 실패한다. 배포 환경마다 모델이 다르므로
델리미터를 고를 수 있어야 한다.
"""
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from egress_audit import surrogate as S

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _restore_delims():
    """각 테스트 후 모듈 전역을 기본값으로 되돌린다."""
    lb, rb = S.LB, S.RB
    yield
    S.set_delimiters(lb, rb)


def test_default_is_unchanged():
    """기존 동작 보존 — 환경변수가 없으면 ⟦…⟧ 그대로."""
    assert (S._DEFAULT_LB, S._DEFAULT_RB) == ("⟦", "⟧")
    assert S.make_surrogate("E", 1) == "⟦E1⟧"


def test_set_delimiters_changes_minting_and_matching():
    S.set_delimiters("<", ">")

    assert S.make_surrogate("E", 1) == "<E1>"
    assert S._EXACT.search("보내는 곳 <E1> 입니다")
    assert not S._EXACT.search("보내는 곳 ⟦E1⟧ 입니다")


def test_lenient_still_requires_brackets_on_both_sides():
    """맨 E1 은 매칭되면 안 된다.

    E1/P1/T2 는 셀 참조·부품번호 같은 평범한 문자열이다. 괄호 없이 넓히면
    정상 텍스트를 손상시키므로, 델리미터를 바꿔도 이 제약은 유지되어야 한다.
    """
    S.set_delimiters("<", ">")

    assert S._LENIENT.search("[E1]")
    assert S._LENIENT.search("(E1)")
    assert S._LENIENT.search("<E1>")
    assert not S._LENIENT.search("보내는 곳 E1 입니다")


def test_max_surrogate_len_follows_the_delimiter_length():
    """스트리밍 홀드 상한이 델리미터 길이를 반영해야 한다.

    고정 16 이면 긴 델리미터에서 미완결 토큰이 상한을 넘겨 잘린 채 방출된다.
    """
    S.set_delimiters("⟦", "⟧")
    short = S.MAX_SURROGATE_LEN
    S.set_delimiters("[[", "]]")

    assert S.MAX_SURROGATE_LEN > short


def test_empty_delimiter_is_refused():
    """빈 델리미터는 _EXACT 를 모든 곳에 매칭시켜 원문을 파괴한다."""
    with pytest.raises(ValueError):
        S.set_delimiters("", ">")
    with pytest.raises(ValueError):
        S.set_delimiters("<", "")


def test_regex_metacharacters_in_delimiters_are_escaped():
    """`(` 같은 델리미터도 리터럴로 취급되어야 한다 — 정규식으로 새면 오작동."""
    S.set_delimiters("((", "))")

    assert S.make_surrogate("E", 7) == "((E7))"
    assert S._EXACT.search("((E7))")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("<,>", ("<", ">")),
        ("[[,]]", ("[[", "]]")),
        (" < , > ", ("<", ">")),
        ("", ("⟦", "⟧")),
        ("no-comma", ("⟦", "⟧")),
        (",", ("⟦", "⟧")),
        ("a,b,c", ("⟦", "⟧")),
    ],
)
def test_env_var_parsing(raw, expected):
    """잘못된 값은 조용히 기본값으로 — 시작 시 예외로 서비스를 죽이지 않는다.

    별도 프로세스로 확인한다. 델리미터는 import 시점에 결정되므로 같은
    프로세스에서 환경변수만 바꿔서는 검증할 수 없다.
    """
    env = dict(os.environ, NUFI_SURROGATE_DELIMS=raw)
    code = "from egress_audit import surrogate as S; print(repr(S.LB), repr(S.RB))"
    out = subprocess.run(
        [sys.executable, "-c", code], env=env, cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    assert out == f"{expected[0]!r} {expected[1]!r}"


def test_module_reload_picks_up_the_env_var():
    """import 시점 결정이 실제로 환경변수를 읽는지 확인."""
    os.environ["NUFI_SURROGATE_DELIMS"] = "<,>"
    try:
        reloaded = importlib.reload(S)
        assert (reloaded.LB, reloaded.RB) == ("<", ">")
    finally:
        os.environ.pop("NUFI_SURROGATE_DELIMS", None)
        importlib.reload(S)
