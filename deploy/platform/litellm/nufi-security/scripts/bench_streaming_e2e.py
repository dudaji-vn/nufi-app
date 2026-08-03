"""스트리밍 E2E 가명화 벤치마크 — StreamingDeanonymizer 품질 검증 (CMP-366).

기존 170 샘플의 LLM 응답을 다양한 청크 크기(1, 3, 5, 10, random)로 분할,
StreamingDeanonymizer.feed(chunk) → flush()로 원복한 결과가
비스트리밍 deanonymize() 결과와 정확히 일치하는지 검증.

실행:
  python3 scripts/bench_streaming_e2e.py
  python3 scripts/bench_streaming_e2e.py --json-out docs/reports/streaming-e2e-quality.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import MappingVault, ReversibleEgress  # noqa: E402
from scripts.bench_pseudonymize_e2e import (  # noqa: E402
    EVAL_SET,
    MockLLM,
    load_eval_set,
)

SEED = 20260709
CHUNK_SIZES = [1, 3, 5, 10]  # fixed + random

# ── 목표 ──────────────────────────────────────────────────────────────────
TARGETS = {
    "streaming_match_rate": 1.0,  # 스트리밍 원복 == 비스트리밍 원복 비율
}


# ── 청크 분할 유틸 ─────────────────────────────────────────────────────────
def split_fixed(text: str, size: int) -> List[str]:
    """고정 크기로 텍스트 분할."""
    return [text[i:i + size] for i in range(0, len(text), size)]


def split_random(text: str, rng: random.Random, min_size: int = 1,
                 max_size: int = 15) -> List[str]:
    """랜덤 크기로 텍스트 분할."""
    chunks = []
    i = 0
    while i < len(text):
        size = rng.randint(min_size, max_size)
        chunks.append(text[i:i + size])
        i += size
    return chunks


# ── 벤치마크 파이프라인 ───────────────────────────────────────────────────
@dataclass
class StreamingSampleResult:
    id: str
    category: str
    pseudo_response: str
    nonstream_restored: str
    # 청크별 결과
    chunk_results: Dict[str, dict] = field(default_factory=dict)
    # 전체 매치 여부
    all_match: bool = True


@dataclass
class ChunkResult:
    chunk_size: str
    stream_restored: str
    match: bool
    n_chunks: int
    latency_ms: float


def run_streaming_benchmark(eval_path: Path = EVAL_SET) -> dict:
    """스트리밍 E2E 벤치마크 실행."""
    samples = load_eval_set(eval_path)
    if not samples:
        raise ValueError(f"평가셋 비어 있음: {eval_path}")

    llm = MockLLM(samples)
    rng = random.Random(SEED)

    results: List[StreamingSampleResult] = []
    # 청크 크기별 집계
    per_chunk_stats: Dict[str, dict] = {
        str(s): {"match": 0, "total": 0, "latencies": []}
        for s in CHUNK_SIZES
    }
    per_chunk_stats["random"] = {"match": 0, "total": 0, "latencies": []}

    rev = ReversibleEgress()

    for idx, sample in enumerate(samples):
        sid = f"stream-e2e-{idx}"

        # 가명화
        pseudo_result = rev.pseudonymize(sample.question, sid)
        pseudo_q = pseudo_result.transformed_text

        # MockLLM 응답 (surrogate 포함)
        pseudo_response = llm.generate(pseudo_q)

        # 비스트리밍 원복 (기준)
        nonstream_restored, _ = rev.deanonymize(pseudo_response, sid)

        sr = StreamingSampleResult(
            id=sample.id,
            category=sample.category,
            pseudo_response=pseudo_response,
            nonstream_restored=nonstream_restored,
        )

        # 각 청크 크기로 스트리밍 원복 → 비스트리밍과 비교
        for size in CHUNK_SIZES:
            chunks = split_fixed(pseudo_response, size)
            restorer = rev.stream_restorer(sid)

            t0 = time.perf_counter()
            stream_out = "".join(restorer.feed(c) for c in chunks)
            stream_out += restorer.flush()
            latency = (time.perf_counter() - t0) * 1000

            match = stream_out == nonstream_restored
            sr.chunk_results[str(size)] = {
                "match": match,
                "n_chunks": len(chunks),
                "latency_ms": round(latency, 3),
            }
            if not match:
                sr.all_match = False
                sr.chunk_results[str(size)]["stream_restored"] = stream_out
                sr.chunk_results[str(size)]["nonstream_restored"] = nonstream_restored

            per_chunk_stats[str(size)]["total"] += 1
            per_chunk_stats[str(size)]["match"] += 1 if match else 0
            per_chunk_stats[str(size)]["latencies"].append(latency)

        # 랜덤 청크
        chunks = split_random(pseudo_response, rng)
        restorer = rev.stream_restorer(sid)

        t0 = time.perf_counter()
        stream_out = "".join(restorer.feed(c) for c in chunks)
        stream_out += restorer.flush()
        latency = (time.perf_counter() - t0) * 1000

        match = stream_out == nonstream_restored
        sr.chunk_results["random"] = {
            "match": match,
            "n_chunks": len(chunks),
            "latency_ms": round(latency, 3),
        }
        if not match:
            sr.all_match = False
            sr.chunk_results["random"]["stream_restored"] = stream_out
            sr.chunk_results["random"]["nonstream_restored"] = nonstream_restored

        per_chunk_stats["random"]["total"] += 1
        per_chunk_stats["random"]["match"] += 1 if match else 0
        per_chunk_stats["random"]["latencies"].append(latency)

        results.append(sr)
        rev.end_session(sid)

    return _aggregate(results, per_chunk_stats)


def _aggregate(results: List[StreamingSampleResult],
               per_chunk_stats: Dict[str, dict]) -> dict:
    """결과 집계."""
    n = len(results)
    if n == 0:
        return {"error": "no samples"}

    # 전체 매치율
    all_match_count = sum(1 for r in results if r.all_match)
    streaming_match_rate = round(all_match_count / n, 4)

    # 청크 크기별 매치율 + 레이턴시
    def _percentile(arr, p):
        if not arr:
            return 0.0
        arr_sorted = sorted(arr)
        idx = min(int(len(arr_sorted) * p), len(arr_sorted) - 1)
        return round(arr_sorted[idx], 3)

    chunk_breakdown = {}
    for label, stats in per_chunk_stats.items():
        total = stats["total"]
        match = stats["match"]
        lats = stats["latencies"]
        chunk_breakdown[label] = {
            "match_rate": round(match / total, 4) if total else 0.0,
            "match_n": f"{match}/{total}",
            "latency_ms": {
                "p50": _percentile(lats, 0.5),
                "p95": _percentile(lats, 0.95),
                "p99": _percentile(lats, 0.99),
            },
        }

    # 카테고리별 매치율
    by_category: Dict[str, dict] = {}
    for r in results:
        d = by_category.setdefault(r.category, {"match": 0, "n": 0})
        d["n"] += 1
        if r.all_match:
            d["match"] += 1
    for cat, d in by_category.items():
        d["match_rate"] = round(d["match"] / d["n"], 4)

    # 불일치 샘플
    mismatches = []
    for r in results:
        if not r.all_match:
            failed_chunks = {k: v for k, v in r.chunk_results.items()
                            if not v["match"]}
            mismatches.append({
                "id": r.id,
                "category": r.category,
                "failed_chunks": failed_chunks,
            })

    # 게이트 판정
    acceptance = {
        f"streaming_match_rate=={TARGETS['streaming_match_rate']}":
            streaming_match_rate >= TARGETS["streaming_match_rate"],
    }

    report = {
        "benchmark": "streaming-e2e-quality",
        "eval_set": str(EVAL_SET.relative_to(ROOT)),
        "n_samples": n,
        "chunk_sizes": CHUNK_SIZES + ["random"],
        "seed": SEED,
        "targets": TARGETS,
        "scores": {
            "streaming_match_rate": streaming_match_rate,
            "streaming_match_n": f"{all_match_count}/{n}",
        },
        "by_chunk_size": chunk_breakdown,
        "by_category": dict(sorted(by_category.items())),
        "mismatches": mismatches[:20],  # 최대 20건
        "n_mismatches": len(mismatches),
        "acceptance": acceptance,
        "acceptance_pass": all(acceptance.values()),
    }
    return report


# ── CLI ───────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="스트리밍 E2E 가명화 벤치마크 (CMP-366)")
    ap.add_argument("--eval-set", default=str(EVAL_SET),
                    help="평가셋 경로")
    ap.add_argument("--json-out", default=None,
                    help="JSON 리포트 출력 경로")
    args = ap.parse_args()

    report = run_streaming_benchmark(eval_path=Path(args.eval_set))

    # 콘솔 요약
    scores = report["scores"]
    print("=" * 65)
    print("스트리밍 E2E 가명화 벤치마크 결과 (CMP-366)")
    print("=" * 65)
    print(f"  샘플 수: {report['n_samples']}")
    print(f"  청크 크기: {report['chunk_sizes']}")
    print()
    print(f"  [전체 매치율]")
    match_pass = "PASS" if report["acceptance_pass"] else "FAIL"
    print(f"    Streaming Match Rate: {scores['streaming_match_rate']:.4f}"
          f"  ({scores['streaming_match_n']})  목표=={TARGETS['streaming_match_rate']:.1f}"
          f"  {match_pass}")
    print()

    print(f"  [청크 크기별]")
    for label, data in report["by_chunk_size"].items():
        lat = data["latency_ms"]
        print(f"    chunk={label:>6s}  match={data['match_rate']:.4f}"
              f"  ({data['match_n']})  p50={lat['p50']:.2f}ms"
              f"  p95={lat['p95']:.2f}ms")
    print()

    if report["by_category"]:
        print(f"  [카테고리별]")
        for cat, d in sorted(report["by_category"].items()):
            print(f"    {cat:25s}  match={d['match_rate']:.4f}  ({d['match']}/{d['n']})")
        print()

    if report["mismatches"]:
        print(f"  [불일치 샘플] ({report['n_mismatches']}건)")
        for m in report["mismatches"][:5]:
            print(f"    {m['id']} ({m['category']})"
                  f"  실패 청크: {list(m['failed_chunks'].keys())}")
        if report["n_mismatches"] > 5:
            print(f"    ... 외 {report['n_mismatches'] - 5}건")
        print()

    print(f"  종합: {match_pass}")
    print("=" * 65)

    # JSON 출력
    out = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(out + "\n", encoding="utf-8")
        print(f"\n리포트 저장: {args.json_out}")

    return 0 if report["acceptance_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
