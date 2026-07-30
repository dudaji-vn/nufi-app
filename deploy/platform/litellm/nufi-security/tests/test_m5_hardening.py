"""M5 산출물 D — 하드닝 체크리스트 검증 (부하·실패주입·감사 무결성).

설계: docs/design/gateway/m5-bench-hardening-spec.md §4 (CMP-78).
구현: CMP-99 (Engineer, 보안 상시승인 CMP-96).

실행: python3 tests/test_m5_hardening.py   (또는 pytest)
각 항목 → §4.1 부하 / §4.2 실패주입(fail-closed) / §4.3 감사 무결성.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import EgressGuard, AuditLogger, DetectionPipeline  # noqa: E402
from egress_audit.detectors.ner import KoreanNerDetector, _GazetteerBackend  # noqa: E402
from gateway.core import Gateway  # noqa: E402


# =========================================================== §4.1 부하 (Load)
def test_load_p95_and_no_errors():
    """지속 호출에서 p95 ≤ 150ms 유지 + 에러율 0 + RSS 평탄(객체 재사용)."""
    g = EgressGuard(ner_backend="gazetteer")
    prompt = ("고객 연락처 010-1234-5678 이메일 a@b.co.kr 확인 바랍니다. "
              "일반 업무 텍스트입니다. ") * 8  # ~512자
    for _ in range(20):
        g.inspect(prompt)
    lat, errors = [], 0
    for _ in range(500):
        t0 = time.perf_counter()
        try:
            g.inspect(prompt)
        except Exception:
            errors += 1
        lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()
    p95 = lat[int(len(lat) * 0.95)]
    assert errors == 0, f"에러율 0 위반: {errors}건"
    assert p95 <= 150, f"p95 {p95:.1f}ms > 150ms"


def test_load_length_cap_no_hang():
    """대용량 프롬프트(≥32k자) — 무한 지연 없이 한도 내 완료."""
    g = EgressGuard(ner_backend="gazetteer")
    big = "고객 김민수님 010-1234-5678 " * 2000  # ~5만자
    assert len(big) >= 32000
    t0 = time.perf_counter()
    res = g.inspect(big)
    dt = time.perf_counter() - t0
    assert dt < 5.0, f"대용량 입력 처리 {dt:.2f}s — 길이상한/타임아웃 정책 필요"
    assert res is not None


# =================================================== §4.2 실패주입 (Fail-closed)
def test_ner_backend_down_strong_pii_still_blocks():
    """NER 백엔드 다운 → gazetteer 폴백, 그래도 강한 PII(정규식+체크섬)는 항상 차단."""
    # transformers 강제 요청이 로드 실패하면 gazetteer 로 폴백되는지
    det = KoreanNerDetector(backend="auto")
    assert det.backend_name == "gazetteer"  # 에어갭: 폴백 동작 확인
    # NER 자체를 끈(=완전 다운) 상태에서도 강한 PII 는 잡힌다.
    g = EgressGuard(enable_ner=False)
    res = g.inspect("주민등록번호 900101-1234568 전화 010-1234-5678")
    types = {f.entity_type for f in res.findings}
    assert "KR_RRN" in types, "NER 다운 시에도 RRN(정규식+체크섬) 탐지 보장 위반"
    assert res.blocked, "강한 PII fail-safe 차단 위반"


def test_pipeline_exception_fail_closed():
    """탐지 파이프라인 예외 → 게이트웨이 fail-closed(403), public 미전송."""
    class _ExplodingGuard:
        policy = EgressGuard(enable_ner=False).policy
        ner_backend = "exploding"

        def inspect(self, text):
            raise RuntimeError("탐지기 내부 오류 주입")

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EGRESS_PRIVATE_DOWN"] = "1"  # public 경로 강제
        try:
            gw = Gateway(guard=_ExplodingGuard(), audit=AuditLogger(path=os.path.join(tmp, "a.jsonl")))
            resp = gw.process({"model": "nufi-default",
                               "messages": [{"role": "user", "content": "주민번호 900101-1234568"}]})
            logged = gw.audit.read_all()  # tmp 삭제 전에 읽어둔다
        finally:
            os.environ["EGRESS_PRIVATE_DOWN"] = "0"
        assert resp.status == 403, f"fail-closed 위반: status={resp.status}"
        assert resp.outcome == "blocked"
        assert logged and logged[-1]["outcome"] == "blocked"
        # 예외 경로도 원문 평문 미저장
        assert "900101-1234568" not in json.dumps(logged[-1], ensure_ascii=False)


def test_secret_detection_without_detect_secrets():
    """detect-secrets/presidio 미설치 → 내장 패턴/엔트로피로 강등 동작(SECRET 탐지 유지)."""
    g = EgressGuard(ner_backend="gazetteer")
    assert g.pipeline.secrets._ds is None  # 에어갭: 외부 스캐너 부재 확인
    res = g.inspect("배포 키 AKIAIOSFODNN7EXAMPLE 검토")
    assert any(f.entity_type == "SECRET" for f in res.findings)
    assert res.blocked


def test_regex_path_independent_of_ner():
    """정규식/체크섬 경로는 NER 유무와 독립(§4.2 강한 PII 항상 동작)."""
    on = EgressGuard(ner_backend="gazetteer").inspect("카드 4532-0111-2345-6788 결제")
    off = EgressGuard(enable_ner=False).inspect("카드 4532-0111-2345-6788 결제")
    assert any(f.entity_type == "CREDIT_CARD" for f in on.findings)
    assert any(f.entity_type == "CREDIT_CARD" for f in off.findings)
    assert on.blocked and off.blocked


# =================================================== §4.3 감사 무결성 (Audit integrity)
def _chain_logger(tmp):
    return AuditLogger(path=os.path.join(tmp, "chain.jsonl"), hash_chain=True)


def _log_some(al, n=5):
    for i in range(n):
        al.log(model="gpt-x", provider="openai", is_public=True,
               request_body={"text": f"req-{i}", "redacted": True}, outcome="forwarded")


def test_audit_hash_chain_valid():
    with tempfile.TemporaryDirectory() as tmp:
        al = _chain_logger(tmp)
        _log_some(al, 6)
        v = al.verify_chain()
        assert v["ok"] and v["count"] == 6, v


def test_audit_tamper_detected():
    """레코드 본문 변조 → verify_chain 탐지."""
    with tempfile.TemporaryDirectory() as tmp:
        al = _chain_logger(tmp)
        _log_some(al, 5)
        lines = al.path.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[2])
        rec["outcome"] = "blocked"  # 사후 변조
        lines[2] = json.dumps(rec, ensure_ascii=False)
        al.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        v = al.verify_chain()
        assert not v["ok"] and v["broken_seq"] == 2, v


def test_audit_deletion_detected():
    """행 삭제 → seq 불연속/prev_hash 불일치 탐지."""
    with tempfile.TemporaryDirectory() as tmp:
        al = _chain_logger(tmp)
        _log_some(al, 5)
        lines = al.path.read_text(encoding="utf-8").splitlines()
        del lines[2]  # 중간 행 삭제
        al.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        v = al.verify_chain()
        assert not v["ok"], v


def test_audit_clock_monotonic():
    """타임스탬프 역행 주입 → 시계 신뢰 위반 탐지."""
    with tempfile.TemporaryDirectory() as tmp:
        al = _chain_logger(tmp)
        _log_some(al, 4)
        lines = al.path.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[3])
        rec["epoch_ms"] = 1  # 과거로 역행
        # 해시도 함께 재계산해 본문변조가 아닌 '역행만' 시뮬레이션
        from egress_audit.audit import _record_hash
        rec["chain"]["hash"] = _record_hash(rec)
        lines[3] = json.dumps(rec, ensure_ascii=False)
        al.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        v = al.verify_chain()
        assert not v["ok"] and "역행" in v["error"], v


def test_audit_no_plaintext_pii_via_gateway():
    """게이트웨이 차단 경로의 감사 레코드에 원문 PII 평문 미저장(§4.3)."""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EGRESS_PRIVATE_DOWN"] = "1"
        try:
            gw = Gateway(audit=AuditLogger(path=os.path.join(tmp, "a.jsonl"), hash_chain=True),
                         ner_backend="gazetteer")
            gw.process({"model": "nufi-default",
                        "messages": [{"role": "user", "content": "주민번호 900101-1234568 입니다"}]})
        finally:
            os.environ["EGRESS_PRIVATE_DOWN"] = "0"
        blob = gw.audit.path.read_text(encoding="utf-8")
        assert "900101-1234568" not in blob, "감사 로그에 원문 RRN 평문 저장됨(§4.3 위반)"
        assert gw.audit.verify_chain()["ok"]


def test_audit_determinism():
    """동일 입력 → 동일 결정(정책 버전 고정 시 비결정성 0, §4.3 재현성)."""
    g = EgressGuard(ner_backend="gazetteer")
    p = "고객 김민수님 주민번호 900101-1234568 카드 4532-0111-2345-6788"
    a = g.inspect(p)
    b = g.inspect(p)
    assert a.summary == b.summary
    assert sorted((f.entity_type, f.start, f.end) for f in a.findings) == \
           sorted((f.entity_type, f.start, f.end) for f in b.findings)


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} M5 하드닝 테스트 PASS")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
