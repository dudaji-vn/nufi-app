"""pseudonymize --quality-report 품질 메트릭 리포트 테스트 (v0.7.2 / CMP-337).

pytest 또는 ``python3 tests/test_cmp337_quality_report.py`` 로 실행.
"""
from __future__ import annotations

import json
import io
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── 1. JSON 스키마 검증 ──────────────────────────────────────────────────────
def test_quality_report_json_schema():
    """--quality-report --format json 출력이 올바른 JSON 스키마를 따르는지 검증."""
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    args = SimpleNamespace(
        text="김철수의 전화번호는 010-1234-5678, 이메일은 hong@test.com",
        file=None, output=None, restore=False,
        session="qr-json-sess", json=False, format="json",
        check=False, quality_report=True,
    )
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(io.StringIO()):
        rc = cmd_pseudonymize(args)
    assert rc == 0
    data = json.loads(buf.getvalue())

    # quality_report must be present
    assert "quality_report" in data
    qr = data["quality_report"]

    # Schema: required keys
    for key in ("total_entities", "pseudonymized", "coverage",
                "reversal_accuracy", "by_type", "elapsed_ms"):
        assert key in qr, f"missing key: {key}"

    # Type checks
    assert isinstance(qr["total_entities"], int)
    assert isinstance(qr["pseudonymized"], int)
    assert isinstance(qr["coverage"], (int, float))
    assert isinstance(qr["reversal_accuracy"], (int, float))
    assert isinstance(qr["by_type"], dict)
    assert isinstance(qr["elapsed_ms"], (int, float))

    # by_type entries have count/success
    for etype, stats in qr["by_type"].items():
        assert "count" in stats
        assert "success" in stats


# ── 2. 역변환 정확도 100% 검증 ───────────────────────────────────────────────
def test_reversal_accuracy_100():
    """가명화 → 역변환 정확도가 100%인지 검증."""
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    args = SimpleNamespace(
        text="김민수 010-9999-8888 hong@dudaji.com",
        file=None, output=None, restore=False,
        session="rev-acc-sess", json=False, format="json",
        check=False, quality_report=True,
    )
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(io.StringIO()):
        rc = cmd_pseudonymize(args)
    assert rc == 0
    data = json.loads(buf.getvalue())
    qr = data["quality_report"]
    assert qr["reversal_accuracy"] == 1.0


# ── 3. 엔티티 타입별 통계 검증 ──────────────────────────────────────────────
def test_by_type_statistics():
    """by_type 통계에 올바른 엔티티 타입과 건수가 포함되는지 검증."""
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    args = SimpleNamespace(
        text="전화번호 010-1234-5678 이메일 test@example.com",
        file=None, output=None, restore=False,
        session="bytype-sess", json=False, format="json",
        check=False, quality_report=True,
    )
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(io.StringIO()):
        rc = cmd_pseudonymize(args)
    assert rc == 0
    data = json.loads(buf.getvalue())
    qr = data["quality_report"]

    assert qr["total_entities"] >= 2
    assert qr["pseudonymized"] >= 2

    # KR_PHONE and EMAIL should appear
    types_found = set(qr["by_type"].keys())
    assert "KR_PHONE" in types_found
    assert "EMAIL" in types_found
    assert len(types_found) >= 2

    # Each type has count and success matching
    for etype, stats in qr["by_type"].items():
        assert stats["count"] >= 1
        assert stats["success"] == stats["count"]


# ── 4. PII 없는 입력 → 빈 리포트 ────────────────────────────────────────────
def test_no_pii_empty_report():
    """PII가 없는 입력에 대해 빈 리포트가 반환되는지 검증."""
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    args = SimpleNamespace(
        text="Hello world, this is a clean text with no PII.",
        file=None, output=None, restore=False,
        session="nopii-sess", json=False, format="json",
        check=False, quality_report=True,
    )
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(io.StringIO()):
        rc = cmd_pseudonymize(args)
    assert rc == 0
    data = json.loads(buf.getvalue())
    qr = data["quality_report"]

    assert qr["total_entities"] == 0
    assert qr["pseudonymized"] == 0
    assert qr["coverage"] == 1.0
    assert qr["reversal_accuracy"] == 1.0
    assert qr["by_type"] == {}


# ── 5. SDK API: pseudonymize_with_report ─────────────────────────────────────
def test_sdk_pseudonymize_with_report():
    """SDK pseudonymize_with_report 가 quality_report dict를 포함하는지 검증."""
    from nufi import pseudonymize_with_report

    result = pseudonymize_with_report(
        "김철수 010-1234-5678",
        session_id="sdk-qr-sess",
    )
    assert "quality_report" in result
    assert "transformed_text" in result
    assert "session_id" in result
    assert result["blocked"] is False
    assert result["pseudonymized_count"] >= 1

    qr = result["quality_report"]
    assert qr["total_entities"] >= 1
    assert qr["pseudonymized"] >= 1
    assert qr["coverage"] == 1.0
    assert qr["reversal_accuracy"] == 1.0


# ── 6. text 포맷 출력 (기본) ─────────────────────────────────────────────────
def test_quality_report_text_format():
    """--quality-report 텍스트 포맷이 stderr에 출력되는지 검증."""
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    args = SimpleNamespace(
        text="김철수 010-1234-5678",
        file=None, output=None, restore=False,
        session="text-fmt-sess", json=False, format=None,
        check=False, quality_report=True,
    )
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        rc = cmd_pseudonymize(args)
    assert rc == 0
    err_output = buf_err.getvalue()
    assert "품질 메트릭 리포트" in err_output
    assert "엔티티 커버리지" in err_output
    assert "역변환 정확도" in err_output


# ── 7. --quality-report 없으면 리포트 미포함 ─────────────────────────────────
def test_no_quality_report_flag():
    """--quality-report 없이 실행 시 quality_report가 JSON에 포함되지 않음."""
    from enforcement.pseudonymize_cmd import cmd_pseudonymize

    args = SimpleNamespace(
        text="김철수 010-1234-5678",
        file=None, output=None, restore=False,
        session="noflag-sess", json=False, format="json",
        check=False, quality_report=False,
    )
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(io.StringIO()):
        rc = cmd_pseudonymize(args)
    assert rc == 0
    data = json.loads(buf.getvalue())
    assert "quality_report" not in data


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
    print(f"\n{len(fns)-failed}/{len(fns)} quality report tests PASS")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
