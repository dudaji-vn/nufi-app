"""CMP-308: ai4privacy 전체 데이터셋 NuFi 탐지 성능 벤치마크.

ai4privacy/open-pii-masking-500k 전체 ~580k 행을 NuFi 탐지 파이프라인으로 평가하여
클래스별 recall/precision, span P/R/F1, Wilson CI, 언어별 성능을 측정한다.

실행:
  python3 scripts/bench_ai4privacy.py --backend gazetteer
  python3 scripts/bench_ai4privacy.py --backend transformers
  python3 scripts/bench_ai4privacy.py --backend gazetteer --json-out results.json
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import EgressGuard  # noqa: E402
from goldset.external_loader import (  # noqa: E402
    download_ai4privacy_full,
    AI4PRIVACY_LABEL_MAP,
)

# NuFi PII 유니버스 (ai4privacy 매핑 대상)
PII_UNIVERSE = {"KR_RRN", "KR_FOREIGNER_REG", "KR_BRN", "KR_PASSPORT", "KR_DRIVER_LICENSE",
                "CREDIT_CARD", "KR_ACCOUNT", "KR_PHONE", "EMAIL", "KR_PERSON",
                "KR_LOCATION", "SECRET"}

# ai4privacy 에서 NuFi 로 매핑되는 클래스
MAPPED_CLASSES = {v for v in AI4PRIVACY_LABEL_MAP.values() if v is not None}


def wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = hits / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4))


def span_overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def build_guard(backend: str):
    if backend == "transformers":
        try:
            import transformers  # noqa: F401
            return EgressGuard(ner_backend="transformers"), None
        except Exception as e:
            return None, f"transformers 백엔드 로드 실패: {e}"
    elif backend == "onnx-int8":
        try:
            import onnxruntime  # noqa: F401
            return EgressGuard(ner_backend="onnx-int8"), None
        except Exception as e:
            return None, f"onnx-int8 백엔드 로드 실패: {e}"
    return EgressGuard(ner_backend="gazetteer"), None


def benchmark(rows: list[dict], guard: EgressGuard, progress_interval: int = 5000):
    """전체 데이터셋 벤치마크 수행."""
    # 클래스별 카운터
    cls_exp: dict[str, int] = defaultdict(int)
    cls_hit: dict[str, int] = defaultdict(int)
    # 언어별 카운터
    lang_exp: dict[str, int] = defaultdict(int)
    lang_hit: dict[str, int] = defaultdict(int)
    # 언어×클래스 카운터
    lang_cls_exp: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    lang_cls_hit: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    # span 단위
    span_gold = span_pred = span_exact = span_partial = 0
    # precision
    emit_total = emit_correct = 0
    # 지연
    latencies: list[float] = []

    total = len(rows)
    t_total_start = time.perf_counter()

    for i, row in enumerate(rows):
        t0 = time.perf_counter()
        res = guard.inspect(row["prompt"])
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

        got_types = {f.entity_type for f in res.findings if f.entity_type in PII_UNIVERSE}
        got_spans = [(f.start, f.end, f.entity_type) for f in res.findings
                     if f.entity_type in PII_UNIVERSE and f.end > f.start]

        expect = row.get("expect", [])
        lang = row.get("language", "unknown")

        # 클래스 recall
        for e in expect:
            cls_exp[e] += 1
            lang_exp[lang] += 1
            lang_cls_exp[lang][e] += 1
            if e in got_types:
                cls_hit[e] += 1
                lang_hit[lang] += 1
                lang_cls_hit[lang][e] += 1

        # precision
        for s in got_spans:
            emit_total += 1
            if s[2] in expect:
                emit_correct += 1

        # span 단위
        gold_spans = [tuple(g) for g in row.get("spans", [])]
        span_gold += len(gold_spans)
        span_pred += len(got_spans)
        for g in gold_spans:
            for p in got_spans:
                if p[2] == g[2] and span_overlap(p, g):
                    if p[0] == g[0] and p[1] == g[1]:
                        span_exact += 1
                    else:
                        span_partial += 1
                    break

        if (i + 1) % progress_interval == 0:
            elapsed = time.perf_counter() - t_total_start
            rate = (i + 1) / elapsed
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1}/{total}] {rate:.0f} rows/s, ETA {eta:.0f}s", flush=True)

    wall_time = time.perf_counter() - t_total_start

    # --- 클래스별 집계 ---
    per_class = {}
    for c in sorted(cls_exp):
        exp, hit = cls_exp[c], cls_hit[c]
        per_class[c] = {
            "recall": round(hit / exp, 4) if exp else 0.0,
            "hit": hit, "exp": exp,
            "ci95": wilson_ci(hit, exp),
        }

    # --- 언어별 집계 ---
    per_lang = {}
    for lang in sorted(lang_exp):
        exp, hit = lang_exp[lang], lang_hit[lang]
        per_lang[lang] = {
            "recall": round(hit / exp, 4) if exp else 0.0,
            "hit": hit, "exp": exp,
            "ci95": wilson_ci(hit, exp),
        }

    # --- 언어×클래스 집계 (주요 언어만) ---
    lang_class_detail = {}
    for lang in sorted(lang_cls_exp):
        if lang_exp[lang] < 50:
            continue
        lang_class_detail[lang] = {}
        for c in sorted(lang_cls_exp[lang]):
            exp = lang_cls_exp[lang][c]
            hit = lang_cls_hit[lang].get(c, 0)
            lang_class_detail[lang][c] = {
                "recall": round(hit / exp, 4) if exp else 0.0,
                "hit": hit, "exp": exp,
            }

    # --- 전체 집계 ---
    total_exp = sum(cls_exp.values())
    total_hit = sum(cls_hit.values())
    precision = round(emit_correct / emit_total, 4) if emit_total else 1.0
    span_recall = round((span_exact + span_partial) / span_gold, 4) if span_gold else 0.0
    span_prec = round((span_exact + span_partial) / span_pred, 4) if span_pred else 0.0

    latencies.sort()
    n_lat = len(latencies)

    return {
        "dataset": "ai4privacy/open-pii-masking-500k",
        "total_rows": total,
        "total_annotations": total_exp,
        "overall_recall": round(total_hit / total_exp, 4) if total_exp else 0.0,
        "overall_recall_ci95": wilson_ci(total_hit, total_exp),
        "overall_precision": precision,
        "span_exact_recall": round(span_exact / span_gold, 4) if span_gold else 0.0,
        "span_recall_incl_partial": span_recall,
        "span_precision": span_prec,
        "span_gold_total": span_gold,
        "span_pred_total": span_pred,
        "per_class": per_class,
        "per_language": per_lang,
        "language_class_detail": lang_class_detail,
        "latency": {
            "p50_ms": round(statistics.median(latencies), 2),
            "p95_ms": round(latencies[int(n_lat * 0.95)], 2) if n_lat else 0,
            "p99_ms": round(latencies[int(n_lat * 0.99)], 2) if n_lat else 0,
            "mean_ms": round(statistics.mean(latencies), 2),
            "rows_per_sec": round(total / wall_time, 1),
        },
        "wall_time_sec": round(wall_time, 1),
    }


def main():
    ap = argparse.ArgumentParser(description="CMP-308: ai4privacy 전체 벤치마크")
    ap.add_argument("--backend", default="gazetteer",
                    choices=["gazetteer", "transformers", "onnx-int8"])
    ap.add_argument("--max-rows", type=int, default=0,
                    help="0=전체, N>0이면 처음 N행만 평가 (디버그용)")
    ap.add_argument("--json-out", help="결과 JSON 파일 경로")
    args = ap.parse_args()

    print(f"[CMP-308] ai4privacy 전체 벤치마크 — backend={args.backend}")

    # 1) 데이터셋 다운로드/로드
    print("데이터셋 로드 중...", flush=True)
    rows = download_ai4privacy_full()
    print(f"  변환된 행: {len(rows):,} (NuFi 매핑 가능한 PII ≥ 1)")

    if args.max_rows > 0:
        rows = rows[:args.max_rows]
        print(f"  --max-rows={args.max_rows} 적용, 평가 행: {len(rows):,}")

    # 2) 가드 빌드
    guard, reason = build_guard(args.backend)
    if guard is None:
        print(f"[ERROR] {reason}")
        return 1

    # 3) 벤치마크 실행
    print(f"벤치마크 실행 중 ({len(rows):,} rows)...", flush=True)
    report = benchmark(rows, guard)
    report["backend"] = args.backend

    # 4) 결과 출력
    out = json.dumps(report, ensure_ascii=False, indent=2)
    print("\n" + "=" * 60)
    print(out)

    if args.json_out:
        Path(args.json_out).write_text(out, encoding="utf-8")
        print(f"\n결과 저장: {args.json_out}")

    # 5) 요약
    print("\n" + "=" * 60)
    print(f"[요약] backend={args.backend}")
    print(f"  전체 recall: {report['overall_recall']:.4f} "
          f"CI95={report['overall_recall_ci95']}")
    print(f"  전체 precision: {report['overall_precision']:.4f}")
    print(f"  span exact recall: {report['span_exact_recall']:.4f}")
    print(f"  처리 속도: {report['latency']['rows_per_sec']:.0f} rows/s "
          f"(p95={report['latency']['p95_ms']:.1f}ms)")
    print(f"  소요 시간: {report['wall_time_sec']:.0f}s")
    print("\n클래스별 recall:")
    for c, v in sorted(report["per_class"].items()):
        print(f"  {c:25s} {v['recall']:.4f} ({v['hit']}/{v['exp']}) "
              f"CI95={v['ci95']}")
    print("\n언어별 recall:")
    for lang, v in sorted(report["per_language"].items()):
        print(f"  {lang:10s} {v['recall']:.4f} ({v['hit']}/{v['exp']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
