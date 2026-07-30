"""I5 정확도·가명화 벤치마크 단일 진입점 (CMP-201).

완료기준 검증:
- 단일 함수(`run_benchmarks`)로 정확도 게이트 + 가명화 하니스를 함께 재현한다.
- 단일 CLI 명령(`nufi-egress benchmark`)이 전체 PASS 시 exit 0, 미달 시 1 을 낸다.
- `--only` 로 각 축을 독립 실행하고, 정확도 게이트가 커밋 산출물을 목표선에 대조한다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from enforcement import benchmark as B  # noqa: E402
from enforcement.cli import main as cli_main  # noqa: E402


def test_run_benchmarks_full_pass():
    rep = B.run_benchmarks()
    assert rep["accuracy"] is not None
    assert rep["pseudonymize"] is not None
    assert rep["overall_pass"] is True
    # 가명화 하니스 라이브 재실행 결과가 수용 판정 통과.
    assert rep["pseudonymize"]["acceptance_pass"] is True


def test_accuracy_gate_targets_and_baseline():
    acc = B.evaluate_accuracy_gate()
    assert acc["pass"] is True
    ids = {g["id"] for g in acc["gates"]}
    assert ids == {"kr_person_ci_floor", "onprem_p95_low_concurrency"}
    # KR_PERSON CI 하한 게이트는 목표(0.85) 이상.
    ci_gate = next(g for g in acc["gates"] if g["id"] == "kr_person_ci_floor")
    assert ci_gate["ci_floor"] >= B.PERSON_CI_FLOOR
    # I1 공개 골드셋 baseline 은 정보성으로 존재하되 pass 산입 안 함.
    assert acc["baseline_informational"] is not None


def test_only_selectors():
    a = B.run_benchmarks(only="accuracy")
    assert a["accuracy"] is not None and a["pseudonymize"] is None
    p = B.run_benchmarks(only="pseudonymize")
    assert p["pseudonymize"] is not None and p["accuracy"] is None


def test_missing_report_fails_gate(tmp_path):
    missing = tmp_path / "nope.json"
    acc = B.evaluate_accuracy_gate(recall_report=missing, p95_report=missing,
                                   baseline_report=missing)
    assert acc["pass"] is False
    assert str(missing) in acc["missing"]
    # baseline 누락은 조용히 None(정보성 — 게이트 실패로 취급 안 함).
    assert acc["baseline_informational"] is None


def test_cli_benchmark_exit0():
    assert cli_main(["benchmark"]) == 0
    assert cli_main(["benchmark", "--only", "accuracy"]) == 0
    assert cli_main(["benchmark", "--only", "pseudonymize"]) == 0


def test_cli_benchmark_json_out(tmp_path, capsys):
    out = tmp_path / "bench.json"
    rc = cli_main(["benchmark", "--json", "--json-out", str(out)])
    assert rc == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["overall_pass"] is True
    assert doc["benchmark"] == "nufi-benchmark"
