"""CMP-249 v0.4.6 SDK 편의 함수 검증.

검증 항목:
  1. scan_file — 텍스트 파일에서 PII 탐지.
  2. guard_file — 텍스트 파일 정책 평가.
  3. batch_detect — 여러 텍스트 한 번에 탐지.

실행: python3 tests/test_cmp249_sdk_helpers.py  (FAIL → exit 1)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("EGRESS_NER_BACKEND", "gazetteer")

from nufi import scan_file, guard_file, batch_detect, Finding, GuardResult  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(crit: str, ok: bool, detail: str = ""):
    results.append((crit, ok, detail))
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {crit}" + (f" — {detail}" if detail else ""))


def test_scan_file():
    print("\n=== 1. scan_file ===")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                      encoding="utf-8") as f:
        f.write("김민수님 주민번호 900101-1234568 계좌 110-123-456789")
        tmp = f.name
    try:
        findings = scan_file(tmp)
        check("scan_file 반환 타입", isinstance(findings, list))
        check("scan_file Finding 타입", all(isinstance(f, Finding) for f in findings))
        types = {f.entity_type for f in findings}
        check("scan_file KR_RRN 탐지", "KR_RRN" in types, f"types={types}")
        check("scan_file KR_ACCOUNT 탐지", "KR_ACCOUNT" in types, f"types={types}")
    finally:
        os.unlink(tmp)

    # 빈 파일
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                      encoding="utf-8") as f:
        f.write("hello world")
        tmp = f.name
    try:
        findings = scan_file(tmp)
        check("scan_file 무해 텍스트 0건", len(findings) == 0, f"count={len(findings)}")
    finally:
        os.unlink(tmp)


def test_guard_file():
    print("\n=== 2. guard_file ===")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                      encoding="utf-8") as f:
        f.write("주민번호 900101-1234568")
        tmp = f.name
    try:
        result = guard_file(tmp)
        check("guard_file 반환 타입", isinstance(result, GuardResult))
        check("guard_file 차단", result.blocked, f"blocked={result.blocked}")
    finally:
        os.unlink(tmp)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                      encoding="utf-8") as f:
        f.write("안녕하세요")
        tmp = f.name
    try:
        result = guard_file(tmp)
        check("guard_file 허용", not result.blocked, f"blocked={result.blocked}")
    finally:
        os.unlink(tmp)


def test_batch_detect():
    print("\n=== 3. batch_detect ===")
    texts = [
        "주민번호 900101-1234568",
        "안녕하세요",
        "계좌번호 110-123-456789",
    ]
    results_list = batch_detect(texts)
    check("batch_detect 반환 길이", len(results_list) == 3, f"len={len(results_list)}")
    check("batch_detect 각 항목 리스트",
          all(isinstance(r, list) for r in results_list))
    check("batch_detect [0] PII 있음", len(results_list[0]) > 0,
          f"count={len(results_list[0])}")
    check("batch_detect [1] PII 없음", len(results_list[1]) == 0,
          f"count={len(results_list[1])}")
    check("batch_detect [2] PII 있음", len(results_list[2]) > 0,
          f"count={len(results_list[2])}")

    # 빈 리스트
    empty = batch_detect([])
    check("batch_detect 빈 입력", empty == [], f"result={empty}")


if __name__ == "__main__":
    print("CMP-249 v0.4.6 — SDK 편의 함수 검증")
    test_scan_file()
    test_guard_file()
    test_batch_detect()

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{'='*40}")
    print(f"결과: {passed}/{total} PASS")
    if passed < total:
        for c, ok, d in results:
            if not ok:
                print(f"  FAIL: {c} — {d}")
        sys.exit(1)
    print("모든 검증 통과.")
