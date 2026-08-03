"""멀티-인스턴스(프로세스) NER 추론 워커풀 — GIL 우회 (CMP-130, CMP-127 후속).

왜 프로세스인가 (CMP-127 §3 실측 근거)
--------------------------------------
CMP-127 은 in-process 스레드풀(`_infer_pool.BoundedInference`)이 부하 하
C≥4 에서 p95 게이트(≤150ms)를 못 맞춤을 정량 확정했다. 근인은 **CPython GIL**:
공유 HF `pipeline` 의 토크나이즈 디스패치 + `aggregation_strategy` 후처리(파이썬)
가 GIL 을 잡아 **공유 파이프라인 호출이 직렬화**된다. onnxruntime `Run`(C++)이
GIL 을 풀어도 파이썬 글루가 직렬화되어 스레드 W 를 늘려도 처리량이 포화한다.

GIL 회피의 정석은 **스레드가 아니라 프로세스**다. 각 워커 프로세스가 자체
인터프리터(자체 GIL)·자체 추론 세션을 가지므로 파이썬 글루가 **진짜 병렬**로
실행된다 → 처리량이 워커수 P 에 선형 근접(코어 한도까지)한다. 이 모듈은 그
구조적 해법을 in-repo 로 시연하는 PoC 다(측정: `scripts/bench_proc_pool.py`).

설계
----
- ``ProcessInferencePool(workers=P)`` — `ProcessPoolExecutor` 로 P개 워커 기동.
  각 워커는 initializer 에서 **자체 `EgressGuard` 1개**를 lazy 빌드(자체 모델 로드).
- 워커당 intra-op=1 로 캡 → P 워커 × 1 스레드 = 총 P 스레드(코어 전용화). 따라서
  P = cores 일 때 코어를 꽉 채우되 과구독 없음(W×K≈cores 의 프로세스판).
- ``inspect(text)`` 결과는 프로세스 경계를 넘으므로 **picklable 요약**
  (`InspectSummary`: blocked·finding 수·backend)만 반환한다. GuardResult 전체
  객체(정책/스팬)는 직렬화 비용·결합도가 커 PoC 측정엔 불필요.

start method
------------
기본 ``spawn`` — onnxruntime/torch 세션은 fork-after-load 시 불안정(스레드/뮤텍스
상속)하므로, 워커를 fresh 인터프리터로 띄워 각자 모델을 로드한다. 부모는 모델을
로드하지 않는다(워커만 로드). env ``NUFI_NER_PROC_START`` 로 재정의 가능.

이 모듈은 detectors 레벨 동시성 primitive 로, in-process `_infer_pool` 의
형제다. 운영 기본 경로 교체가 아니라 **수평확장(프로세스/인스턴스) 측정용**이다.
"""
from __future__ import annotations

import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import List, Optional

from ._infer_pool import cpu_count

# ── 워커 프로세스 전역 (initializer 에서 1회 빌드) ──────────────────────────
_WORKER_GUARD = None  # type: ignore[var-annotated]


@dataclass(frozen=True)
class InspectSummary:
    """프로세스 경계를 넘는 picklable 검사 요약(GuardResult 의 측정용 축약)."""

    blocked: bool
    n_findings: int
    backend: str


def _worker_init(backend: str, model_id: Optional[str]) -> None:
    """워커당 1회: 자체 EgressGuard(자체 모델/추론 세션) 빌드.

    워커당 intra-op=1 로 캡해 P 워커 × 1 스레드 = 총 P 스레드(코어 전용화).
    env 를 워커 프로세스 안에서 설정하므로 부모/형제 프로세스에 영향 없다.
    """
    os.environ.setdefault("NUFI_NER_INTRA_OP_THREADS", "1")
    os.environ.setdefault("NUFI_NER_INFER_WORKERS", "1")  # 프로세스당 in-flight 1
    from egress_audit import EgressGuard  # 워커 인터프리터에서 import

    global _WORKER_GUARD
    _WORKER_GUARD = EgressGuard(ner_backend=backend, **({"model_id": model_id} if model_id else {}))


def _worker_inspect(text: str) -> InspectSummary:
    """워커에서 guard.inspect 실행 → picklable 요약 반환."""
    assert _WORKER_GUARD is not None, "worker guard not initialized"
    res = _WORKER_GUARD.inspect(text)
    return InspectSummary(
        blocked=bool(res.blocked),
        n_findings=len(res.findings),
        backend=_WORKER_GUARD.ner_backend,
    )


def _start_method() -> str:
    return os.environ.get("NUFI_NER_PROC_START", "spawn")


class ProcessInferencePool:
    """P개 워커 프로세스로 NER 검사를 분산해 GIL 을 우회한다.

    각 워커가 자체 인터프리터·자체 추론 세션을 가지므로 파이썬 핫패스
    (토크나이즈 디스패치 + aggregation 후처리)가 진짜 병렬로 실행된다.
    """

    def __init__(self, workers: Optional[int] = None, *, backend: str = "onnx-int8",
                 model_id: Optional[str] = None):
        self.workers = workers if workers is not None else cpu_count()
        self.backend = backend
        self.model_id = model_id
        ctx = mp.get_context(_start_method())
        self._ex = ProcessPoolExecutor(
            max_workers=self.workers,
            mp_context=ctx,
            initializer=_worker_init,
            initargs=(backend, model_id),
        )

    def warmup(self, body: str) -> None:
        """모든 워커가 모델을 로드하고 1회 추론하도록 워밍업(콜드스타트 제거)."""
        list(self._ex.map(_worker_inspect, [body] * self.workers))

    def inspect(self, text: str):
        """단건 검사 future. `.result()` 로 InspectSummary 획득."""
        return self._ex.submit(_worker_inspect, text)

    def map(self, texts: List[str]) -> List[InspectSummary]:
        """다건 검사를 워커풀에 분산(순서 보존)."""
        return list(self._ex.map(_worker_inspect, texts))

    @property
    def config(self) -> dict:
        return {
            "mode": "process_pool",
            "workers": self.workers,
            "backend": self.backend,
            "start_method": _start_method(),
            "intra_op_per_worker": 1,
            "cpu_count": cpu_count(),
        }

    def shutdown(self) -> None:
        self._ex.shutdown(wait=True, cancel_futures=True)

    def __enter__(self) -> "ProcessInferencePool":
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown()
