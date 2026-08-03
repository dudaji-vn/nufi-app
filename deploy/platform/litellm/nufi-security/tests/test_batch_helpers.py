"""tests/test_batch_helpers.py — SDK batch_route / batch_inspect 테스트 (patch95)."""
from __future__ import annotations

from nufi import batch_route, batch_inspect, RoutingDecision


def test_batch_route_returns_list_of_decisions():
    """batch_route 는 텍스트 리스트를 받아 RoutingDecision 리스트를 반환한다."""
    texts = [
        "홍길동 주민번호 900101-1234567",  # PII → local
        "hello world no pii here",          # no PII → cloud
    ]
    decisions = batch_route(texts)
    assert len(decisions) == 2
    assert isinstance(decisions[0], RoutingDecision)
    assert isinstance(decisions[1], RoutingDecision)
    # First should be routed to local (PII detected)
    assert decisions[0].pii_detected is True
    assert decisions[0].routed_to_local is True
    # Second should go to cloud (no PII)
    assert decisions[1].pii_detected is False
    assert decisions[1].routed_to_local is False


def test_batch_inspect_returns_list_of_dicts():
    """batch_inspect 는 텍스트 리스트를 받아 inspect_text 결과 dict 리스트를 반환한다."""
    texts = [
        "홍길동 주민번호 900101-1234567",  # PII → blocked
        "hello world",                      # clean → not blocked
    ]
    results = batch_inspect(texts)
    assert len(results) == 2
    assert isinstance(results[0], dict)
    assert isinstance(results[1], dict)
    # First should be blocked (PII found)
    assert results[0]["blocked"] is True
    # Second should not be blocked
    assert results[1]["blocked"] is False
