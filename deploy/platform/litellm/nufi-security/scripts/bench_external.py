"""외부 PII 데이터셋 전체 다운로드 + NuFi 탐지 성능 벤치마크 (CMP-308).

ai4privacy/open-pii-masking-500k 전체 데이터를 다운로드하여 NuFi 탐지 파이프라인의
recall/precision 을 측정한다. 데이터는 data/external/ 에 캐시되며 .gitignore 에 의해
git 추적에서 제외된다.

실행:
  python3 scripts/bench_external.py                          # 다운로드 + gazetteer 벤치마크
  python3 scripts/bench_external.py --backend transformers   # KoELECTRA FP32
  python3 scripts/bench_external.py --backend onnx-int8      # ONNX INT8
  python3 scripts/bench_external.py --download-only          # 다운로드만
  python3 scripts/bench_external.py --max-rows 1000          # 표본 제한
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

DATA_DIR = ROOT / "data" / "external"
CACHE_FILE = DATA_DIR / "ai4privacy_full.jsonl"

# NuFi label mapping from external_loader
from goldset.external_loader import AI4PRIVACY_LABEL_MAP, _convert_ai4privacy_row  # noqa: E402


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

PARQUET_DIR = DATA_DIR / "parquet"


def _download_parquet(split: str = "train") -> Path:
    """HuggingFace 에서 parquet 파일을 직접 다운로드한다."""
    import requests

    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PARQUET_DIR / f"{split}.parquet"

    if out_path.exists():
        size_mb = out_path.stat().st_size / 1024 / 1024
        print(f"Parquet 캐시 존재: {out_path} ({size_mb:.1f} MB)")
        return out_path

    # Get parquet URL from HuggingFace API
    api_url = "https://datasets-server.huggingface.co/parquet?dataset=ai4privacy/open-pii-masking-500k-ai4privacy"
    resp = requests.get(api_url, timeout=30)
    resp.raise_for_status()
    parquet_files = resp.json().get("parquet_files", [])

    target = None
    for pf in parquet_files:
        if pf.get("split") == split:
            target = pf
            break

    if not target:
        raise RuntimeError(f"Parquet file for split '{split}' not found")

    download_url = target["url"]
    size_mb = target.get("size", 0) / 1024 / 1024
    print(f"Parquet 다운로드: {split} ({size_mb:.1f} MB)...")

    resp = requests.get(download_url, stream=True, timeout=300)
    resp.raise_for_status()

    downloaded = 0
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192 * 16):
            f.write(chunk)
            downloaded += len(chunk)
            if downloaded % (50 * 1024 * 1024) == 0:
                print(f"  {downloaded / 1024 / 1024:.0f} MB...")

    print(f"  완료: {downloaded / 1024 / 1024:.1f} MB")
    return out_path


def download_full_dataset(max_rows: int | None = None) -> Path:
    """ai4privacy 전체 데이터셋을 다운로드하여 JSONL 로 변환·캐시한다."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if CACHE_FILE.exists():
        with open(CACHE_FILE, encoding="utf-8") as f:
            existing = sum(1 for line in f if line.strip())
        print(f"JSONL 캐시 존재: {CACHE_FILE} ({existing}행)")
        if max_rows and existing >= max_rows:
            return CACHE_FILE
        if not max_rows and existing >= 10000:
            return CACHE_FILE

    # Download parquet
    parquet_path = _download_parquet("train")

    # Convert parquet → JSONL with NuFi label mapping
    import pyarrow.parquet as pq

    print("Parquet → JSONL 변환 중...")
    table = pq.read_table(parquet_path)
    total_rows = len(table)
    total_converted = 0

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        for i in range(total_rows):
            if max_rows and total_converted >= max_rows:
                break

            row = {
                "source_text": str(table.column("source_text")[i].as_py()),
                "privacy_mask": table.column("privacy_mask")[i].as_py(),
                "language": str(table.column("language")[i].as_py()),
            }

            converted = _convert_ai4privacy_row(row)
            if converted:
                f.write(json.dumps(converted, ensure_ascii=False) + "\n")
                total_converted += 1

            if (i + 1) % 50000 == 0:
                print(f"  변환: {i+1}/{total_rows} → {total_converted}행 매핑")

    print(f"변환 완료: {total_rows}행 중 {total_converted}행 NuFi 매핑 가능")
    return CACHE_FILE


def load_dataset(path: Path, max_rows: int | None = None) -> list[dict]:
    """캐시된 JSONL 파일을 로드한다."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))
            if max_rows and len(rows) >= max_rows:
                break
    return rows


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

def run_benchmark(rows: list[dict], backend: str = "gazetteer") -> dict:
    """NuFi DetectionPipeline 으로 외부 데이터 벤치마크를 실행한다.

    Returns: recall/precision per entity type + overall metrics.
    """
    from egress_audit import DetectionPipeline

    print(f"\n벤치마크 시작: backend={backend}, rows={len(rows)}")
    pipeline = DetectionPipeline(ner_backend=backend, enable_ner=True)

    # Per-type counters
    tp = defaultdict(int)  # true positives (expected & detected)
    fn = defaultdict(int)  # false negatives (expected but not detected)
    fp = defaultdict(int)  # false positives (detected but not expected)
    total_expected = defaultdict(int)
    total_detected = defaultdict(int)

    # Span-level metrics
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

        # Entity-class recall/precision
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

        # Span-level matching (partial overlap counts as partial)
        detected_spans = [(f.start, f.end, f.entity_type) for f in findings]
        matched_expected = set()
        matched_detected = set()

        for ei, (es, ee, et) in enumerate(expected_spans):
            for di, (ds, de, dt) in enumerate(detected_spans):
                if et != dt:
                    continue
                # Check overlap
                overlap_start = max(es, ds)
                overlap_end = min(ee, de)
                if overlap_start < overlap_end:  # some overlap
                    if es == ds and ee == de:
                        # Exact match
                        if ei not in matched_expected:
                            span_tp += 1
                            matched_expected.add(ei)
                            matched_detected.add(di)
                    else:
                        # Partial overlap
                        if ei not in matched_expected:
                            span_partial += 1
                            matched_expected.add(ei)
                            matched_detected.add(di)

        span_fn += len(expected_spans) - len(matched_expected)
        span_fp += len(detected_spans) - len(matched_detected)

    elapsed = time.monotonic() - start_time

    # Compute metrics
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

    result = {
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

    return result


def print_report(result: dict):
    """벤치마크 결과를 사람이 읽을 수 있는 형태로 출력한다."""
    print("\n" + "=" * 72)
    print(f"  NuFi 외부 데이터셋 벤치마크 — {result['backend']} backend")
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
    parser = argparse.ArgumentParser(description="외부 PII 데이터셋 벤치마크 (CMP-308)")
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

    # Download
    cache_path = download_full_dataset(max_rows=args.max_rows)

    if args.download_only:
        return 0

    # Load
    rows = load_dataset(cache_path, max_rows=args.max_rows)
    if not rows:
        print("데이터 없음 — 벤치마크 불가")
        return 1

    # Benchmark
    result = run_benchmark(rows, backend=args.backend)
    print_report(result)

    # Save results
    output_path = args.output or str(DATA_DIR / f"bench_result_{args.backend}.json")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n결과 저장: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
