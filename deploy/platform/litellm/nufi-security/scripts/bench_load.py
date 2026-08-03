"""CMP-123 D3 — 동시성·지속부하 p95 측정 하니스 (NFR2 ≤150ms 검증).

`scripts/bench_m5.py` 의 단일스레드 지연 측정을 보완한다. 게이트웨이 pre_call
훅(`EgressGuard.inspect`)은 동기 호출이므로, 다중 클라이언트가 공유 가드를
동시에 때릴 때의 *부하 하 p95* 와 처리량/큐지연/감사봇 백프레셔 기준선을 측정한다.

측정 항목
---------
- **동시성 스윕**: concurrency C ∈ {1,4,8,16} 각각에서 512자 입력 N회 →
  요청 지연 p50/p95/p99 + 처리량(req/s) + 제출→시작 큐지연(스케줄 대기).
- **지속부하**: 목표 동시성에서 D초 연속 → 처리량 안정성 + 구간 p95 드리프트.
- **감사봇 백프레셔 기준선**: 단일 워커 최대 서비스율 μ(req/s) 측정.
  도착률 λ>μ 이면 비동기 감사 큐가 무한 증가 → λ_safe ≈ μ 가 백프레셔 임계.

GIL 주의: 탐지는 CPU 바운드라 스레드 동시성은 진짜 병렬이 아니다(인프로세스
게이트웨이의 현실적 모델). 따라서 동시성↑ 시 처리량 포화 + 요청 지연 상승이
관측되는 것이 정상이며, 본 리포트는 그 포화점과 부하 하 p95 를 기록한다.

실행:
  python3 scripts/bench_load.py                         # 기본 스윕 + 지속 + 백프레셔
  python3 scripts/bench_load.py --backend gazetteer --concurrency 1,4,8,16 \
      --requests 200 --sustain-seconds 10 --json-out docs/reports/load-p95.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import EgressGuard  # noqa: E402

P95_TARGET_MS = 150.0  # NFR2

# bench_m5.latency 와 동일 계열의 512자 대표 입력(고객 PII + 업무 필러)
_BASE_PII = "고객 연락처 010-1234-5678 이메일 user@company.co.kr 확인 부탁드립니다. "
_FILLER = "이 문서는 분기 운영 리뷰를 위한 일반 업무 텍스트입니다. "


def make_body(approx: int = 512) -> str:
    body = _BASE_PII
    while len(body) < approx:
        body += _FILLER
    return body[:approx]


def _pct(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(len(sorted_vals) * q))
    return round(sorted_vals[idx], 3)


def build_guard(backend: str):
    """transformers/onnx-int8 미설치 시 (None, reason). gazetteer 는 항상 가용."""
    if backend in ("transformers", "onnx-int8"):
        try:
            import transformers  # noqa: F401
        except Exception:
            return None, f"{backend} 미설치(transformers 없음) — 에어갭. 모델 프로비저닝 후 재측정."
        if backend == "onnx-int8":
            try:
                import onnxruntime  # noqa: F401
                import optimum.onnxruntime  # noqa: F401
            except Exception:
                return None, "onnx-int8 미설치(onnxruntime/optimum 없음)."
        try:
            return EgressGuard(ner_backend=backend), None
        except Exception as e:  # 모델 미산출 등
            return None, f"{backend} 로드 실패: {e}"
    return EgressGuard(ner_backend="gazetteer"), None


def concurrency_sweep(guard, body, levels, requests_per_level, warmup=20):
    """동시성 C 별: 부하 하 요청 지연 p50/95/99 + 처리량 + 큐지연."""
    for _ in range(warmup):
        guard.inspect(body)

    results = {}
    for c in levels:
        latencies = []        # 순수 처리 지연(ms)
        queue_delays = []     # 제출→실제 시작 대기(ms): 동시성 포화 시 상승
        lock = threading.Lock()

        def task(submit_t):
            start = time.perf_counter()
            qd = (start - submit_t) * 1000.0
            guard.inspect(body)
            dur = (time.perf_counter() - start) * 1000.0
            with lock:
                latencies.append(dur)
                queue_delays.append(qd)

        t_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=c) as ex:
            futures = []
            for _ in range(requests_per_level):
                submit_t = time.perf_counter()
                futures.append(ex.submit(task, submit_t))
            for f in as_completed(futures):
                f.result()
        wall = time.perf_counter() - t_start

        latencies.sort()
        queue_delays.sort()
        p95 = _pct(latencies, 0.95)
        results[str(c)] = {
            "concurrency": c,
            "requests": requests_per_level,
            "lat_p50_ms": _pct(latencies, 0.50),
            "lat_p95_ms": p95,
            "lat_p99_ms": _pct(latencies, 0.99),
            "lat_max_ms": round(latencies[-1], 3),
            "queue_delay_p95_ms": _pct(queue_delays, 0.95),
            "throughput_req_s": round(requests_per_level / wall, 1) if wall else 0.0,
            "wall_s": round(wall, 3),
            "p95_le_150ms": p95 <= P95_TARGET_MS,
        }
    return results


def sustained(guard, body, concurrency, seconds):
    """지속부하: D초 연속 부하 → 처리량 안정성 + 1초 구간 p95 드리프트."""
    stop_at = time.perf_counter() + seconds
    all_lat = []
    bucket_lat = []
    bucket_start = time.perf_counter()
    intervals = []
    count = 0
    lock = threading.Lock()

    def worker():
        nonlocal count, bucket_start
        while time.perf_counter() < stop_at:
            t0 = time.perf_counter()
            guard.inspect(body)
            dur = (time.perf_counter() - t0) * 1000.0
            with lock:
                all_lat.append(dur)
                bucket_lat.append(dur)
                count += 1
                if time.perf_counter() - bucket_start >= 1.0:
                    bl = sorted(bucket_lat)
                    intervals.append({"p95_ms": _pct(bl, 0.95), "n": len(bl)})
                    bucket_lat.clear()
                    bucket_start = time.perf_counter()

    t_start = time.perf_counter()
    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - t_start

    all_lat.sort()
    p95s = [iv["p95_ms"] for iv in intervals] or [0.0]
    p95 = _pct(all_lat, 0.95)
    return {
        "concurrency": concurrency,
        "duration_s": round(wall, 2),
        "total_requests": count,
        "throughput_req_s": round(count / wall, 1) if wall else 0.0,
        "lat_p50_ms": _pct(all_lat, 0.50),
        "lat_p95_ms": p95,
        "lat_p99_ms": _pct(all_lat, 0.99),
        "interval_p95_min_ms": round(min(p95s), 3),
        "interval_p95_max_ms": round(max(p95s), 3),
        "p95_le_150ms": p95 <= P95_TARGET_MS,
    }


def backpressure_baseline(guard, body, samples=500, warmup=20):
    """감사봇 백프레셔 기준선: 단일 워커 최대 서비스율 μ(req/s).

    비동기 감사 큐(FileQueue→AuditBot)는 인스펙션 서비스율 μ 로 드레인된다.
    도착률 λ>μ 면 큐가 무한 증가 → 백프레셔. λ_safe ≈ μ 가 안정 임계.
    """
    for _ in range(warmup):
        guard.inspect(body)
    lat = []
    t_start = time.perf_counter()
    for _ in range(samples):
        t0 = time.perf_counter()
        guard.inspect(body)
        lat.append((time.perf_counter() - t0) * 1000.0)
    wall = time.perf_counter() - t_start
    lat.sort()
    mu = round(samples / wall, 1) if wall else 0.0
    mean_ms = round(statistics.fmean(lat), 3)
    return {
        "service_rate_mu_req_s": mu,
        "mean_service_ms": mean_ms,
        "p95_service_ms": _pct(lat, 0.95),
        "lambda_safe_req_s": mu,
        "note": "도착률 λ ≤ μ 이면 감사 큐 안정(유한 대기). λ>μ 면 큐 무한 증가→백프레셔.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="gazetteer",
                    choices=["gazetteer", "transformers", "onnx-int8"])
    ap.add_argument("--concurrency", default="1,4,8,16",
                    help="콤마구분 동시성 레벨")
    ap.add_argument("--requests", type=int, default=200, help="레벨당 요청수")
    ap.add_argument("--chars", type=int, default=512, help="입력 길이(자) — NFR2 기준 512")
    ap.add_argument("--sustain-seconds", type=int, default=10)
    ap.add_argument("--sustain-concurrency", type=int, default=8)
    ap.add_argument("--json-out")
    args = ap.parse_args()

    guard, reason = build_guard(args.backend)
    report = {"backend": args.backend, "chars": args.chars, "p95_target_ms": P95_TARGET_MS}

    if guard is None:
        report["backend_status"] = "unavailable"
        report["reason"] = reason
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\n[SKIP] {args.backend}: {reason}")
        return 0

    report["ner_backend_active"] = guard.ner_backend
    report["ner_pool_config"] = guard.ner_pool_config  # CMP-127: K/W/cores
    body = make_body(args.chars)
    levels = [int(x) for x in args.concurrency.split(",") if x.strip()]

    report["concurrency_sweep"] = concurrency_sweep(guard, body, levels, args.requests)
    report["sustained"] = sustained(guard, body, args.sustain_concurrency, args.sustain_seconds)
    report["backpressure"] = backpressure_baseline(guard, body)

    # 종합 판정: 모든 동시성 레벨 + 지속부하 p95 ≤ 150ms?
    sweep_ok = all(v["p95_le_150ms"] for v in report["concurrency_sweep"].values())
    report["all_concurrency_p95_le_150ms"] = sweep_ok and report["sustained"]["p95_le_150ms"]

    out = json.dumps(report, ensure_ascii=False, indent=2)
    print(out)
    if args.json_out:
        p = Path(args.json_out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out, encoding="utf-8")
        print(f"\n[written] {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
