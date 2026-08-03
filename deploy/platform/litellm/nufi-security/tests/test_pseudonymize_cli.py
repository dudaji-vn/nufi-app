"""pseudonymize CLI 커맨드 + scan --pseudonymize 테스트 (v0.6.0~v0.6.1 / CMP-330, CMP-331).

pytest 또는 ``python3 tests/test_pseudonymize_cli.py`` 로 실행.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── pseudonymize CLI: 텍스트 모드 ──────────────────────────────────────────
def test_pseudonymize_text_mode():
    """인라인 텍스트 가명화 — PII가 surrogate로 치환되고 session_id 반환."""
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    args = SimpleNamespace(
        text="김철수의 전화번호는 010-1234-5678",
        file=None, output=None, restore=False,
        session="test-sess-1", json=False, format=None,
    )
    rc = cmd_pseudonymize(args)
    assert rc == 0


def test_pseudonymize_text_json():
    """--json 출력 — JSON에 session_id, transformed_text, pseudonymized_count 포함."""
    import io
    from contextlib import redirect_stdout
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    args = SimpleNamespace(
        text="이메일은 hong@dudaji.com 입니다",
        file=None, output=None, restore=False,
        session="json-sess", json=True, format=None,
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cmd_pseudonymize(args)
    assert rc == 0
    data = json.loads(buf.getvalue())
    assert data["mode"] == "pseudonymize"
    assert data["session_id"] == "json-sess"
    assert "transformed_text" in data
    assert data["pseudonymized_count"] >= 1
    # Original PII should not appear in transformed text
    assert "hong@dudaji.com" not in data["transformed_text"]


def test_pseudonymize_file_mode():
    """파일 가명화 — 입력 파일의 PII가 가명화되어 출력 파일에 저장."""
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    with tempfile.TemporaryDirectory() as td:
        inp = Path(td) / "input.txt"
        out = Path(td) / "output.txt"
        inp.write_text("전화번호 010-9999-8888 로 연락주세요.\n", encoding="utf-8")

        args = SimpleNamespace(
            text=None, file=str(inp), output=str(out),
            restore=False, session="file-sess", json=False, format=None,
        )
        rc = cmd_pseudonymize(args)
        assert rc == 0
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "010-9999-8888" not in content
        assert "⟦" in content


def test_pseudonymize_restore_mode():
    """가명화 → 원복 라운드트립이 무손실 (SDK RoundTrip 패턴)."""
    from egress_audit.reversible import ReversibleEgress

    # CLI의 pseudonymize/restore는 같은 프로세스 내 vault를 공유해야 원복 가능.
    # SDK의 RoundTrip 패턴으로 무손실 라운드트립 검증.
    rev = ReversibleEgress(ner_backend="gazetteer")
    src = "김민수 010-1234-5678"
    r = rev.pseudonymize(src, "rt-sess")
    assert not r.blocked
    assert r.pseudonymized >= 1
    # Restore
    restored, stats = rev.deanonymize(r.transformed_text, "rt-sess")
    assert restored == src


def test_pseudonymize_restore_cli():
    """CLI restore 모드 — 세션 ID 필수, 실행 성공 확인."""
    import io
    from contextlib import redirect_stdout
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    # restore 모드는 동일 프로세스 내에서 vault가 유지되지 않으므로
    # deanonymize가 실행되지만 매핑이 없어 fallback 처리됨.
    # CLI 자체가 오류 없이 동작하는지 확인.
    args = SimpleNamespace(
        text="⟦T1⟧ 테스트", file=None, output=None,
        restore=True, session="orphan-sess", json=True, format=None,
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cmd_pseudonymize(args)
    assert rc == 0
    data = json.loads(buf.getvalue())
    assert data["mode"] == "restore"


def test_pseudonymize_restore_requires_session():
    """--restore 시 --session 없으면 오류."""
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    args = SimpleNamespace(
        text="⟦P1⟧ 테스트", file=None, output=None,
        restore=True, session=None, json=False, format=None,
    )
    rc = cmd_pseudonymize(args)
    assert rc == 1


def test_pseudonymize_format_json():
    """--format json 옵션도 JSON 출력."""
    import io
    from contextlib import redirect_stdout
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    args = SimpleNamespace(
        text="전화 010-1234-5678", file=None, output=None,
        restore=False, session="fmt-sess", json=False, format="json",
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cmd_pseudonymize(args)
    assert rc == 0
    data = json.loads(buf.getvalue())
    assert data["mode"] == "pseudonymize"


def test_pseudonymize_no_input_error():
    """텍스트/파일 둘 다 없으면 오류."""
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    args = SimpleNamespace(
        text=None, file=None, output=None,
        restore=False, session=None, json=False, format=None,
    )
    rc = cmd_pseudonymize(args)
    assert rc == 1


def test_pseudonymize_blocked_text():
    """강한 PII(RRN) 포함 텍스트는 blocked 처리."""
    import io
    from contextlib import redirect_stdout
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    args = SimpleNamespace(
        text="주민번호 900101-1234568", file=None, output=None,
        restore=False, session="block-sess", json=True, format=None,
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cmd_pseudonymize(args)
    assert rc == 0
    data = json.loads(buf.getvalue())
    assert data["blocked"] is True


# ── scan --pseudonymize ────────────────────────────────────────────────────
def test_scan_pseudonymize():
    """scan --pseudonymize 로 PII 발견 파일의 가명화 텍스트 출력."""
    import io
    from contextlib import redirect_stdout, redirect_stderr
    from enforcement.scan_cmd import cmd_scan

    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "test.txt"
        f.write_text("홍길동의 이메일은 hong@test.com\n", encoding="utf-8")

        args = SimpleNamespace(
            target=str(f), pattern=None, check_injection=False,
            json=False, format=None, output=None, exclude=None,
            fail_on_pii=False, redact=False, dry_run=False,
            no_backup=False, stats=False, parallel=1, profile=None,
            summary_only=False, verbose=False, git_staged=False,
            ignore_file=None, baseline=None, count_only=False,
            min_score=0.0, only_types=None, cache=False,
            pseudonymize=True,
        )
        buf = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(err):
            rc = cmd_scan(args)
        assert rc == 0
        output = buf.getvalue()
        assert "가명화 결과" in output


def test_scan_pseudonymize_output_dir():
    """scan --pseudonymize --output <dir> 로 가명화 파일 저장."""
    import io
    from contextlib import redirect_stdout, redirect_stderr
    from enforcement.scan_cmd import cmd_scan

    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "data.txt"
        f.write_text("전화번호 010-1234-5678 확인\n", encoding="utf-8")
        out_dir = Path(td) / "out"

        args = SimpleNamespace(
            target=str(f), pattern=None, check_injection=False,
            json=False, format=None, output=str(out_dir), exclude=None,
            fail_on_pii=False, redact=False, dry_run=False,
            no_backup=False, stats=False, parallel=1, profile=None,
            summary_only=False, verbose=False, git_staged=False,
            ignore_file=None, baseline=None, count_only=False,
            min_score=0.0, only_types=None, cache=False,
            pseudonymize=True,
        )
        buf = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(err):
            rc = cmd_scan(args)
        assert rc == 0
        # Pseudonymized file should be saved
        out_file = out_dir / "data.txt"
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "010-1234-5678" not in content


# ── pseudonymize --check (v0.6.1 / CMP-331) ─────────────────────────────────
def test_pseudonymize_check_finds_pii():
    """--check 모드: PII 파일 → exit 1 + 가명화 제안."""
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "data.txt"
        f.write_text("이메일: hong@test.com\n", encoding="utf-8")

        args = SimpleNamespace(
            text=None, file=None, output=None, restore=False,
            session=None, json=False, format=None,
            check=True, filenames=[str(f)],
        )
        rc = cmd_pseudonymize(args)
        assert rc == 1


def test_pseudonymize_check_clean():
    """--check 모드: PII 없는 파일 → exit 0."""
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "clean.txt"
        f.write_text("No PII here, just a normal sentence.\n", encoding="utf-8")

        args = SimpleNamespace(
            text=None, file=None, output=None, restore=False,
            session=None, json=False, format=None,
            check=True, filenames=[str(f)],
        )
        rc = cmd_pseudonymize(args)
        assert rc == 0


def test_pseudonymize_check_no_files():
    """--check 모드: 파일 없으면 exit 0."""
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    args = SimpleNamespace(
        text=None, file=None, output=None, restore=False,
        session=None, json=False, format=None,
        check=True, filenames=[],
    )
    rc = cmd_pseudonymize(args)
    assert rc == 0


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} pseudonymize CLI tests PASS")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
