"""부하 하 NER 추론 동시성 제어 — 코어 전용화 (CMP-127 동시성 하드닝).

문제(CMP-123 D3 §3.5 실측 근거)
--------------------------------
onnxruntime/torch 추론 세션은 intra-op 스레드로 코어를 점유한다. N개 요청
스레드가 공유 가드(`EgressGuard.inspect`)를 동시에 때리면 N×(코어수) 개의
intra-op 스레드가 코어를 **과구독(oversubscription)** 하여 컨텍스트 스위치
스래싱이 발생, 부하 p95 가 폭증한다(예: INT8 198ms@C4 → 1468ms@C16, 12코어).

해법(코어 전용화)
-----------------
1. 세션당 intra-op 스레드를 K 로 **캡**한다(`SessionOptions.intra_op_num_threads`).
2. 공유 bounded 세마포어로 동시 추론 수를 W = max(1, cores // K) 로 **제한**한다.

W×K ≈ cores 이므로 동시에 도는 추론들의 총 스레드가 코어수에 수렴 → 각 추론이
무부하에 근접한 지연으로 실행되고, W 를 초과하는 요청은 공정 대기(큐잉)한다.
naive 동시성(모든 요청이 모든 코어로 intra-op 확장)의 과구독을 제거한다.

튜닝(배포 환경 의존 — 코어수에 따라 재측정 권고)
-----------------------------------------------
- ``NUFI_NER_INTRA_OP_THREADS``  세션당 intra-op 스레드 캡 K (기본 1).
- ``NUFI_NER_INFER_WORKERS``     동시 추론 허용 수 W (기본 cores // K).

K=1 은 추론을 단일스레드화해 코어당 1 in-flight 추론을 보장(동시성 처리량 최대,
단건 무부하 지연은 상승). 단건 지연이 게이트(≤150ms)를 위협하면 K 를 키우고 W 를
줄여(예: K=2) 단건 지연과 동시성을 절충한다.
"""
from __future__ import annotations

import os
import threading
from typing import Callable, Optional, TypeVar

T = TypeVar("T")


def cpu_count() -> int:
    """가용 코어수. cgroup/affinity 제약을 반영(컨테이너 안전)."""
    try:
        return max(1, len(os.sched_getaffinity(0)))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def _env_int(name: str) -> Optional[int]:
    raw = os.environ.get(name)
    if not raw:
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        return None


def intra_op_threads() -> int:
    """세션당 intra-op 스레드 캡 K. env NUFI_NER_INTRA_OP_THREADS 우선, 기본 1.

    onnxruntime 기본값(=코어수)을 그대로 두면 C개 동시요청이 C×cores 개 intra-op
    스레드로 코어를 과구독한다(12코어 박스 C4=198ms 의 근인). K 를 작은 상수로 캡하고
    W=cores//K 로 동시 추론을 제한하면 총 추론 스레드 W×K≈cores 로 수렴해 과구독이
    사라진다. 단건 지연이 더 중요하면 K↑(예: =코어수)로 튜닝.
    """
    return _env_int("NUFI_NER_INTRA_OP_THREADS") or 1


def worker_count(intra_op: Optional[int] = None) -> int:
    """동시 추론 허용 수 W. env NUFI_NER_INFER_WORKERS 우선, 아니면 cores // K.

    W×K ≈ cores 로 동시 추론들의 총 intra-op 스레드를 코어수에 수렴시켜 과구독을
    제거한다(코어 전용화). 동시 추론 수가 호출자 동시성 C 와 무관하게 W 로 상한.
    """
    env = _env_int("NUFI_NER_INFER_WORKERS")
    if env is not None:
        return env
    k = intra_op if intra_op is not None else intra_op_threads()
    return max(1, cpu_count() // max(1, k))


class BoundedInference:
    """공유 세마포어로 동시 추론 수를 W 로 제한해 코어 과구독을 방지한다.

    하나의 백엔드 인스턴스에 1개 생성되어 가드를 공유하는 모든 요청 스레드가
    같은 세마포어를 통과한다(인프로세스 게이트웨이 부하 모델과 일치).
    """

    def __init__(self, workers: Optional[int] = None, intra_op: Optional[int] = None):
        self.intra_op = intra_op if intra_op is not None else intra_op_threads()
        self.workers = workers if workers is not None else worker_count(self.intra_op)
        self._sem = threading.BoundedSemaphore(self.workers)

    def run(self, fn: Callable[..., T], *args, **kwargs) -> T:
        """fn 실행을 동시 W 건으로 제한. 초과 호출은 슬롯이 날 때까지 대기."""
        with self._sem:
            return fn(*args, **kwargs)

    @property
    def config(self) -> dict:
        return {"intra_op_threads": self.intra_op, "infer_workers": self.workers,
                "cpu_count": cpu_count()}
