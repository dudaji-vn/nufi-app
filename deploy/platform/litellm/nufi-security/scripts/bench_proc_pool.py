"""CMP-130 — 멀티-인스턴스(프로세스) 워커풀 PoC 측정 (CMP-127 후속).

CMP-127 §3 은 in-process 스레드풀이 GIL 로 C≥4 처리량이 포화함을 확정했다.
본 하니스는 **동일 박스**에서 두 구성의 처리량 μ(req/s)·지연 p95 를 직접 비교해
프로세스 분리의 GIL 우회 효과를 정량화한다(절대 ms 가 아니라 **상대 비교**에
결론을 앵커 — 측정 박스 경합 가능성 때문, CMP-127 §1 과 동일 원칙).

세 구성 (동일 입력 512자, 동일 backend):
  1. thread@C   — 단일 EgressGuard + ThreadPoolExecutor(C) (= 현 운영 in-process 경로)
  2. proc@P     — ProcessInferencePool(P) (= 수평확장 1박스 시뮬레이션, 워커당 모델 1벌)
  3. serial     — 단일스레드 순차(μ₁ 기준선; 워커당 서비스율 추정)

판정: μ_proc / μ_serial ≈ P (선형 근접) 이고 μ_thread 가 포화하면 GIL 우회 입증.

실행:
  PYTHONPATH=$HOME/.cache/m5_libs python3 scripts/bench_proc_pool.py \
      --backend onnx-int8 --workers 1,2,4 --requests 120 \
      --json-out docs/reports/CMP-130-procpool.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

P95_TARGET_MS = 150.0  # NFR2

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


def _measure(name, run_one, n, *, warmup=10):
    """run_one() -> latency_ms 콜백을 n회 실행해 처리량/지연 집계."""
    for _ in range(warmup):
        run_one()
    lat = []
    t0 = time.perf_counter()
    for _ in range(n):
        lat.append(run_one())
    wall = time.perf_counter() - t0
    lat.sort()
    p95 = _pct(lat, 0.95)
    return {
        "mode": name,
        "requests": n,
        "throughput_req_s": round(n / wall, 1) if wall else 0.0,
        "lat_p50_ms": _pct(lat, 0.50),
        "lat_p95_ms": p95,
        "lat_p99_ms": _pct(lat, 0.99),
        "mean_ms": round(statistics.fmean(lat), 3),
        "wall_s": round(wall, 3),
        "p95_le_150ms": p95 <= P95_TARGET_MS,
    }


def serial_baseline(guard, body, n):
    """단일스레드 순차 μ₁(워커당 서비스율 기준선)."""
    def run_one():
        t = time.perf_counter()
        guard.inspect(body)
        return (time.perf_counter() - t) * 1000.0
    return _measure("serial", run_one, n)


def thread_pool(guard, body, n, concurrency):
    """현 운영 경로: 단일 guard + ThreadPoolExecutor(C). GIL 직렬화 대상."""
    lat = []
    def submit_one(_):
        t = time.perf_counter()
        guard.inspect(body)
        return (time.perf_counter() - t) * 1000.0
    # 워밍업
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        list(ex.map(submit_one, range(min(10, n))))
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        for f in as_completed([ex.submit(submit_one, i) for i in range(n)]):
            lat.append(f.result())
    wall = time.perf_counter() - t0
    lat.sort()
    p95 = _pct(lat, 0.95)
    return {
        "mode": f"thread@C={concurrency}", "requests": n, "concurrency": concurrency,
        "throughput_req_s": round(n / wall, 1) if wall else 0.0,
        "lat_p50_ms": _pct(lat, 0.50), "lat_p95_ms": p95, "lat_p99_ms": _pct(lat, 0.99),
        "mean_ms": round(statistics.fmean(lat), 3), "wall_s": round(wall, 3),
        "p95_le_150ms": p95 <= P95_TARGET_MS,
    }


def process_pool(body, n, workers, backend, model_id):
    """ProcessInferencePool(P): 워커당 자체 모델/GIL → 진짜 병렬."""
    from egress_audit.detectors._proc_pool import ProcessInferencePool
    lat = []
    with ProcessInferencePool(workers=workers, backend=backend, model_id=model_id) as pool:
        pool.warmup(body)  # 모든 워커 모델 로드 + 1회 추론(콜드스타트 제거)
        # P 워커를 포화시키도록 P in-flight 유지하며 n건 제출
        t0 = time.perf_counter()
        futures = [pool.inspect(body) for _ in range(n)]
        for f in futures:
            t = time.perf_counter()
            f.result()
            # 개별 지연은 제출-완료 분리가 어려워 wall 기반 μ 를 주지표로 사용
        wall = time.perf_counter() - t0
    return {
        "mode": f"proc@P={workers}", "requests": n, "workers": workers,
        "throughput_req_s": round(n / wall, 1) if wall else 0.0,
        "wall_s": round(wall, 3),
        "note": "프로세스풀 μ 는 wall 기반 집계(워커당 모델 1벌). 워밍업 후 측정.",
    }


def build_guard(backend):
    from egress_audit import EgressGuard
    if backend in ("transformers", "onnx-int8"):
        try:
            import transformers  # noqa: F401
        except Exception:
            return None, f"{backend} 미설치(transformers 없음)."
        if backend == "onnx-int8":
            try:
                import onnxruntime  # noqa: F401
                import optimum.onnxruntime  # noqa: F401
            except Exception:
                return None, "onnx-int8 미설치(onnxruntime/optimum 없음)."
        try:
            return EgressGuard(ner_backend=backend), None
        except Exception as e:
            return None, f"{backend} 로드 실패: {e}"
    return EgressGuard(ner_backend="gazetteer"), None


def _env_snapshot():
    from egress_audit.detectors._infer_pool import cpu_count
    snap = {"cpu_count": cpu_count(), "nproc": os.cpu_count()}
    try:
        snap["loadavg"] = [round(x, 2) for x in os.getloadavg()]
    except (AttributeError, OSError):
        pass
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    snap["mem_total_kb"] = int(line.split()[1])
                    break
    except OSError:
        pass
    return snap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="onnx-int8",
                    choices=["gazetteer", "transformers", "onnx-int8"])
    ap.add_argument("--workers", default="1,2,4", help="콤마구분 프로세스/스레드 수")
    ap.add_argument("--requests", type=int, default=120, help="구성당 요청수")
    ap.add_argument("--chars", type=int, default=512)
    ap.add_argument("--model-id", default=None)
    ap.add_argument("--json-out")
    args = ap.parse_args()

    body = make_body(args.chars)
    levels = [int(x) for x in args.workers.split(",") if x.strip()]
    report = {
        "backend": args.backend, "chars": args.chars,
        "p95_target_ms": P95_TARGET_MS, "env": _env_snapshot(),
        "requests_per_config": args.requests,
    }

    guard, reason = build_guard(args.backend)
    if guard is None:
        report["backend_status"] = "unavailable"
        report["reason"] = reason
        out = json.dumps(report, ensure_ascii=False, indent=2)
        print(out)
        if args.json_out:
            Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.json_out).write_text(out, encoding="utf-8")
        print(f"\n[SKIP] {args.backend}: {reason}")
        return 0

    report["ner_backend_active"] = guard.ner_backend
    report["ner_pool_config"] = guard.ner_pool_config

    # 1) 단일스레드 순차 μ₁ (워커당 서비스율 기준선)
    report["serial"] = serial_baseline(guard, body, args.requests)
    mu1 = report["serial"]["throughput_req_s"]

    # 2) in-process 스레드풀 (현 운영 경로) — C 스윕
    report["thread_pool"] = [thread_pool(guard, body, args.requests, c) for c in levels]

    # 3) 프로세스풀 — P 스윕 (별도 프로세스이므로 부모 guard 와 메모리 분리)
    del guard  # 부모는 모델 점유 해제(프로세스풀 워커가 자체 로드)
    report["process_pool"] = [process_pool(body, args.requests, p, args.backend, args.model_id)
                              for p in levels]

    # 4) GIL 우회 판정: 프로세스풀 μ 가 워커수에 선형 근접 vs 스레드풀 포화
    report["scaling"] = {
        "serial_mu_req_s": mu1,
        "thread_mu_by_C": {str(r.get("concurrency")): r["throughput_req_s"]
                           for r in report["thread_pool"]},
        "proc_mu_by_P": {str(r["workers"]): r["throughput_req_s"]
                         for r in report["process_pool"]},
        "proc_speedup_vs_serial": {str(r["workers"]): round(r["throughput_req_s"] / mu1, 2)
                                   for r in report["process_pool"]} if mu1 else {},
        "thread_speedup_vs_serial": {str(r.get("concurrency")): round(r["throughput_req_s"] / mu1, 2)
                                     for r in report["thread_pool"]} if mu1 else {},
    }

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
