"""recall/precision + 인라인 지연 측정 (SPEC 산출물: M5에서 본격화, M2는 스텁/참고치).

실행: python3 scripts/bench.py [--ner gazetteer|transformers|auto]

KR 목표(참고): 한국어 PII recall ≥ 0.9 / 인라인 지연 p95 ≤ 150ms(CPU).
gazetteer 백엔드는 최소 보장 라인이며, recall ≥ 0.9 목표는 transformers/ONNX 백엔드로 달성.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import EgressGuard  # noqa: E402

SAMPLES = ROOT / "samples"


def load(name):
    return [json.loads(l) for l in open(SAMPLES / name, encoding="utf-8") if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ner", default="gazetteer", choices=["gazetteer", "transformers", "auto"])
    ap.add_argument("--warmup", type=int, default=5)
    args = ap.parse_args()

    g = EgressGuard(ner_backend=args.ner)
    pii = load("pii_samples.jsonl")
    secrets = load("secret_samples.jsonl")
    benign = load("benign_samples.jsonl")

    # --- recall (PII + secrets) ---
    exp_tot = hit = 0
    for s in pii:
        got = {f.entity_type for f in g.inspect(s["prompt"]).findings}
        for e in s["expect"]:
            exp_tot += 1
            hit += (e in got)
    sec_hit = sum(1 for s in secrets
                  if any(f.entity_type == "SECRET" for f in g.inspect(s["prompt"]).findings))

    # --- precision sanity (benign false-positive findings) ---
    fp_findings = sum(len(g.inspect(s["prompt"]).findings) for s in benign)
    fp_blocks = sum(1 for s in benign if g.inspect(s["prompt"]).blocked)

    # --- latency (per-request, CPU) ---
    corpus = [s["prompt"] for s in (pii + secrets + benign)]
    for _ in range(args.warmup):
        for p in corpus:
            g.inspect(p)
    lat = []
    for _ in range(20):
        for p in corpus:
            t0 = time.perf_counter()
            g.inspect(p)
            lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()
    p50 = statistics.median(lat)
    p95 = lat[int(len(lat) * 0.95)]
    p99 = lat[int(len(lat) * 0.99)]

    print(f"NER backend         : {g.ner_backend}")
    print(f"PII recall          : {hit/exp_tot:.3f} ({hit}/{exp_tot})  [목표 ≥ 0.9]")
    print(f"Secret recall       : {sec_hit/len(secrets):.3f} ({sec_hit}/{len(secrets)})")
    print(f"Benign false-blocks : {fp_blocks}/{len(benign)}")
    print(f"Benign FP findings  : {fp_findings}")
    print(f"Latency ms (CPU)    : p50={p50:.2f}  p95={p95:.2f}  p99={p99:.2f}  [목표 p95 ≤ 150ms]")
    print(f"Latency target p95  : {'PASS' if p95 <= 150 else 'FAIL'}")


if __name__ == "__main__":
    main()
