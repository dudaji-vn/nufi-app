"""I5 — 정확도·가명화·인젝션 벤치마크 단일 진입점 (프로그램/CLI/SDK 공용 표면).

CMP-188 P0 I5. 흩어져 있던 벤치마크를 **한 함수·한 명령**으로 묶어 재현한다:

- **정확도(accuracy)** — 봉인 골드셋 측정 산출물(커밋된 JSON 증거)을 게이트 목표선에
  대조한다(무거운 모델 재실행 없이 결정적). 게이트:
    · KR_PERSON Wilson CI 하한 ≥ 0.90 (per-channel INT8; docs/reports/recall-int8.json; CMP-236)
    · 온프렘 p95 표: 단일~중간 동시성(c≤2) p95 ≤ 목표 (docs/reports/load-p95.json)
    · I1 공개 골드셋 baseline(정보성, 게이트 미산입; docs/reports/baseline-int8.json)
  실제 재측정 경로는 scripts/export_onnx_int8.py + scripts/bench_m5.py (모델 스택 필요).
- **가명화(pseudonymize)** — 가역/비가역 품질 하니스를 **라이브로 재실행**한다(결정적,
  모델 불필요). scripts/bench_pseudonymize.run_all() 재사용. 충돌율 0·결정성·원복 정확·
  차단 유지 불변식.
- **인젝션(injection)** — 인젝션 골드셋(samples/injection_gold.jsonl)에 대해
  PromptInjectionDetector 의 recall/precision/F1 을 라이브 측정한다(결정적, 모델 불필요).
  게이트: recall >= 0.90, precision >= 0.90.

원칙: 실고객 데이터 0 · 외부 호출 0 · 결정적. 종료/`overall_pass` 는 게이트 판정.
CLI:  nufi-egress benchmark [--only accuracy|pseudonymize|injection] [--json-out FILE]
SDK:  from enforcement.benchmark import run_benchmarks, evaluate_accuracy_gate,
                                       run_pseudonymize_benchmark, run_injection_benchmark
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent

# 커밋된 측정 산출물(증거 자산) — 데모/게이트 기본 경로.
RECALL_REPORT = ROOT / "docs/reports/recall-int8.json"       # per-channel INT8 recall
P95_REPORT = ROOT / "docs/reports/load-p95.json"             # INT8 부하 p95 sweep
BASELINE_REPORT = ROOT / "docs/reports/baseline-int8.json"   # I1 공개 골드셋 baseline(정보성)
PSEUDO_REPORT = ROOT / "docs/reports/pseudonymize-quality.json"

PERSON_CI_FLOOR = 0.90    # KR_PERSON Wilson CI 하한 목표 (CMP-236: 0.85 → 0.90 상향)
LOW_CONCURRENCY = 2       # 운영 p95 기준: c≤2 에서 목표 이내면 통과(고동시성=워커 스케일아웃)

INJECTION_RECALL_FLOOR = 0.90   # 인젝션 recall 목표
INJECTION_PRECISION_FLOOR = 0.90  # 인젝션 precision 목표
INJECTION_GOLD = ROOT / "samples" / "injection_gold.jsonl"


def _load(path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def evaluate_accuracy_gate(recall_report=RECALL_REPORT, p95_report=P95_REPORT,
                           baseline_report=BASELINE_REPORT,
                           person_ci_floor: float = PERSON_CI_FLOOR) -> Dict[str, Any]:
    """커밋된 정확도 측정 산출물을 게이트 목표선에 대조(새 측정 없음).

    반환: {gates:[...], baseline:{...|None}, pass:bool, missing:[...]}.
    산출물 누락 시 해당 게이트는 pass=False + missing 에 기록(재측정 안내는 데모/문서).
    """
    gates = []
    missing = []

    # --- KR_PERSON Wilson CI 하한 ≥ floor -----------------------------------
    rc = _load(recall_report)
    if rc is None:
        missing.append(str(recall_report))
        gates.append({"id": "kr_person_ci_floor", "pass": False,
                      "detail": f"측정 산출물 없음: {recall_report}",
                      "target": f"KR_PERSON CI 하한 ≥ {person_ci_floor}"})
    else:
        sc = rc["scores"]
        pc = (sc.get("per_class", {}).get("KR_PERSON")
              or sc.get("per_class", {}).get("PERSON") or {})
        ci = pc.get("ci95") or [None, None]
        floor = ci[0]
        ok = floor is not None and floor >= person_ci_floor
        gates.append({
            "id": "kr_person_ci_floor", "pass": bool(ok),
            "target": f"KR_PERSON CI 하한 ≥ {person_ci_floor}",
            "detail": (f"backend={rc.get('ner_backend_active')} "
                       f"recall={pc.get('recall')} ({pc.get('hit')}/{pc.get('exp')}) "
                       f"CI95={ci}  pii_recall={sc.get('pii_recall')} "
                       f"benign_false_block={sc.get('benign_false_block')}"),
            "ci_floor": floor,
        })

    # --- 온프렘 p95: c≤2 에서 목표 이내 -------------------------------------
    p95 = _load(p95_report)
    if p95 is None:
        missing.append(str(p95_report))
        gates.append({"id": "onprem_p95_low_concurrency", "pass": False,
                      "detail": f"측정 산출물 없음: {p95_report}",
                      "target": "c≤2 p95 ≤ 목표"})
    else:
        tgt = p95.get("p95_target_ms", 150.0)
        sweep = p95["concurrency_sweep"]
        low_ok = True
        rows = []
        for k in sorted(sweep, key=lambda x: int(x)):
            s = sweep[k]
            rows.append(f"c={s['concurrency']} p95={s['lat_p95_ms']:.1f}ms")
            if int(k) <= LOW_CONCURRENCY and s["lat_p95_ms"] > tgt:
                low_ok = False
        gates.append({
            "id": "onprem_p95_low_concurrency", "pass": bool(low_ok),
            "target": f"c≤{LOW_CONCURRENCY} p95 ≤ {tgt}ms",
            "detail": (f"backend={p95.get('ner_backend_active')} "
                       f"chars={p95.get('chars')}  " + " · ".join(rows)),
        })

    # --- I1 공개 골드셋 baseline (정보성 — pass 산입 안 함) ------------------
    baseline = None
    bl = _load(baseline_report)
    if bl is not None:
        sc = bl["scores"]
        pc = sc.get("per_class", {})
        baseline = {
            "backend": bl.get("ner_backend_active"),
            "acceptance_pass": bl.get("acceptance_pass"),
            "pii_recall": sc.get("pii_recall"),
            "pii_recall_ci95": sc.get("pii_recall_ci95"),
            "pii_precision": sc.get("pii_precision"),
            "benign_false_block": sc.get("benign_false_block"),
            "strong_recall": sc.get("strong_recall"),
            "per_class": {name: {"recall": v.get("recall"), "ci95": v.get("ci95"),
                                 "hit": v.get("hit"), "exp": v.get("exp")}
                          for name, v in pc.items()},
        }

    return {
        "benchmark": "accuracy-gate",
        "gates": gates,
        "baseline_informational": baseline,
        "missing": missing,
        "pass": all(g["pass"] for g in gates),
    }


def run_pseudonymize_benchmark() -> Dict[str, Any]:
    """가명화 품질 하니스를 라이브 재실행(결정적, 모델 불필요).

    scripts/bench_pseudonymize.run_all() 을 재사용. 반환 dict 에 acceptance_pass 포함.
    """
    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import bench_pseudonymize  # noqa: E402  (scripts/ 하니스 재사용)
    return bench_pseudonymize.run_all()


def run_injection_benchmark(gold_path=INJECTION_GOLD,
                            recall_floor: float = INJECTION_RECALL_FLOOR,
                            precision_floor: float = INJECTION_PRECISION_FLOOR) -> Dict[str, Any]:
    """인젝션 골드셋에 대해 recall/precision/F1 을 라이브 측정(결정적, 모델 불필요).

    scripts/bench_injection.py 의 run_benchmark() 를 재사용.
    반환: {tp, fn, fp, tn, recall, precision, f1, pass, gates:[...]}.
    """
    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import bench_injection  # noqa: E402

    metrics = bench_injection.run_benchmark()

    recall_ok = metrics["recall"] >= recall_floor
    precision_ok = metrics["precision"] >= precision_floor
    passed = recall_ok and precision_ok

    gates = [
        {"id": "injection_recall", "pass": bool(recall_ok),
         "target": f"recall >= {recall_floor}",
         "detail": f"recall={metrics['recall']:.4f} (TP={metrics['tp']} FN={metrics['fn']})"},
        {"id": "injection_precision", "pass": bool(precision_ok),
         "target": f"precision >= {precision_floor}",
         "detail": f"precision={metrics['precision']:.4f} (TP={metrics['tp']} FP={metrics['fp']})"},
    ]

    return {
        "benchmark": "injection",
        "tp": metrics["tp"],
        "fn": metrics["fn"],
        "fp": metrics["fp"],
        "tn": metrics["tn"],
        "recall": metrics["recall"],
        "precision": metrics["precision"],
        "f1": metrics["f1"],
        "gates": gates,
        "pass": passed,
    }


def run_benchmarks(only: Optional[str] = None, *,
                   recall_report=RECALL_REPORT, p95_report=P95_REPORT,
                   baseline_report=BASELINE_REPORT,
                   person_ci_floor: float = PERSON_CI_FLOOR) -> Dict[str, Any]:
    """정확도 게이트 + 가명화 하니스를 한 번에 재현.

    only: None=둘 다, "accuracy"=정확도만, "pseudonymize"=가명화만.
    반환: {accuracy:{...|None}, pseudonymize:{...|None}, overall_pass:bool}.
    """
    if only not in (None, "accuracy", "pseudonymize", "injection"):
        raise ValueError(f"only 는 accuracy|pseudonymize|injection 중 하나여야 합니다: {only!r}")

    accuracy = None
    pseudonymize = None
    injection = None
    if only in (None, "accuracy"):
        accuracy = evaluate_accuracy_gate(recall_report, p95_report,
                                          baseline_report, person_ci_floor)
    if only in (None, "pseudonymize"):
        pseudonymize = run_pseudonymize_benchmark()
    if only in (None, "injection"):
        injection = run_injection_benchmark()

    passes = []
    if accuracy is not None:
        passes.append(accuracy["pass"])
    if pseudonymize is not None:
        passes.append(bool(pseudonymize.get("acceptance_pass")))
    if injection is not None:
        passes.append(bool(injection.get("pass")))

    return {
        "benchmark": "nufi-benchmark",
        "only": only,
        "accuracy": accuracy,
        "pseudonymize": pseudonymize,
        "injection": injection,
        "overall_pass": all(passes) if passes else False,
    }


def render(report: Dict[str, Any]) -> str:
    """사람 친화 요약(텍스트) — CLI/데모 출력용."""
    lines = []
    lines.append("=" * 60)
    lines.append(" NuFi 벤치마크 — 정확도 게이트 + 가명화 품질 (단일 진입점)")
    lines.append(" 외부호출 0 · 결정적 · 실고객데이터 0")
    lines.append("=" * 60)

    acc = report.get("accuracy")
    if acc is not None:
        lines.append("")
        lines.append("[정확도] 커밋된 측정 산출물 → 게이트 대조(새 측정 없음)")
        for g in acc["gates"]:
            mark = "PASS" if g["pass"] else "FAIL"
            lines.append(f"  [{mark}] {g['id']}  ({g['target']})")
            lines.append(f"         {g['detail']}")
        bl = acc.get("baseline_informational")
        if bl is not None:
            lines.append(f"  (i) I1 공개 골드셋 baseline: backend={bl['backend']} "
                         f"pii_recall={bl['pii_recall']} precision={bl['pii_precision']} "
                         f"benign_false_block={bl['benign_false_block']} — 정보성(게이트 미산입)")
        if acc.get("missing"):
            lines.append(f"  ! 누락 산출물: {', '.join(acc['missing'])} "
                         f"(재측정: scripts/export_onnx_int8.py + scripts/bench_m5.py)")

    ps = report.get("pseudonymize")
    if ps is not None:
        lines.append("")
        lines.append("[가명화] 품질 하니스 라이브 재실행(가역/비가역 불변식)")
        acc_map = ps.get("acceptance", {})
        ap = bool(ps.get("acceptance_pass"))
        lines.append(f"  [{'PASS' if ap else 'FAIL'}] pseudonymize-quality  "
                     f"({sum(acc_map.values())}/{len(acc_map)} 불변식 충족)")
        for name, val in acc_map.items():
            if not val:
                lines.append(f"         [미달] {name}")

    inj = report.get("injection")
    if inj is not None:
        lines.append("")
        lines.append("[인젝션] 골드셋 recall/precision/F1 라이브 측정(결정적)")
        for g in inj["gates"]:
            mark = "PASS" if g["pass"] else "FAIL"
            lines.append(f"  [{mark}] {g['id']}  ({g['target']})")
            lines.append(f"         {g['detail']}")
        lines.append(f"  F1={inj['f1']:.4f}  (TP={inj['tp']} FN={inj['fn']} "
                     f"FP={inj['fp']} TN={inj['tn']})")

    lines.append("-" * 60)
    lines.append("PASS" if report["overall_pass"]
                 else "FAIL")
    return "\n".join(lines)
