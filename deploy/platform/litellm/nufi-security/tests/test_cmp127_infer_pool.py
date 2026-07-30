"""CMP-127 — NER 동시성 하드닝: bounded 추론 풀 단위 테스트.

부하 하 코어 과구독을 막는 핵심 불변식(동시 추론 ≤ W)을 하드웨어 독립적으로
검증한다. 실제 모델/onnxruntime 없이 BoundedInference 자체를 검사한다.
"""
import os
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress_audit.detectors._infer_pool import (  # noqa: E402
    BoundedInference, intra_op_threads, worker_count, cpu_count)


def _run_concurrently(pool, callers, hold_s=0.03):
    """callers 개 스레드가 동시에 pool.run 을 때릴 때 관측된 최대 동시 실행수."""
    state = {"cur": 0, "peak": 0}
    lock = threading.Lock()

    def job():
        with lock:
            state["cur"] += 1
            state["peak"] = max(state["peak"], state["cur"])
        time.sleep(hold_s)
        with lock:
            state["cur"] -= 1

    threads = [threading.Thread(target=lambda: pool.run(job)) for _ in range(callers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return state["peak"]


def test_pool_caps_concurrency_at_W():
    """동시 추론은 W 를 절대 넘지 않는다(과구독 방지의 핵심 불변식)."""
    pool = BoundedInference(workers=2, intra_op=2)
    peak = _run_concurrently(pool, callers=8)
    assert peak <= 2, f"동시 실행 {peak} > W=2 — 세마포어가 동시성을 제한하지 못함"


def test_pool_allows_up_to_W():
    """W 개까지는 실제로 병렬 실행된다(불필요한 직렬화 없음)."""
    pool = BoundedInference(workers=3, intra_op=1)
    peak = _run_concurrently(pool, callers=6)
    assert peak == 3, f"기대 동시 실행 3, 관측 {peak}"


def test_run_returns_value_and_propagates_args():
    pool = BoundedInference(workers=1, intra_op=1)
    assert pool.run(lambda a, b: a + b, 2, 3) == 5


def test_threads_bounded_independent_of_caller_concurrency():
    """핵심 불변식: 동시 추론 수가 호출자 동시성 C 와 무관하게 W 로 상한.

    총 추론 스레드 ≤ W×K(상수) → C×cores 무한 과구독 제거(하드웨어 독립).
    """
    pool = BoundedInference()
    assert pool.workers >= 1 and pool.intra_op >= 1
    # K 는 코어수를 넘지 않음(다코어 폭발 차단 상한 적용).
    assert pool.intra_op <= cpu_count()
    # 호출자가 W 의 5배여도 동시 실행은 W 를 넘지 않는다.
    peak = _run_concurrently(pool, callers=pool.workers * 5)
    assert peak <= pool.workers, f"동시 실행 {peak} > W={pool.workers}"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("NUFI_NER_INTRA_OP_THREADS", "3")
    monkeypatch.setenv("NUFI_NER_INFER_WORKERS", "5")
    assert intra_op_threads() == min(3, cpu_count())
    assert worker_count() == 5
    pool = BoundedInference()
    assert pool.workers == 5


def test_default_worker_count_formula(monkeypatch):
    """기본 W = cores // K (코어 전용화). K=1(기본) → W=cores."""
    monkeypatch.delenv("NUFI_NER_INFER_WORKERS", raising=False)
    monkeypatch.delenv("NUFI_NER_INTRA_OP_THREADS", raising=False)
    k = intra_op_threads()
    assert worker_count() == max(1, cpu_count() // max(1, k))


def test_default_intra_op_is_one(monkeypatch):
    """기본 K = 1: onnxruntime 기본(=코어수)을 캡해 C×cores 과구독을 차단."""
    monkeypatch.delenv("NUFI_NER_INTRA_OP_THREADS", raising=False)
    assert intra_op_threads() == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
