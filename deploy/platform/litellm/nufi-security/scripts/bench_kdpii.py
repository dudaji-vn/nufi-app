"""KDPII 53k 한국어 PII 데이터셋 벤치마크 (CMP-310).

korean-guardrail-dataset KDPII(53,778건 한국어 대화 기반 PII)를 NuFi 탐지
파이프라인으로 평가한다. KDPII 라벨 → NuFi 라벨 매핑 후 recall/precision 측정.

실행:
  python3 scripts/bench_kdpii.py                          # gazetteer 벤치마크
  python3 scripts/bench_kdpii.py --backend onnx-int8      # ONNX INT8
  python3 scripts/bench_kdpii.py --backend transformers   # KoELECTRA FP32
  python3 scripts/bench_kdpii.py --download-only          # 다운로드만
  python3 scripts/bench_kdpii.py --max-rows 1000          # 표본 제한
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from goldset.external_loader import download_kdpii  # noqa: E402


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

def run_benchmark(rows: list[dict], backend: str = "gazetteer") -> dict:
    """NuFi DetectionPipeline 으로 KDPII 벤치마크를 실행한다."""
    from egress_audit import DetectionPipeline

    print(f"\nKDPII 벤치마크 시작: backend={backend}, rows={len(rows)}")
    pipeline = DetectionPipeline(ner_backend=backend, enable_ner=True)

    tp = defaultdict(int)
    fn = defaultdict(int)
    fp = defaultdict(int)
    total_expected = defaultdict(int)
    total_detected = defaultdict(int)

    span_tp = 0
    span_fp = 0
    span_fn = 0
    span_partial = 0

    start_time = time.monotonic()
    errors = 0

    for i, row in enumerate(rows):
        if (i + 1) % 500 == 0:
            elapsed = time.monotonic() - start_time
            rate = (i + 1) / elapsed
            print(f"  진행: {i+1}/{len(rows)} ({rate:.1f} rows/s)")

        text = row["prompt"]
        expected_types = set(row.get("expect", []))
        expected_spans = row.get("spans", [])

        try:
            findings = pipeline.analyze(text)
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  오류 ({i}): {e}")
            continue

        detected_types = {f.entity_type for f in findings}

        for etype in expected_types:
            total_expected[etype] += 1
            if etype in detected_types:
                tp[etype] += 1
            else:
                fn[etype] += 1

        for etype in detected_types:
            total_detected[etype] += 1
            if etype not in expected_types:
                fp[etype] += 1

        # Span-level matching
        detected_spans = [(f.start, f.end, f.entity_type) for f in findings]
        matched_expected = set()
        matched_detected = set()

        for ei, (es, ee, et) in enumerate(expected_spans):
            for di, (ds, de, dt) in enumerate(detected_spans):
                if et != dt:
                    continue
                overlap_start = max(es, ds)
                overlap_end = min(ee, de)
                if overlap_start < overlap_end:
                    if es == ds and ee == de:
                        if ei not in matched_expected:
                            span_tp += 1
                            matched_expected.add(ei)
                            matched_detected.add(di)
                    else:
                        if ei not in matched_expected:
                            span_partial += 1
                            matched_expected.add(ei)
                            matched_detected.add(di)

        span_fn += len(expected_spans) - len(matched_expected)
        span_fp += len(detected_spans) - len(matched_detected)

    elapsed = time.monotonic() - start_time

    all_types = sorted(set(list(total_expected.keys()) + list(total_detected.keys())))
    per_type = {}
    for etype in all_types:
        exp = total_expected.get(etype, 0)
        det = total_detected.get(etype, 0)
        t = tp.get(etype, 0)
        recall = t / exp if exp > 0 else 0.0
        precision = t / det if det > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        per_type[etype] = {
            "expected": exp, "detected": det, "tp": t,
            "fn": fn.get(etype, 0), "fp": fp.get(etype, 0),
            "recall": round(recall, 4), "precision": round(precision, 4),
            "f1": round(f1, 4),
        }

    total_tp = sum(tp.values())
    total_fn_sum = sum(fn.values())
    total_fp_sum = sum(fp.values())
    overall_recall = total_tp / (total_tp + total_fn_sum) if (total_tp + total_fn_sum) > 0 else 0
    total_det_sum = total_tp + total_fp_sum
    overall_precision = total_tp / total_det_sum if total_det_sum > 0 else 0

    span_recall = span_tp / (span_tp + span_fn) if (span_tp + span_fn) > 0 else 0
    span_precision = span_tp / (span_tp + span_fp) if (span_tp + span_fp) > 0 else 0

    return {
        "dataset": "KDPII",
        "dataset_url": "https://github.com/skan0779/korean-guardrail-dataset",
        "backend": backend,
        "total_rows": len(rows),
        "elapsed_seconds": round(elapsed, 2),
        "rows_per_second": round(len(rows) / elapsed, 2),
        "errors": errors,
        "overall": {
            "recall": round(overall_recall, 4),
            "precision": round(overall_precision, 4),
            "f1": round(2 * overall_recall * overall_precision / (overall_recall + overall_precision), 4) if (overall_recall + overall_precision) > 0 else 0,
            "tp": total_tp,
            "fn": total_fn_sum,
            "fp": total_fp_sum,
        },
        "span_level": {
            "exact_tp": span_tp,
            "partial": span_partial,
            "fn": span_fn,
            "fp": span_fp,
            "exact_recall": round(span_recall, 4),
            "exact_precision": round(span_precision, 4),
        },
        "per_type": per_type,
    }


def print_report(result: dict):
    """벤치마크 결과를 사람이 읽을 수 있는 형태로 출력한다."""
    print("\n" + "=" * 72)
    print(f"  KDPII 한국어 PII 벤치마크 — {result['backend']} backend")
    print("=" * 72)
    print(f"  데이터: {result['total_rows']}행 | "
          f"소요: {result['elapsed_seconds']}s | "
          f"속도: {result['rows_per_second']} rows/s")
    if result['errors']:
        print(f"  오류: {result['errors']}건")

    o = result["overall"]
    print(f"\n  전체 Entity-Class Recall:    {o['recall']:.4f}")
    print(f"  전체 Entity-Class Precision: {o['precision']:.4f}")
    print(f"  전체 Entity-Class F1:        {o['f1']:.4f}")
    print(f"  (TP={o['tp']}, FN={o['fn']}, FP={o['fp']})")

    s = result["span_level"]
    print(f"\n  Span Exact Recall:    {s['exact_recall']:.4f}")
    print(f"  Span Exact Precision: {s['exact_precision']:.4f}")
    print(f"  (Exact TP={s['exact_tp']}, Partial={s['partial']}, "
          f"FN={s['fn']}, FP={s['fp']})")

    print(f"\n  {'Type':<22} {'Expected':>8} {'Detected':>8} {'TP':>5} "
          f"{'Recall':>8} {'Prec':>8} {'F1':>8}")
    print("  " + "-" * 70)
    for etype, m in sorted(result["per_type"].items()):
        print(f"  {etype:<22} {m['expected']:>8} {m['detected']:>8} {m['tp']:>5} "
              f"{m['recall']:>8.4f} {m['precision']:>8.4f} {m['f1']:>8.4f}")
    print("=" * 72)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="KDPII 한국어 PII 벤치마크 (CMP-310)")
    parser.add_argument("--backend", default="gazetteer",
                        choices=["gazetteer", "transformers", "onnx-int8", "auto"],
                        help="NER 백엔드 (default: gazetteer)")
    parser.add_argument("--max-rows", type=int, default=None,
                        help="평가할 최대 행 수 (default: 전체)")
    parser.add_argument("--download-only", action="store_true",
                        help="다운로드만 수행")
    parser.add_argument("--output", type=str, default=None,
                        help="결과 JSON 저장 경로")
    args = parser.parse_args()

    # Download + convert
    rows = download_kdpii()
    print(f"KDPII NuFi 매핑 행: {len(rows)}건")

    if args.download_only:
        return 0

    # Apply max-rows limit
    if args.max_rows and len(rows) > args.max_rows:
        rows = rows[:args.max_rows]

    if not rows:
        print("데이터 없음 — 벤치마크 불가")
        return 1

    # Benchmark
    result = run_benchmark(rows, backend=args.backend)
    print_report(result)

    # Save results
    report_dir = ROOT / "docs" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output or str(report_dir / f"bench_kdpii_{args.backend}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n결과 저장: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
