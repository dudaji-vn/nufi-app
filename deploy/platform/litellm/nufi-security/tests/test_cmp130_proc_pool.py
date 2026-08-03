"""CMP-130 — 멀티-인스턴스(프로세스) 워커풀 PoC: 단위 테스트.

하드웨어/모델 독립 불변식(설정·picklable 요약·start method)을 검증한다.
실제 모델 추론은 air-gapped CI 에서 불가하므로 transformers 가용 시에만
end-to-end 기능 테스트를 수행한다(없으면 skip).
"""
import pickle
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress_audit.detectors._proc_pool import (  # noqa: E402
    InspectSummary, ProcessInferencePool, _start_method)


def _models_available() -> bool:
    try:
        import transformers  # noqa: F401
        import onnxruntime  # noqa: F401
        import optimum.onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def test_inspect_summary_is_picklable():
    """프로세스 경계를 넘는 결과는 반드시 picklable(round-trip 동일)."""
    s = InspectSummary(blocked=True, n_findings=3, backend="onnx-int8")
    back = pickle.loads(pickle.dumps(s))
    assert back == s
    assert back.blocked is True and back.n_findings == 3


def test_default_start_method_is_spawn():
    """기본 start method 는 spawn(ORT/torch fork-after-load 불안정 회피)."""
    assert _start_method() == "spawn"


def test_start_method_env_override(monkeypatch):
    monkeypatch.setenv("NUFI_NER_PROC_START", "forkserver")
    assert _start_method() == "forkserver"


def test_config_reports_isolation_invariants():
    """config 는 워커당 intra-op=1(코어 전용화) 및 프로세스 모드를 보고한다.

    풀을 즉시 shutdown 해 워커 모델 로드 없이 설정만 검사(모델 불필요).
    """
    pool = ProcessInferencePool(workers=2, backend="gazetteer")
    try:
        cfg = pool.config
        assert cfg["mode"] == "process_pool"
        assert cfg["workers"] == 2
        assert cfg["intra_op_per_worker"] == 1  # W×K 의 프로세스판: 워커당 1스레드
        assert cfg["backend"] == "gazetteer"
        assert cfg["start_method"] == "spawn"
    finally:
        pool.shutdown()


def test_workers_defaults_to_cpu_count():
    from egress_audit.detectors._infer_pool import cpu_count
    pool = ProcessInferencePool(backend="gazetteer")
    try:
        assert pool.config["workers"] == cpu_count()
    finally:
        pool.shutdown()


@pytest.mark.skipif(not _models_available(), reason="NER 모델 스택 미설치(에어갭 CI)")
def test_process_pool_inspect_end_to_end():
    """워커가 자체 모델을 로드하고 inspect 를 수행해 요약을 반환한다(GIL 우회 경로)."""
    body = "고객 김철수 부장 연락처 010-1234-5678 user@company.co.kr 서울특별시 확인."
    with ProcessInferencePool(workers=2, backend="onnx-int8") as pool:
        pool.warmup(body)
        results = pool.map([body, body, body])
        assert len(results) == 3
        assert all(isinstance(r, InspectSummary) for r in results)
        assert all(r.backend == "onnx-int8" for r in results)
        # PII 가 포함된 입력 → finding 이 최소 1개 이상 잡혀야 한다.
        assert all(r.n_findings >= 1 for r in results)
