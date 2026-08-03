"""CMP-249 v0.4.2 게이트웨이 강건성 검증.

검증 항목:
  1. 탐지 타임아웃 → fail-closed (차단).
  2. 응답에 latency_ms 포함.
  3. 방어 파싱: 비정상 메시지(비-dict, content 누락, content 비-string) 처리.
  4. 프롬프트 크기 제한 (_MAX_PROMPT_BYTES) 초과 시 잘라서 처리.

실행: python3 tests/test_cmp249_resilience.py  (FAIL → exit 1)
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("EGRESS_NER_BACKEND", "gazetteer")

from egress_audit import AuditLogger  # noqa: E402
from gateway.core import (  # noqa: E402
    Gateway, GatewayResponse, extract_text,
    DetectionTimeoutError, _MAX_PROMPT_BYTES,
)

results: list[tuple[str, bool, str]] = []


def check(crit: str, ok: bool, detail: str = ""):
    results.append((crit, ok, detail))
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {crit}" + (f" — {detail}" if detail else ""))


def make_gateway(tmp):
    return Gateway(
        audit=AuditLogger(path=os.path.join(tmp, "audit.jsonl")),
        ner_backend="gazetteer",
    )


# --- 1. latency_ms 포함 ---
def test_latency_present():
    print("\n=== 1. latency_ms 포함 ===")
    with tempfile.TemporaryDirectory() as tmp:
        gw = make_gateway(tmp)
        body = {"model": "nufi-default",
                "messages": [{"role": "user", "content": "안녕"}]}
        resp = gw.process(body)
        check("private 경로 latency_ms ≥ 0",
              resp.latency_ms is not None and resp.latency_ms >= 0,
              f"latency_ms={resp.latency_ms}")

        os.environ["EGRESS_PRIVATE_DOWN"] = "1"
        try:
            resp2 = gw.process(body)
            check("public 경로(허용) latency_ms ≥ 0",
                  resp2.latency_ms is not None and resp2.latency_ms >= 0,
                  f"latency_ms={resp2.latency_ms}")
        finally:
            os.environ.pop("EGRESS_PRIVATE_DOWN", None)


# --- 2. 탐지 타임아웃 → fail-closed ---
def test_timeout_fail_closed():
    print("\n=== 2. 탐지 타임아웃 → fail-closed ===")
    with tempfile.TemporaryDirectory() as tmp:
        gw = make_gateway(tmp)
        os.environ["EGRESS_PRIVATE_DOWN"] = "1"
        try:
            # inspect 에서 DetectionTimeoutError 발생 시뮬레이션
            with patch.object(gw, "_inspect_with_timeout",
                              side_effect=DetectionTimeoutError("test timeout")):
                resp = gw.process({
                    "model": "nufi-default",
                    "messages": [{"role": "user", "content": "test"}],
                })
            check("타임아웃 시 403 차단",
                  resp.status == 403, f"status={resp.status}")
            check("타임아웃 시 outcome=blocked",
                  resp.outcome == "blocked", f"outcome={resp.outcome}")
            check("타임아웃 시 FAIL_CLOSED 엔티티",
                  "FAIL_CLOSED" in resp.blocked_entities,
                  f"entities={resp.blocked_entities}")
            check("타임아웃 시 latency_ms 포함",
                  resp.latency_ms is not None and resp.latency_ms >= 0,
                  f"latency_ms={resp.latency_ms}")
            err = resp.body.get("error", {})
            check("타임아웃 메시지에 '타임아웃' 포함",
                  "타임아웃" in err.get("message", ""),
                  f"message={err.get('message', '')}")
        finally:
            os.environ.pop("EGRESS_PRIVATE_DOWN", None)


# --- 3. 방어 파싱: 비정상 메시지 ---
def test_defensive_parsing():
    print("\n=== 3. 방어 파싱: 비정상 메시지 ===")

    # 비-dict 항목은 건너뜀
    text = extract_text(["not_a_dict", {"role": "user", "content": "hello"}])
    check("비-dict 항목 건너뜀", "hello" in text, f"text={text!r}")

    # content 가 None
    text2 = extract_text([{"role": "user", "content": None}])
    check("content=None 처리", text2 == "", f"text={text2!r}")

    # content 가 숫자
    text3 = extract_text([{"role": "user", "content": 42}])
    check("content=int 처리 (str 변환)", "42" in text3, f"text={text3!r}")

    # content 없음
    text4 = extract_text([{"role": "user"}])
    check("content 키 없음 처리", text4 == "", f"text={text4!r}")

    # 정상: multimodal 리스트
    text5 = extract_text([{"role": "user", "content": [
        {"type": "text", "text": "A"},
        {"type": "image"},
        {"type": "text", "text": "B"},
    ]}])
    check("multimodal content 리스트", text5 == "A\n\nB", f"text={text5!r}")


# --- 4. 프롬프트 크기 제한 ---
def test_prompt_size_limit():
    print("\n=== 4. 프롬프트 크기 제한 ===")
    # _MAX_PROMPT_BYTES 초과 텍스트
    huge = "가" * (_MAX_PROMPT_BYTES + 1000)
    text = extract_text([{"role": "user", "content": huge}])
    text_bytes = len(text.encode("utf-8"))
    # 잘려서 원문보다 짧아야 함
    check("큰 프롬프트가 잘림",
          text_bytes < len(huge.encode("utf-8")),
          f"original={len(huge.encode('utf-8'))} trimmed={text_bytes}")

    # 정상 크기는 그대로
    small = "hello world"
    text2 = extract_text([{"role": "user", "content": small}])
    check("작은 프롬프트 그대로", text2 == small, f"text={text2!r}")


# --- 5. 일반 예외도 fail-closed ---
def test_generic_exception_fail_closed():
    print("\n=== 5. 일반 예외 fail-closed ===")
    with tempfile.TemporaryDirectory() as tmp:
        gw = make_gateway(tmp)
        os.environ["EGRESS_PRIVATE_DOWN"] = "1"
        try:
            with patch.object(gw, "_inspect_with_timeout",
                              side_effect=RuntimeError("model crashed")):
                resp = gw.process({
                    "model": "nufi-default",
                    "messages": [{"role": "user", "content": "test"}],
                })
            check("RuntimeError 시 403", resp.status == 403, f"status={resp.status}")
            check("RuntimeError 시 latency_ms 포함",
                  resp.latency_ms is not None,
                  f"latency_ms={resp.latency_ms}")
        finally:
            os.environ.pop("EGRESS_PRIVATE_DOWN", None)


if __name__ == "__main__":
    print("CMP-249 v0.4.2 — 게이트웨이 강건성 검증")
    test_latency_present()
    test_timeout_fail_closed()
    test_defensive_parsing()
    test_prompt_size_limit()
    test_generic_exception_fail_closed()

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{'='*40}")
    print(f"결과: {passed}/{total} PASS")
    if passed < total:
        for c, ok, d in results:
            if not ok:
                print(f"  FAIL: {c} — {d}")
        sys.exit(1)
    print("모든 검증 통과.")
