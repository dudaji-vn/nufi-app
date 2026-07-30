#!/usr/bin/env python3
"""docs 정합성 자동 가드 (CMP-117).

ARCHITECTURE.md §7 의 '사람이 기억하는 드리프트 방지 체크리스트' 를 '기계가 강제하는 가드' 로
승격한다. CI/pre-commit 에서 PR 마다 실행 → 흐름을 바꾸는 PR 이 문서 동시 갱신을 빠뜨리면 실패.

검사 (living 문서 한정):
  1. Mermaid lint      — ```mermaid 코드펜스의 밸런스/비어있음/다이어그램 타입 검사 (깨진 블록 0).
  2. 식별자 교차검증    — ARCHITECTURE.md 가 인용한 모듈/클래스/함수가 실제 코드에 존재하는지 AST 대조.
  3. 버전 정합          — VERSION == CHANGELOG.md 최신 [x.y.z] 헤더.
  4. 내부 링크 (선택)   — living 문서의 상대 링크가 실제로 resolve 되는지.
  5. 정확도 수치 추적   — 공개 문서의 정확도·성능 헤드라인 수치가 커밋된 근거 리포트(docs/reports/*.json)
                          값과 일치하는지 대조. 리포트가 갱신됐는데 문서가 안 따라오면(또는 그 반대) 실패.

living vs frozen:
  living  = 현행 정합 대상(드리프트 검사 ON).
  frozen  = 마일스톤 SPEC*/IMPL/DEMO/측정 리포트 등 역사적 스냅샷 → 검사 제외.

순수 헬퍼(lint_mermaid / crosscheck_identifiers / check_version_pair / check_links_text)는
tests/test_docs_consistency.py 에서 합성 드리프트로 단위 검증한다. stdlib 만 사용(외부 의존성 0).
실패 시 종료코드 1.  사용:  python scripts/check_docs.py [--verbose]
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# --- living 문서 (현행 정합 대상) -------------------------------------------------
ARCHITECTURE = "docs/ARCHITECTURE.md"
LIVING_MD = [
    ARCHITECTURE,
    "README.md",
    "docs/README.md",
    "CHANGELOG.md",
]
VERSION_FILE = "VERSION"
CHANGELOG = "CHANGELOG.md"

# 식별자 교차검증 대상: 단일 권위 문서만 (frozen SPEC/IMPL/DEMO 는 역사적 스냅샷이라 제외).
IDENTIFIER_DOC = ARCHITECTURE

# --- 정확도·성능 수치 ↔ 근거 리포트 추적 -------------------------------------------
# 공개 문서에 실린 헤드라인 수치는 커밋된 리포트(docs/reports/*.json)의 현재 값을 그대로
# 인용해야 한다. 리포트가 바뀌면(또는 문서만 옛 값으로 남으면) 이 대조가 실패한다.
# json_path 는 리포트 dict 를 파고드는 키/인덱스 시퀀스. 각 항목의 값 문자열이 문서에
# 그대로 등장하는지(presence) 검사 — 드리프트(공개 수치 ≠ 근거) 재발 차단.
NUMBER_CLAIMS = [
    # README 성능·정확도 요약표 + 하단 서술
    ("README.md", "docs/reports/recall-int8.json", ("scores", "pii_recall"), "전체 PII recall"),
    ("README.md", "docs/reports/recall-int8.json", ("scores", "pii_recall_ci95", 0), "PII recall CI 하한"),
    ("README.md", "docs/reports/recall-int8.json", ("scores", "pii_recall_ci95", 1), "PII recall CI 상한"),
    ("README.md", "docs/reports/recall-int8.json", ("scores", "span_precision"), "정밀도(span)"),
    ("README.md", "docs/reports/load-p95.json", ("concurrency_sweep", "1", "lat_p95_ms"), "인라인 지연 p95(c=1)"),
    ("README.md", "docs/reports/kr-location-gate.json", ("after_v0.2.0", "test", "kr_location_ci95_low"), "KR_LOCATION CI 하한"),
    ("README.md", "docs/reports/recall-int8.json", ("scores", "person_recall"), "KR_PERSON recall"),
    ("README.md", "docs/reports/recall-int8.json", ("scores", "person_recall_ci_low"), "KR_PERSON CI 하한"),
    # docs/README 한 줄 요약
    ("docs/README.md", "docs/reports/recall-int8.json", ("scores", "pii_recall"), "전체 PII recall"),
    ("docs/README.md", "docs/reports/load-p95.json", ("concurrency_sweep", "1", "lat_p95_ms"), "인라인 지연 p95(c=1)"),
]

VALID_MERMAID_TYPES = (
    "flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram",
    "stateDiagram-v2", "erDiagram", "gantt", "pie", "journey", "gitGraph",
    "mindmap", "timeline", "quadrantChart", "C4Context", "C4Container",
)


# ============================================================================
# 순수 헬퍼 — 파일시스템 부수효과 없이 텍스트만 검사 (테스트 가능 단위)
# ============================================================================
def _iter_fences(text: str):
    """코드펜스를 (lang, body, open_line, closed) 로 yield. 줄 시작의 ``` 만 펜스로 인정
    (인라인 ` ```mermaid ` 언급은 무시)."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^\s*```([A-Za-z0-9_-]*)\s*$", lines[i])
        if not m:
            i += 1
            continue
        lang, open_line, body = m.group(1), i + 1, []
        i += 1
        closed = False
        while i < len(lines):
            if re.match(r"^\s*```\s*$", lines[i]):
                closed = True
                i += 1
                break
            body.append(lines[i])
            i += 1
        yield lang, "\n".join(body), open_line, closed


def lint_mermaid(text: str, label: str) -> list[str]:
    """mermaid 코드펜스 밸런스/비어있음/다이어그램 타입 검사. 오류 메시지 리스트 반환."""
    errs: list[str] = []
    if len(re.findall(r"(?m)^\s*```", text)) % 2 != 0:
        errs.append(f"[mermaid] {label}: 코드펜스 ``` 가 짝이 맞지 않음(닫히지 않은 블록)")
    for lang, body, ln, closed in _iter_fences(text):
        if lang != "mermaid":
            continue
        if not closed:
            errs.append(f"[mermaid] {label}:{ln}: mermaid 블록이 닫히지 않음")
            continue
        content = [l for l in body.splitlines()
                   if l.strip() and not l.strip().startswith("%%")]
        if not content:
            errs.append(f"[mermaid] {label}:{ln}: 빈 mermaid 블록")
            continue
        first = content[0].strip()
        if not any(first == t or first.startswith(t) for t in VALID_MERMAID_TYPES):
            errs.append(f"[mermaid] {label}:{ln}: 알 수 없는 다이어그램 타입 '{first[:40]}'")
    return errs


def count_mermaid(text: str) -> int:
    return sum(1 for lang, *_ in _iter_fences(text) if lang == "mermaid")


_BACKTICK = re.compile(r"`([^`\n]+)`")
_PATH_TOKEN = re.compile(r"^[\w./*\-]+\.(?:py|ya?ml|md)$")
_DOTTED_SYM = re.compile(r"^[A-Z]\w*\.")
_FUNC_CALL = re.compile(r"^([a-z_][a-z0-9_]+)\(\)$")


def _path_token_exists(tok: str, root: Path, doc_dir: Path) -> bool:
    """인용 파일/glob 이 저장소에 존재하는지. 디렉터리 구분자 없는 bare 파일명은 basename 으로
    재귀 탐색, 경로 포함 토큰은 repo 루트와 문서 디렉터리 양쪽 기준으로 resolve."""
    if "*" in tok:
        return bool(list(root.glob(tok)) or list(doc_dir.glob(tok)))
    if "/" not in tok:  # bare 파일명: 서브디렉터리 어디든 존재하면 OK.
        return any(True for _ in root.rglob(tok))
    return (root / tok).exists() or (doc_dir / tok).exists()


def crosscheck_identifiers(text: str, root: Path, doc_dir: Path,
                           classes: dict[str, set[str]], all_defs: set[str],
                           label: str) -> tuple[list[str], int]:
    """백틱 인용 토큰을 코드 심볼과 대조. (오류 리스트, 검사한 토큰 수) 반환.

    토큰 분류:
      (a) 파일/glob 경로 (`.py`/`.yaml`/`.md`)  → 실제 존재 확인.
      (b) `Class.method` / `Class.m1/m2`        → 클래스+메서드 존재 확인.
      (c) `name()` 함수 호출                      → 동일 이름 def 존재 확인.
      그 외(프로즈/설정키)는 검사 대상 아님.
    """
    errs: list[str] = []
    n = 0
    for raw in _BACKTICK.findall(text):
        tok = raw.strip()
        if _PATH_TOKEN.match(tok):
            n += 1
            if not _path_token_exists(tok, root, doc_dir):
                errs.append(f"[ident] {label}: 인용 파일 없음 `{tok}` (드리프트?)")
            continue
        if _DOTTED_SYM.match(tok):
            clean = re.sub(r"\(.*?\)", "", tok)  # 인자/괄호 제거
            parts = clean.split(".")
            if len(parts) < 2:
                continue
            cls = parts[0]
            methods = [m.strip() for m in parts[1].split("/") if m.strip()]
            n += 1
            if cls not in classes:
                errs.append(f"[ident] {label}: 클래스 없음 `{cls}` (인용 `{tok}` 드리프트?)")
                continue
            for meth in methods:
                if meth not in classes[cls]:
                    errs.append(f"[ident] {label}: `{cls}.{meth}` 메서드 없음 (드리프트?)")
            continue
        fm = _FUNC_CALL.match(tok)
        if fm:
            n += 1
            if fm.group(1) not in all_defs:
                errs.append(f"[ident] {label}: 함수 `{fm.group(1)}()` 정의 없음 (드리프트?)")
    return errs, n


_CHANGELOG_HDR = re.compile(r"(?m)^##\s*\[(\d+\.\d+\.\d+)\]")


def check_version_pair(version_str: str, changelog_text: str) -> list[str]:
    """VERSION 문자열과 CHANGELOG 최신 [x.y.z] 헤더 정합."""
    version = version_str.strip()
    m = _CHANGELOG_HDR.search(changelog_text)
    if not m:
        return ["[version] CHANGELOG 에서 최신 [x.y.z] 헤더를 찾지 못함"]
    if m.group(1) != version:
        return [f"[version] VERSION={version!r} 와 CHANGELOG 최신 [{m.group(1)}] 불일치"]
    return []


_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def check_links_text(text: str, base_dir: Path, label: str) -> tuple[list[str], int]:
    """마크다운 상대 링크가 resolve 되는지. (오류 리스트, 검사한 링크 수) 반환.
    http(s)/mailto/앵커(#)는 건너뜀."""
    errs: list[str] = []
    n = 0
    for target in _MD_LINK.findall(text):
        target = target.split()[0].strip()  # "(path \"title\")" 의 title 제거
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        ref = target.split("#", 1)[0]  # 앵커 제거
        if not ref:
            continue
        n += 1
        if not (base_dir / ref).resolve().exists():
            errs.append(f"[links] {label}: 깨진 내부 링크 → {target}")
    return errs, n


def fmt_report_number(v) -> str:
    """리포트 JSON 값을 문서에 등장하는 표기로 정규화. 정수값 float(41.0)은 '41',
    그 외 float 는 최단 왕복 표기(0.9433)."""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    return str(v)


def dig_json(obj, path):
    """키/인덱스 시퀀스로 dict/list 를 파고든다. 없으면 KeyError/IndexError/TypeError."""
    cur = obj
    for k in path:
        cur = cur[k] if isinstance(cur, dict) else cur[int(k)]
    return cur


def check_number_integrity(claims, doc_texts: dict, reports: dict) -> list[str]:
    """공개 문서의 헤드라인 수치가 근거 리포트의 현재 값과 일치하는지 대조.
    claims = [(doc_rel, report_rel, json_path, label), ...].
    doc_texts[doc_rel] = 문서 텍스트, reports[report_rel] = 파싱된 JSON.
    각 값 문자열이 문서에 등장하지 않으면(=드리프트) 오류를 낸다. 순수 함수(테스트 가능)."""
    errs: list[str] = []
    for doc_rel, report_rel, jpath, label in claims:
        text = doc_texts.get(doc_rel)
        if text is None:
            errs.append(f"[number] 문서 텍스트 없음: {doc_rel}")
            continue
        rep = reports.get(report_rel)
        if rep is None:
            errs.append(f"[number] 근거 리포트 없음: {report_rel}")
            continue
        try:
            val = dig_json(rep, jpath)
        except (KeyError, IndexError, TypeError, ValueError):
            errs.append(f"[number] {report_rel} 경로 없음: {'/'.join(map(str, jpath))}")
            continue
        s = fmt_report_number(val)
        if s not in text:
            errs.append(
                f"[number] {doc_rel}: {label} 값 '{s}'(근거 {report_rel}#{'/'.join(map(str, jpath))}) "
                f"가 문서에 없음 — 공개 수치가 리포트와 드리프트")
    return errs


def build_symbol_index(root: Path) -> tuple[dict[str, set[str]], set[str]]:
    """저장소 전체 .py 를 AST 로 스캔 → (classes{name:{methods}}, all_defs{모든 def 이름})."""
    classes: dict[str, set[str]] = {}
    all_defs: set[str] = set()
    skip = {".git", "__pycache__", ".pytest_cache", ".venv", "node_modules"}
    for p in root.rglob("*.py"):
        if any(part in skip for part in p.parts):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.setdefault(node.name, set()).update(
                    m.name for m in node.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                all_defs.add(node.name)
    return classes, all_defs


# ============================================================================
# 오케스트레이션 — 실제 저장소 파일에 헬퍼 적용
# ============================================================================
def run_all(root: Path, verbose: bool = False) -> tuple[list[tuple[str, int]], list[str]]:
    checks: list[tuple[str, int]] = []
    errors: list[str] = []

    # 1. Mermaid (모든 living .md)
    n_blocks, merr = 0, []
    for rel in LIVING_MD:
        path = root / rel
        if not path.exists():
            merr.append(f"[mermaid] living 문서 누락: {rel}")
            continue
        t = path.read_text(encoding="utf-8")
        n_blocks += count_mermaid(t)
        merr += lint_mermaid(t, rel)
    checks.append((f"Mermaid lint ({n_blocks} 블록)", len(merr)))
    errors += merr

    # 2. 식별자 교차검증 (단일 권위 문서)
    classes, all_defs = build_symbol_index(root)
    apath = root / IDENTIFIER_DOC
    if apath.exists():
        ierr, n_ident = crosscheck_identifiers(
            apath.read_text(encoding="utf-8"), root, apath.parent,
            classes, all_defs, IDENTIFIER_DOC)
    else:
        ierr, n_ident = [f"[ident] 검증 대상 문서 누락: {IDENTIFIER_DOC}"], 0
    checks.append((f"식별자 교차검증 ({n_ident}개)", len(ierr)))
    errors += ierr

    # 3. 버전 정합
    vpath, cpath = root / VERSION_FILE, root / CHANGELOG
    if vpath.exists() and cpath.exists():
        verr = check_version_pair(vpath.read_text(encoding="utf-8"),
                                  cpath.read_text(encoding="utf-8"))
    else:
        verr = [f"[version] {VERSION_FILE} 또는 {CHANGELOG} 없음"]
    checks.append(("버전 정합", len(verr)))
    errors += verr

    # 4. 내부 링크 (선택)
    lerr, n_links = [], 0
    for rel in LIVING_MD:
        path = root / rel
        if not path.exists():
            continue
        e, n = check_links_text(path.read_text(encoding="utf-8"), path.parent, rel)
        lerr += e
        n_links += n
    checks.append((f"내부 링크 ({n_links}개)", len(lerr)))
    errors += lerr

    # 5. 정확도·성능 수치 ↔ 근거 리포트 추적
    doc_texts: dict = {}
    for doc_rel in {c[0] for c in NUMBER_CLAIMS}:
        p = root / doc_rel
        if p.exists():
            doc_texts[doc_rel] = p.read_text(encoding="utf-8")
    reports: dict = {}
    nerr: list[str] = []
    for rep_rel in {c[1] for c in NUMBER_CLAIMS}:
        p = root / rep_rel
        if not p.exists():
            nerr.append(f"[number] 근거 리포트 파일 없음: {rep_rel}")
            continue
        try:
            reports[rep_rel] = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            nerr.append(f"[number] 리포트 JSON 파싱 실패: {rep_rel} ({e})")
    nerr += check_number_integrity(NUMBER_CLAIMS, doc_texts, reports)
    checks.append((f"정확도 수치 추적 ({len(NUMBER_CLAIMS)}건)", len(nerr)))
    errors += nerr

    return checks, errors


def main() -> int:
    ap = argparse.ArgumentParser(description="docs 정합성 자동 가드")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    checks, errors = run_all(REPO, verbose=args.verbose)

    print("\n=== docs 정합성 가드 ===")
    for name, n_err in checks:
        print(f"  [{'FAIL' if n_err else ' OK '}] {name}" + (f" — {n_err} 오류" if n_err else ""))
    if errors:
        print(f"\n드리프트 {len(errors)}건 발견:")
        for e in errors:
            print(f"  ✗ {e}")
        print("\n→ ARCHITECTURE.md §7 체크리스트대로 문서를 코드와 같은 PR 에서 갱신하세요.")
        return 1
    print("\n✓ 모든 docs 정합성 검사 통과 (green).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
