"""docs 정합성 자동 가드 테스트 (CMP-117).

두 가지를 검증:
  1. green-on-main — 현재 저장소에서 모든 검사 통과(드리프트 0).
  2. 의도적 드리프트 재현 — 인용 심볼 rename·버전 불일치·깨진 mermaid·깨진 링크 시 검사 실패.

pytest 또는 `python3 tests/test_docs_consistency.py` 로 실행.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_docs as cd  # noqa: E402


# --- 1. green-on-main -----------------------------------------------------------
def test_repo_docs_are_consistent():
    """현재 main 에서 docs 정합성 가드가 통과(green)해야 한다."""
    checks, errors = cd.run_all(ROOT)
    assert errors == [], "main 에서 docs 드리프트 발견:\n" + "\n".join(errors)
    # 실제로 무언가를 검사했는지(빈 통과 방지) 확인.
    names = " ".join(n for n, _ in checks)
    assert "Mermaid" in names and "식별자" in names and "버전" in names and "링크" in names


# --- 2. 의도적 드리프트 재현 ----------------------------------------------------
def test_identifier_rename_drift_fails():
    """ARCHITECTURE 가 인용한 심볼이 코드에서 rename 되면(코드에 없으면) 실패해야 한다."""
    classes, all_defs = cd.build_symbol_index(ROOT)
    text = "표면: `Gateway.processRENAMED()` 진입점."
    errs, n = cd.crosscheck_identifiers(text, ROOT, ROOT / "docs", classes, all_defs, "x.md")
    assert n == 1 and errs, "인용 심볼 rename 드리프트를 잡지 못함"
    assert "processRENAMED" in errs[0]


def test_missing_class_drift_fails():
    classes, all_defs = cd.build_symbol_index(ROOT)
    errs, _ = cd.crosscheck_identifiers("`GhostClass.method()`", ROOT, ROOT / "docs",
                                        classes, all_defs, "x.md")
    assert errs and "GhostClass" in errs[0]


def test_missing_function_drift_fails():
    classes, all_defs = cd.build_symbol_index(ROOT)
    errs, _ = cd.crosscheck_identifiers("`totally_made_up_fn()`", ROOT, ROOT / "docs",
                                        classes, all_defs, "x.md")
    assert errs and "totally_made_up_fn" in errs[0]


def test_missing_file_drift_fails():
    classes, all_defs = cd.build_symbol_index(ROOT)
    errs, _ = cd.crosscheck_identifiers("`gateway/does_not_exist.py`", ROOT, ROOT / "docs",
                                        classes, all_defs, "x.md")
    assert errs and "does_not_exist.py" in errs[0]


def test_real_symbols_pass():
    """실제 존재하는 심볼/파일은 통과(false positive 없음)."""
    classes, all_defs = cd.build_symbol_index(ROOT)
    text = ("`Gateway.process()` `Router.resolve()` `AuditLogger.log/verify_chain` "
            "`render_ruleset()` `gateway/core.py` `config/policy.yaml`")
    errs, n = cd.crosscheck_identifiers(text, ROOT, ROOT / "docs", classes, all_defs, "x.md")
    assert errs == [], f"실제 심볼에서 오탐: {errs}"
    assert n == 6


def test_version_mismatch_fails():
    assert cd.check_version_pair("0.0.1", "## [0.0.1] - x\n") == []
    errs = cd.check_version_pair("0.0.2", "## [0.0.1] - x\n")
    assert errs and "불일치" in errs[0]
    assert cd.check_version_pair("0.0.1", "헤더 없음")  # 헤더 못 찾으면 실패


def test_broken_mermaid_fails():
    assert cd.lint_mermaid("```mermaid\nflowchart TB\n a-->b\n```\n", "x") == []
    # 닫히지 않은 블록
    assert cd.lint_mermaid("```mermaid\nflowchart TB\n a-->b\n", "x")
    # 빈 블록
    assert cd.lint_mermaid("```mermaid\n```\n", "x")
    # 알 수 없는 다이어그램 타입
    assert cd.lint_mermaid("```mermaid\nNOTADIAGRAM foo\n```\n", "x")
    # 인라인 ` ```mermaid ` 언급은 펜스로 오인하지 않음
    assert cd.lint_mermaid("코드펜스 ` ```mermaid ` 태그 유지.\n", "x") == []


def test_broken_link_fails(tmp_path):
    errs, n = cd.check_links_text("[x](./nope-missing.md)", tmp_path, "x.md")
    assert errs and n == 1
    # 외부/앵커 링크는 건너뜀
    errs2, n2 = cd.check_links_text("[a](https://e.com) [b](#anchor)", tmp_path, "x.md")
    assert errs2 == [] and n2 == 0


# --- 정확도 수치 ↔ 근거 리포트 추적 (v0.2.2) -----------------------------------
def test_number_fmt_and_dig():
    assert cd.fmt_report_number(0.9433) == "0.9433"
    assert cd.fmt_report_number(41.0) == "41"      # 정수값 float 은 소수점 제거
    assert cd.fmt_report_number(True) == "True"
    rep = {"scores": {"pii_recall": 0.9433, "ci": [0.9098, 0.9648]}, "sweep": {"1": {"p95": 41.0}}}
    assert cd.dig_json(rep, ("scores", "pii_recall")) == 0.9433
    assert cd.dig_json(rep, ("scores", "ci", 1)) == 0.9648
    assert cd.dig_json(rep, ("sweep", "1", "p95")) == 41.0


def test_number_integrity_matches_and_drifts():
    reports = {"r.json": {"scores": {"pii_recall": 0.9433}, "sweep": {"1": {"p95": 41.0}}}}
    claims = [
        ("doc.md", "r.json", ("scores", "pii_recall"), "recall"),
        ("doc.md", "r.json", ("sweep", "1", "p95"), "p95"),
    ]
    # 문서가 현재 리포트 값을 인용하면 통과.
    ok = cd.check_number_integrity(claims, {"doc.md": "재현율 0.9433, 지연 41 ms"}, reports)
    assert ok == [], f"일치인데 오탐: {ok}"
    # 문서가 옛 값(0.946/38ms)으로 남으면 드리프트로 실패.
    drift = cd.check_number_integrity(claims, {"doc.md": "재현율 0.946, 지연 38 ms"}, reports)
    assert len(drift) == 2 and all("드리프트" in e for e in drift)


def test_number_integrity_missing_report_and_path():
    claims = [("doc.md", "gone.json", ("a",), "x")]
    errs = cd.check_number_integrity(claims, {"doc.md": "t"}, {})
    assert errs and "근거 리포트 없음" in errs[0]
    errs2 = cd.check_number_integrity([("doc.md", "r.json", ("nope",), "x")],
                                      {"doc.md": "t"}, {"r.json": {"a": 1}})
    assert errs2 and "경로 없음" in errs2[0]


# --- 3. CLI 서브커맨드 ↔ docs/CLI.md 동기화 (CMP-282) -------------------------
import re as _re


def _cli_registered_subcommands() -> set[str]:
    """enforcement/cli.py 에서 `sub.add_parser(...)` 로 등록된 최상위 서브커맨드 집합."""
    cli_src = (ROOT / "enforcement" / "cli.py").read_text()
    # 패턴: `p = sub.add_parser("name"` — 최상위 서브파서만 매칭
    return set(_re.findall(r'p\s*=\s*sub\.add_parser\(\s*"([^"]+)"', cli_src))


def _cli_md_subcommands() -> set[str]:
    """docs/CLI.md 서브커맨드 표에서 행을 추출."""
    cli_md = (ROOT / "docs" / "CLI.md").read_text()
    # 패턴: `| [`name`](...) |` 형태의 테이블 행
    return set(_re.findall(r'^\|\s*\[`([a-z][\w-]*)`\]', cli_md, _re.MULTILINE))


def test_cli_subcommand_sync():
    """enforcement/cli.py 서브커맨드 수와 docs/CLI.md 서브커맨드 표 행 수가 일치해야 한다."""
    code_cmds = _cli_registered_subcommands()
    doc_cmds = _cli_md_subcommands()
    missing_in_docs = code_cmds - doc_cmds
    extra_in_docs = doc_cmds - code_cmds
    msgs: list[str] = []
    if missing_in_docs:
        msgs.append(f"CLI.md 에 누락된 서브커맨드({len(missing_in_docs)}): {sorted(missing_in_docs)}")
    if extra_in_docs:
        msgs.append(f"CLI.md 에 코드에 없는 서브커맨드({len(extra_in_docs)}): {sorted(extra_in_docs)}")
    assert not msgs, "CLI 서브커맨드 동기화 실패:\n" + "\n".join(msgs)


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            import inspect
            if "tmp_path" in inspect.signature(fn).parameters:
                import tempfile
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            print(f"  PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"  FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
