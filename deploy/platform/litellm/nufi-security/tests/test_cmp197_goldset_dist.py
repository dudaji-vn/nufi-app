"""CMP-197 I1 — 골드 평가셋 공개 배포 형태 검증.

완료기준: 결정적 재현 명령 1개로 평가셋 + 매니페스트 해시 재생성 가능,
커버리지·누수방지 슬라이스 검증 통과.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import goldset.generate as g

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "samples" / "gold"


@pytest.fixture(scope="module")
def built():
    rows = g.build()
    dev, test = g.stratify(rows)
    manifest = g.build_manifest(rows, dev, test)
    return rows, dev, test, manifest


def test_deterministic_reproduction(built):
    """동일 시드 재생성 → 동일 content_hash (결정적 재현)."""
    _, _, _, m1 = built
    rows2 = g.build()
    dev2, test2 = g.stratify(rows2)
    m2 = g.build_manifest(rows2, dev2, test2)
    assert m1["content_hash"] == m2["content_hash"]
    assert m1["content_hash"].startswith("sha256:")


def test_committed_manifest_matches(built):
    """커밋된 manifest.json 의 content_hash 가 재생성과 일치(드리프트 방지)."""
    _, _, _, fresh = built
    committed = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    assert committed["content_hash"] == fresh["content_hash"], (
        "samples/gold/manifest.json 이 시드 산출과 다름 — `python3 goldset/generate.py` 재실행 필요")


def test_committed_jsonl_bytes_match(built):
    """커밋된 dev/test.jsonl 바이트가 재생성 직렬화와 정확히 일치."""
    _, dev, test, _ = built
    for name, split in (("dev", dev), ("test", test)):
        expect = "".join(g._serialize_row(r) + "\n" for r in split)
        actual = (OUT / f"{name}.jsonl").read_text(encoding="utf-8")
        assert actual == expect, f"{name}.jsonl 바이트 불일치"


def test_all_synthetic(built):
    """실고객 데이터 0 — 모든 행 source == synth."""
    rows, _, _, m = built
    assert all(r["source"] == "synth" for r in rows)
    assert m["source"] == "synth"
    assert m["license"] == "CC0-1.0"


def test_stratified_split_disjoint(built):
    """dev/test 가 id 기준 서로소(test 누수 방지)이고 40/60 층화."""
    _, dev, test, m = built
    dev_ids = {r["id"] for r in dev}
    test_ids = {r["id"] for r in test}
    assert dev_ids.isdisjoint(test_ids)
    assert m["split"] == {"dev_pct": 0.4, "test_pct": 0.6, "stratified": True}
    assert m["dev_size"] + m["test_size"] == m["total"]


def test_must7_coverage(built):
    """Must 7종 각 dev/test 충분 표본."""
    _, _, _, m = built
    assert m["must_classes"] == g.MUST_CLASSES
    for c in g.MUST_CLASSES:
        cov = m["must_coverage"][c]
        assert cov["dev"] >= g.MUST_MIN_DEV, f"{c} dev={cov['dev']} < {g.MUST_MIN_DEV}"
        assert cov["test"] >= g.MUST_MIN_TEST, f"{c} test={cov['test']} < {g.MUST_MIN_TEST}"


def test_leak_prevention_person_unlisted(built):
    """누수방지 — KR_PERSON 미수록 성씨 비율 ≥ 0.5, 실제로 gazetteer 미수록."""
    rows, _, _, m = built
    assert m["person_unlisted_ratio"] >= 0.5
    # 라벨된 미수록 성씨가 실제로 gazetteer 사전에 없는지 구조 검증
    for sur in g.UNLISTED_SURNAMES:
        assert sur not in g.GAZ_SURNAMES, f"미수록 성씨 {sur} 가 gazetteer 에 있음(누수)"


def test_checksum_identifiers_valid(built):
    """체크섬 식별자(RRN/외국인등록/BRN/카드)가 유효 검증숫자 — 실제 탐지경로 통과."""
    from egress_audit import checksums as ck
    rows, _, _, _ = built
    by_cls = {}
    for r in rows:
        by_cls.setdefault(r["_cls"], []).append(r)

    def _val(cls):
        return [s[2] and r["prompt"][s[0]:s[1]] for r in by_cls[cls] for s in r["spans"]]

    rrn_cls = [c for c in by_cls if c in ("KR_RRN", "KR_FOREIGNER_REG")
               or c.startswith("zz_kr_rrn") or c.startswith("zz_kr_foreigner_reg")]
    for c in rrn_cls:
        for r in by_cls[c]:
            v = r["prompt"][r["spans"][0][0]:r["spans"][0][1]]
            assert ck.validate_rrn(v), f"RRN 체크섬 무효 ({c}): {v}"
    brn_cls = [c for c in by_cls if c in ("KR_BRN",) or c.startswith("zz_kr_brn")]
    for c in brn_cls:
        for r in by_cls[c]:
            v = r["prompt"][r["spans"][0][0]:r["spans"][0][1]]
            assert ck.validate_brn(v), f"BRN 체크섬 무효 ({c}): {v}"
    card_cls = [c for c in by_cls if c in ("CREDIT_CARD",) or c.startswith("zz_credit_card")]
    for c in card_cls:
        for r in by_cls[c]:
            v = r["prompt"][r["spans"][0][0]:r["spans"][0][1]]
            assert ck.validate_luhn(v.replace("-", "")), f"카드 Luhn 무효 ({c}): {v}"


def test_spans_exact(built):
    """모든 양성 행의 span 이 prompt 내 정확한 오프셋."""
    rows, _, _, _ = built
    for r in rows:
        for start, end, _t in r["spans"]:
            assert 0 <= start < end <= len(r["prompt"])


def test_verify_cli_passes():
    """공개 재현 검증 진입점 verify() 가 커밋본에 대해 통과(rc=0)."""
    assert g.verify() == 0


def test_no_scanner_firing_aws_patterns(built):
    """CMP-215 회귀 방지 — 산출 골드셋에 스캐너-발화 AWS 자격증명 패턴 0건(공식 예시키만)."""
    _, dev, test, _ = built
    viol = g.scan_pushblock(dev, test)
    assert viol == [], f"허용목록 외 AWS 패턴 검출(GH013 재발): {viol}"


def test_pushblock_guard_catches_random_aws():
    """CMP-215 가드 실효성 — 랜덤 고엔트로피 AWS 값 재유입 시 scan_pushblock 이 실제로 잡는다."""
    # make_secret 회귀(랜덤 AKIA/40자 시크릿 재유입)를 모사한 오염 행
    bad_id = [{"prompt": "배포 키 AKIA1234567890ABCDEF 검토", "expect": ["SECRET"],
               "spans": [], "source": "synth", "id": "x", "_cls": "SECRET"}]
    bad_secret = [{"prompt": "aws_secret_access_key=abcd1234ABCD5678efgh9012IJKL3456mnop7890 유출",
                   "expect": ["SECRET"], "spans": [], "source": "synth", "id": "y", "_cls": "SECRET"}]
    assert g.scan_pushblock(bad_id, []), "허용목록 외 AKIA 키를 놓침"
    assert g.scan_pushblock([], bad_secret), "허용목록 외 40자 시크릿을 놓침"
    # 공식 예시키는 허용목록이므로 위반 아님(recall 유지 · 스캐너 통과)
    ok = [{"prompt": "배포 키 AKIAIOSFODNN7EXAMPLE / "
                     "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
           "expect": ["SECRET"], "spans": [], "source": "synth", "id": "z", "_cls": "SECRET"}]
    assert g.scan_pushblock(ok, []) == []
