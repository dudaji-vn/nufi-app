"""I4 가명화 품질 벤치마크 게이트 (CMP-200).

완료기준 검증: 가역/비가역 지표 + surrogate 충돌율 0 + 결정성 검증 통과.
- 하니스(scripts/bench_pseudonymize.py)의 측정 함수를 직접 호출해 불변식을 강제한다.
- 커밋된 리포트 자산(docs/reports/CMP-200-*.json)이 현행 측정과 일치하는지 대조한다.
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import bench_pseudonymize as B  # noqa: E402

REPORT = ROOT / "docs" / "reports" / "pseudonymize-quality.json"


def _corpus():
    rng = random.Random(B.SEED)
    return B.build_reversible_corpus(rng), B.build_strong_corpus(rng)


def test_roundtrip_exact_and_no_collision():
    rev_corpus, _ = _corpus()
    r = B.measure_reversible_roundtrip(rev_corpus)
    assert r["roundtrip_exact"] == 1.0, r["roundtrip_exact_n"]
    assert r["surrogate_collisions"] == 0
    assert r["delimiter_corpus_collision"] == 0
    assert r["tokens_minted"] > 0


def test_streaming_matches_nonstreaming_across_boundaries():
    rev_corpus, _ = _corpus()
    s = B.measure_streaming(rev_corpus)
    assert s["streaming_match"] == 1.0, s["streaming_match_n"]
    assert s["boundary_configs_tested"] > 0


def test_collision_rate_zero_at_scale():
    c = B.measure_collision_scale()
    assert c["collisions"] == 0
    assert c["collision_rate"] == 0.0
    assert c["distinct_originals"] == c["distinct_surrogates"] == c["n_minted"]
    assert c["same_original_stable"] is True


def test_reversible_determinism():
    rev_corpus, _ = _corpus()
    d = B.measure_determinism(rev_corpus)
    assert d["reversible_determinism"] is True


def test_strong_identifiers_stay_blocked_not_pseudonymized():
    _, strong = _corpus()
    b = B.measure_block_retention(strong)
    assert b["block_retention"] == 1.0, b["block_retention_n"]
    assert b["pseudonymize_leak"] == 0
    # 각 강한 식별자·비밀 유형 전수 차단.
    for t in B.STRONG_BLOCK:
        assert b["per_type"][t]["blocked"] == b["per_type"][t]["n"]


def test_irreversible_consistency_structure_and_non_restorable():
    ir = B.measure_irreversible()
    assert ir["irreversible_consistency"] == 1.0
    assert ir["irreversible_collisions"] == 0
    assert ir["irreversible_non_restorable"] is True
    assert ir["irreversible_structure_preserved"] == 1.0


def test_acceptance_pass():
    assert B.run_all()["acceptance_pass"] is True


def test_committed_report_matches_current_measurement():
    assert REPORT.exists(), f"측정 리포트 자산 누락: {REPORT}"
    committed = json.loads(REPORT.read_text(encoding="utf-8"))
    fresh = B.run_all()
    # latency 섹션은 환경 의존적이므로 비교에서 제외.
    committed_cmp = {k: v for k, v in committed.items() if k != "latency"}
    fresh_cmp = {k: v for k, v in fresh.items() if k != "latency"}
    # 결정적 하니스이므로 커밋본과 현행 측정이 완전 일치해야(리포트 최신성 게이트).
    assert committed_cmp == fresh_cmp, "커밋된 리포트가 현행 측정과 불일치 — 재생성 후 커밋 필요"
