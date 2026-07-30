"""단위 테스트 (pytest 또는 `python3 tests/test_unit.py`).

체크섬·탐지기·정책·라우터의 핵심 불변식을 검증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import checksums as ck
from egress_audit import EgressGuard
from egress_audit.detectors.secrets import shannon_entropy
from gateway.router import Router


def test_rrn_checksum():
    assert ck.validate_rrn("900101-1234568")
    assert ck.validate_rrn("0503023456789")
    assert not ck.validate_rrn("900101-1234560")   # 잘못된 검증숫자
    assert not ck.validate_rrn("123")


def test_brn_checksum():
    assert ck.validate_brn("123-45-67891")
    assert not ck.validate_brn("123-45-67890")


def test_luhn():
    assert ck.validate_luhn("4532-0111-2345-6788")
    assert not ck.validate_luhn("4532-0111-2345-6789")


def test_entropy_monotonic():
    assert shannon_entropy("aaaaaaaa") < shannon_entropy("aZ3$kP9q")


def test_pii_block_and_pseudonymize():
    g = EgressGuard(ner_backend="gazetteer")
    res = g.inspect("주민번호 900101-1234568 전화 010-1234-5678")
    types = {f.entity_type for f in res.findings}
    assert "KR_RRN" in types and "KR_PHONE" in types
    assert res.blocked                                   # RRN → block
    assert "900101-1234568" not in res.transformed_text  # 본문에서 제거/치환


def test_kr_account_structural_fp_excluded():
    """CMP-103: KR_ACCOUNT 구조적/문맥 오탐 제외 — ISBN·운송장은 미탐지, 실계좌는 유지.

    가드레일: 맨/계좌-문맥 계좌번호는 그대로 탐지(강한PII recall 비훼손).
    """
    g = EgressGuard(ner_backend="gazetteer")

    def acct(text):
        return any(f.entity_type == "KR_ACCOUNT" for f in g.inspect(text).findings)

    # 비계좌(known FP) — 제외되어야 함
    assert not acct("운송장 1234-5678-9012 배송 조회.")          # 운송장 문맥
    assert not acct("도서 ISBN 978-89-12345-67-8 주문.")         # ISBN-13 구조+문맥
    assert not acct("택배 송장번호 9876-5432-1098 확인.")        # 송장/택배 문맥

    # 실계좌 — 4-4-4 가 운송장과 구조 동일해도 계좌-문맥/맨번호는 유지되어야 함
    assert acct("환불 계좌 7669-3587-2362 로 입금 부탁드립니다.")   # 4-4-4 실계좌
    assert acct("환불 계좌 283741-77-410126 로 입금 부탁드립니다.")  # 6-2-6 실계좌
    assert acct("입금처 065-047987-13594 입니다.")               # 맨 계좌(인접 키워드 無)


def test_secret_detection():
    g = EgressGuard(ner_backend="gazetteer")
    res = g.inspect("키 AKIAIOSFODNN7EXAMPLE 노출")
    assert any(f.entity_type == "SECRET" for f in res.findings)
    assert res.blocked


def test_benign_not_blocked():
    g = EgressGuard(ner_backend="gazetteer")
    assert not g.inspect("오늘 회의 안건을 정리해줘").blocked


def test_m4_marking_and_keyword_josa():
    g = EgressGuard(ner_backend="gazetteer")
    res = g.inspect("프로젝트 오로라는 극비입니다")   # 조사 결합 + 표식
    ents = {f.entity_type for f in res.findings}
    assert "CONF_KEYWORD" in ents and "CONF_MARKING_RESTRICTED" in ents
    assert res.blocked
    # 매치 원문은 결정 로그에 비기록
    conf = [f for f in res.decision.findings if f.get("source") in {"keyword", "marking"}]
    assert conf and all(not f.get("text") for f in conf)
    assert all("class" in f and "match_meta" in f for f in conf)


def test_m4_allowlist_no_false_positive():
    g = EgressGuard(ner_backend="gazetteer")
    res = g.inspect("오로라 공주 동화 줄거리 알려줘")
    assert not any(f.source in {"keyword", "marking"} for f in res.findings)
    assert not res.blocked


def test_m4_edm_struct_kofn():
    g = EgressGuard(ner_backend="gazetteer")
    strong = g.inspect("고객 홍길동 연락처 010-2222-3456 등급 VIP")
    assert any(f.entity_type == "CONF_EDM_STRUCT_STRONG" for f in strong.findings)
    assert strong.blocked
    single = g.inspect("성씨가 김인 고객")   # stop_value 단독 → 무시
    assert not any(f.source == "edm_struct" for f in single.findings)


def test_m4_edm_index_no_plaintext():
    idx = ROOT / "config" / "edm" / "index.json"
    raw = idx.read_text(encoding="utf-8")
    for plain in ("홍길동", "010-2222-3456", "사천이백만원"):
        assert plain not in raw   # 원문 비저장(NFR1)


def test_route_pii_detected_routes_local():
    """CMP-272: nufi.route() — PII 텍스트는 로컬로 라우팅."""
    from nufi import route, RoutingDecision
    decision = route("고객 홍길동 주민번호 900101-1234568")
    assert isinstance(decision, RoutingDecision)
    assert decision.pii_detected
    assert decision.routed_to_local


def test_route_clean_text_routes_cloud():
    """CMP-272: nufi.route() — PII 없는 텍스트는 클라우드 허용."""
    from nufi import route
    decision = route("오늘 날씨가 맑습니다.")
    assert not decision.pii_detected
    assert not decision.routed_to_local


def test_router_private_default_public_fallback():
    r = Router()
    assert not r.resolve("nufi-default").is_public
    assert r.resolve("nufi-default", force_fallback=True).is_public


# --------------------------------------------------------------------------- #
# CLI `route` subcommand tests (CMP-270)
# --------------------------------------------------------------------------- #

def test_cli_route_pii_detected_routes_local():
    """CLI route: PII 포함 텍스트는 로컬 모델 라우팅으로 판정."""
    import io
    from contextlib import redirect_stdout
    from enforcement.cli import main as cli_main

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli_main(["route", "--text", "김민수님 계좌 110-123-456789", "--json"])
    assert rc == 0
    import json as _json
    out = _json.loads(buf.getvalue())
    assert out["pii_detected"] is True
    assert out["routed_to_local"] is True


def test_cli_route_clean_text_allows_cloud():
    """CLI route: PII 없는 텍스트는 클라우드 허용."""
    import io
    from contextlib import redirect_stdout
    from enforcement.cli import main as cli_main

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli_main(["route", "--text", "오늘 날씨 어때", "--json"])
    assert rc == 0
    import json as _json
    out = _json.loads(buf.getvalue())
    assert out["pii_detected"] is False
    assert out["routed_to_local"] is False


def test_cli_route_json_output_structure():
    """CLI route --json: 출력에 필수 필드가 모두 존재."""
    import io
    from contextlib import redirect_stdout
    from enforcement.cli import main as cli_main

    buf = io.StringIO()
    with redirect_stdout(buf):
        cli_main(["route", "--text", "테스트 입력", "--json"])
    import json as _json
    out = _json.loads(buf.getvalue())
    required_keys = {"target_model", "reason", "pii_detected", "routed_to_local",
                     "finding_count", "entity_types", "latency_ms"}
    assert required_keys.issubset(out.keys())


def test_cli_route_model_override():
    """CLI route --local-model/--cloud-model 오버라이드가 결과에 반영."""
    import io
    from contextlib import redirect_stdout
    from enforcement.cli import main as cli_main

    buf = io.StringIO()
    with redirect_stdout(buf):
        cli_main(["route", "--text", "오늘 날씨 어때",
                  "--local-model", "my-local", "--cloud-model", "my-cloud", "--json"])
    import json as _json
    out = _json.loads(buf.getvalue())
    # clean text → cloud model should be the overridden name
    assert out["target_model"] == "my-cloud"


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
    print(f"\n{len(fns)-failed}/{len(fns)} unit tests PASS")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
