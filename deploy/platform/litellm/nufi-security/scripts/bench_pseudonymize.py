"""I4 — 가명화 품질 벤치마크 하니스 (§6 가명화 품질 지표 산출 표면).

설계 근거: docs/design/gateway/m3-reversible-pseudonymization-spec.md §2·§4.
평가 대상 표면: egress_audit/surrogate.py (가역) + egress_audit/pseudonymize.py (비가역)
             + config/presets/pseudonymize-roundtrip.yaml (가역/차단 정책 재사용).

측정 축
-------
가역(reversible, surrogate.py):
  - 원복 정확도(roundtrip): pre_call 가명화 → post_call 원복이 원문과 바이트 일치하는가.
  - 스트리밍 경계: surrogate 가 청크 경계로 쪼개져도(1자 청크 등 적대적 경계) 원복이
    비스트리밍 원복과 동일한가.
  - surrogate 충돌율: 서로 다른 원본이 같은 surrogate 로 발급되는 충돌 = 0 이어야 함.
    + 불투명 델리미터(⟦⟧)가 실제 코퍼스 원문과 충돌하지 않는지(0).
  - 결정성: 같은 (type, original) → 같은 surrogate(세션 내). 동일 입력 순서 재실행 →
    동일 surrogate 열(불변).
비가역(irreversible, pseudonymize.py):
  - 원복불가: HMAC 일방향 토큰은 매핑/역함수 없음(원문 부분문자열 미포함).
  - 구조보존: mask() 는 구분자·길이 구조를 보존(alnum 만 가림).
  - 동일값 일관 치환: pseudo_token 은 같은 값 → 같은 토큰(참조 무결성), 서로 다른 값
    충돌 = 0.
차단 유지(강한 식별자·비밀):
  - KR_RRN/외국인등록/여권/면허/카드/계좌/SECRET 은 가역 프리셋에서도 차단되어
    가명화로도 송신되지 않는가(blocked=True, pseudonymized=0).

원칙: 실고객 데이터 0(전량 합성, goldset 생성기 재사용) · 외부 호출 0 · 결정적(고정 시드).

실행:
  python3 scripts/bench_pseudonymize.py                      # 리포트 stdout
  python3 scripts/bench_pseudonymize.py --json-out docs/reports/pseudonymize-quality.json
종료코드: 기계식 불변식(충돌 0 · 결정성 · 원복 정확 · 차단 유지) 미달 시 1, 아니면 0.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import MappingVault, ReversibleEgress  # noqa: E402
from egress_audit.surrogate import (  # noqa: E402
    LB, RB, REVERSIBLE_ENTITIES, SurrogateMinter, deanonymize,
)
from egress_audit.pseudonymize import mask, pseudo_token, redact  # noqa: E402
import goldset.generate as G  # noqa: E402

SEED = 20260630

# 강한 식별자·비밀: 가역 프리셋에서도 차단 유지(가명화로도 송신 금지) 확인 대상.
STRONG_BLOCK = ["KR_RRN", "KR_FOREIGNER_REG", "KR_PASSPORT", "KR_DRIVER_LICENSE",
                "CREDIT_CARD", "KR_ACCOUNT", "SECRET"]

# 기계식 불변식 목표(모델 정확도 목표가 아니라 메커니즘 정확성 게이트).
TARGETS = {
    "roundtrip_exact": 1.0,
    "streaming_match": 1.0,
    "surrogate_collision_rate": 0.0,
    "delimiter_corpus_collision": 0,
    "reversible_determinism": True,
    "block_retention": 1.0,
    "pseudonymize_leak": 0,
    "irreversible_consistency": 1.0,
    "irreversible_collision_rate": 0.0,
    "irreversible_structure_preserved": 1.0,
    "irreversible_non_restorable": True,
}


# --------------------------------------------------------------------------- 코퍼스(합성·결정적)
def _person(rng):
    return rng.choice(G.LISTED_SURNAMES) + rng.choice(G.GIVEN)


def build_reversible_corpus(rng):
    """가역 대상만 담은 합성 프롬프트(gazetteer 백엔드로 탐지 가능한 값). 다중-엔티티 포함."""
    rows = []
    gens = {
        "KR_PHONE": (lambda: G.make_phone(rng), "연락처 {v} 로 안내 문자 보내주세요."),
        "EMAIL": (lambda: G.make_email(rng), "회신은 {v} 메일로 부탁드립니다."),
        "KR_BRN": (lambda: G.make_brn(rng), "사업자등록번호 {v} 세금계산서 발행 요청."),
        "KR_PERSON": (lambda: _person(rng), "고객 {v}님의 계정 본인확인을 진행해 주세요."),
        "KR_LOCATION": (lambda: rng.choice(G.GAZ_LOCATIONS), "이번 워크숍은 {v}에서 진행됩니다."),
    }
    for etype, (gen, tmpl) in gens.items():
        for _ in range(12):
            rows.append({"prompt": tmpl.format(v=gen()), "targets": [etype]})
    # 다중-엔티티(동일 프롬프트 내 여러 가역 토큰 — 오프셋/원복 정확도 스트레스)
    for _ in range(16):
        name, phone, email = _person(rng), G.make_phone(rng), G.make_email(rng)
        rows.append({
            "prompt": f"담당자 {name}님 연락처 {phone}, 회신 메일 {email} 로 견적 회신 바랍니다.",
            "targets": ["KR_PERSON", "KR_PHONE", "EMAIL"]})
    return rows


def build_strong_corpus(rng):
    """강한 식별자·비밀 프롬프트(차단 유지 검증)."""
    gens = {
        "KR_RRN": (lambda: G.make_rrn(rng, rng.randint(1, 4)), "주민등록번호 {v} 본인확인 처리 바랍니다."),
        "KR_FOREIGNER_REG": (lambda: G.make_rrn(rng, rng.randint(5, 8)), "외국인등록번호 {v} 비자 연장 건입니다."),
        "KR_PASSPORT": (lambda: G.make_passport(rng), "여권번호 {v} 항공권 발권 부탁드립니다."),
        "KR_DRIVER_LICENSE": (lambda: G.make_license(rng), "운전면허번호 {v} 렌터카 예약 진행."),
        "CREDIT_CARD": (lambda: G.make_card(rng), "결제 카드번호 {v} 승인 요청합니다."),
        "KR_ACCOUNT": (lambda: G.make_account(rng), "환불 계좌 {v} 로 입금 부탁드립니다."),
        "SECRET": (lambda: G.make_secret(rng)[0], "배포 키 {v} 회수 필요."),
    }
    rows = []
    for etype, (gen, tmpl) in gens.items():
        for _ in range(8):
            rows.append({"prompt": tmpl.format(v=gen()), "targets": [etype]})
    return rows


# --------------------------------------------------------------------------- 가역 측정
def measure_reversible_roundtrip(corpus):
    """end-to-end 원복 정확도 + surrogate 충돌 + 델리미터-코퍼스 충돌."""
    rev = ReversibleEgress()
    exact = total = tokens = 0
    per_type = {}
    delim_corpus_collision = 0
    all_surrogates = []            # (session, surrogate, original) — 충돌 검사용
    for i, row in enumerate(corpus):
        prompt = row["prompt"]
        # 불투명 델리미터가 실제 원문에 이미 존재하면 충돌(0 이어야 함).
        if LB in prompt or RB in prompt:
            delim_corpus_collision += 1
        sid = f"rt-{i}"
        res = rev.pseudonymize(prompt, sid)
        if res.blocked:
            continue  # 가역 코퍼스는 차단 없음이 전제; 방어적으로 스킵
        total += 1
        tokens += res.pseudonymized
        restored, _ = rev.deanonymize(res.transformed_text, sid)
        ok = restored == prompt
        if ok:
            exact += 1
        for t in row["targets"]:
            d = per_type.setdefault(t, {"ok": 0, "n": 0})
            d["n"] += 1
            if ok:
                d["ok"] += 1
        # 발급된 surrogate 수집(세션 스코프)
        for f in res.findings:
            if f.entity_type in REVERSIBLE_ENTITIES:
                sur = rev.vault.find_surrogate(sid, f.entity_type, f.text)
                if sur:
                    all_surrogates.append((sid, sur, f.entity_type, f.text))
        rev.end_session(sid)
    # 세션 내 충돌: 같은 (session, surrogate) 가 서로 다른 원본을 가리키면 충돌.
    seen = {}
    collisions = 0
    for sid, sur, etype, original in all_surrogates:
        key = (sid, sur)
        if key in seen and seen[key] != (etype, original):
            collisions += 1
        seen[key] = (etype, original)
    return {
        "n_prompts": total,
        "tokens_minted": tokens,
        "roundtrip_exact": round(exact / total, 4) if total else 0.0,
        "roundtrip_exact_n": f"{exact}/{total}",
        "per_type": {t: {"recall": round(d["ok"] / d["n"], 4), "ok": d["ok"], "n": d["n"]}
                     for t, d in sorted(per_type.items())},
        "surrogate_collisions": collisions,
        "surrogate_collision_rate": round(collisions / len(all_surrogates), 4) if all_surrogates else 0.0,
        "delimiter_corpus_collision": delim_corpus_collision,
    }


def measure_streaming(corpus):
    """스트리밍 원복이 비스트리밍 원복과 일치하는가(적대적 청크 경계 포함)."""
    rev = ReversibleEgress()
    match = total = 0
    boundary_configs = 0
    for i, row in enumerate(corpus):
        sid = f"st-{i}"
        res = rev.pseudonymize(row["prompt"], sid)
        if res.blocked or res.pseudonymized == 0:
            continue
        echo = res.transformed_text  # 모델이 surrogate 를 그대로 돌려준다고 가정(가장 흔한 원복 경로)
        nonstream, _ = deanonymize(echo, rev.vault, sid)
        total += 1
        row_ok = True
        # 적대적 경계: 1자 청크 + 여러 고정 청크 크기 → 모든 경계에서 동일해야.
        for size in (1, 2, 3, 5, 7, len(echo)):
            if size < 1:
                continue
            boundary_configs += 1
            r = rev.stream_restorer(sid)
            out = "".join(r.feed(echo[j:j + size]) for j in range(0, len(echo), size))
            out += r.flush()
            if out != nonstream:
                row_ok = False
        if row_ok:
            match += 1
        rev.end_session(sid)
    return {
        "n_prompts": total,
        "boundary_configs_tested": boundary_configs,
        "streaming_match": round(match / total, 4) if total else 0.0,
        "streaming_match_n": f"{match}/{total}",
    }


def measure_collision_scale():
    """대규모 결정성·충돌 스트레스: 단일 세션에 다수 원본 발급 → surrogate 전수 유일."""
    vault = MappingVault()
    sid = "collide"
    minter = SurrogateMinter(vault, sid)
    rng = random.Random(SEED + 1)
    originals = []
    for et in REVERSIBLE_ENTITIES:
        for _ in range(200):
            originals.append((et, f"{et}-{rng.randint(0, 10**9)}-{rng.randint(0, 10**9)}"))
    surrogates = [minter.mint(et, v) for et, v in originals]
    # 서로 다른 원본 → 서로 다른 surrogate(충돌 0). 같은 원본 재요청 → 동일(결정성).
    by_original = {}
    for (et, v), sur in zip(originals, surrogates):
        by_original.setdefault((et, v), set()).add(sur)
    determinism_ok = all(len(s) == 1 for s in by_original.values())
    distinct_originals = len(by_original)
    distinct_surrogates = len(set(surrogates))
    collisions = distinct_originals - distinct_surrogates
    # 재발급 결정성: 같은 원본 다시 mint → 동일 surrogate.
    redetermined = all(minter.mint(et, v) == sur
                       for (et, v), sur in zip(originals, surrogates))
    return {
        "n_minted": len(surrogates),
        "distinct_originals": distinct_originals,
        "distinct_surrogates": distinct_surrogates,
        "collisions": collisions,
        "collision_rate": round(collisions / len(surrogates), 6) if surrogates else 0.0,
        "same_original_stable": determinism_ok and redetermined,
    }


def measure_determinism(corpus):
    """동일 입력 순서 재실행 → 동일 surrogate 열(가시 토큰 불변)."""
    def run():
        rev = ReversibleEgress(vault=MappingVault())
        out = []
        for i, row in enumerate(corpus):
            res = rev.pseudonymize(row["prompt"], "det")  # 고정 세션 → 카운터 결정적
            out.append(res.transformed_text)
        return out
    a, b = run(), run()
    identical = a == b
    return {"reversible_determinism": identical,
            "n_prompts": len(corpus),
            "sample": a[0] if a else ""}


def measure_block_retention(corpus):
    """강한 식별자·비밀은 가역 프리셋에서도 차단·미가명화(송신 금지)."""
    rev = ReversibleEgress()
    blocked = total = 0
    leak = 0
    per_type = {}
    for i, row in enumerate(corpus):
        res = rev.pseudonymize(row["prompt"], f"blk-{i}")
        total += 1
        t = row["targets"][0]
        d = per_type.setdefault(t, {"blocked": 0, "n": 0})
        d["n"] += 1
        if res.blocked:
            blocked += 1
            d["blocked"] += 1
        if res.pseudonymized > 0:
            leak += 1  # 강한 식별자가 가명화로 송신되면 누출
        rev.end_session(f"blk-{i}")
    return {
        "n_prompts": total,
        "block_retention": round(blocked / total, 4) if total else 0.0,
        "block_retention_n": f"{blocked}/{total}",
        "pseudonymize_leak": leak,
        "per_type": {t: {"blocked": d["blocked"], "n": d["n"]} for t, d in sorted(per_type.items())},
    }


# --------------------------------------------------------------------------- 비가역 측정
# mask keep_tail 규약: 구조보존 확인용 대표 포맷.
_MASK_SAMPLES = [
    ("KR_PHONE", "010-1234-5678", 4),
    ("KR_BRN", "123-45-67890", 0),
    ("KR_ACCOUNT", "110-234-567890", 4),
    ("CREDIT_CARD", "4111-1111-1111-1111", 4),
    ("EMAIL", "hong.gildong@company.co.kr", 0),
]


def measure_irreversible():
    rng = random.Random(SEED + 2)
    # 코퍼스 값(비가역 토큰화 대상).
    values = []
    for _ in range(120):
        values.append(("KR_PERSON", _person(rng)))
        values.append(("KR_PHONE", G.make_phone(rng)))
        values.append(("EMAIL", G.make_email(rng)))
    # 동일값 일관 치환(결정성): 같은 값 → 같은 토큰(두 번 호출).
    consistent = sum(1 for et, v in values
                     if pseudo_token(et, v) == pseudo_token(et, v))
    consistency = round(consistent / len(values), 4)
    # 충돌: 서로 다른 (type,value) → 서로 다른 토큰.
    tokens = [pseudo_token(et, v) for et, v in values]
    distinct_inputs = len(set(values))
    distinct_tokens = len(set(tokens))
    collisions = distinct_inputs - distinct_tokens
    # 원복불가: 토큰에 원문 부분문자열 미포함 + 역매핑 없음(HMAC 일방향).
    non_restorable = all(v not in pseudo_token(et, v) for et, v in values)
    # 구조보존: mask 는 길이·구분자 위치 보존, alnum 만 '*'.
    struct_ok = 0
    struct_detail = {}
    for et, sample, keep in _MASK_SAMPLES:
        m = mask(sample, keep_tail=keep)
        same_len = len(m) == len(sample)
        seps_ok = all((m[k] == sample[k]) for k, c in enumerate(sample) if not c.isalnum())
        alnum_masked = sum(1 for k, c in enumerate(sample)
                           if c.isalnum() and m[k] == "*")
        expect_masked = sum(1 for c in sample if c.isalnum()) - keep
        ok = same_len and seps_ok and alnum_masked == expect_masked
        struct_ok += 1 if ok else 0
        struct_detail[et] = {"orig": sample, "masked": m, "ok": ok}
    return {
        "n_values": len(values),
        "irreversible_consistency": consistency,
        "distinct_inputs": distinct_inputs,
        "distinct_tokens": distinct_tokens,
        "irreversible_collisions": collisions,
        "irreversible_collision_rate": round(collisions / len(tokens), 6) if tokens else 0.0,
        "irreversible_non_restorable": non_restorable,
        "irreversible_structure_preserved": round(struct_ok / len(_MASK_SAMPLES), 4),
        "structure_samples": struct_detail,
        "token_sample": {"KR_PERSON": pseudo_token("KR_PERSON", "김민수"),
                         "redact": redact("KR_PHONE")},
    }


# --------------------------------------------------------------------------- 집계
def run_all():
    rng = random.Random(SEED)
    rev_corpus = build_reversible_corpus(rng)
    strong_corpus = build_strong_corpus(rng)

    roundtrip = measure_reversible_roundtrip(rev_corpus)
    streaming = measure_streaming(rev_corpus)
    collision = measure_collision_scale()
    determinism = measure_determinism(rev_corpus)
    block = measure_block_retention(strong_corpus)
    irreversible = measure_irreversible()

    scores = {
        "reversible_targets": list(REVERSIBLE_ENTITIES),
        "strong_block_targets": STRONG_BLOCK,
        "roundtrip": roundtrip,
        "streaming": streaming,
        "collision_scale": collision,
        "determinism": determinism,
        "block_retention": block,
        "irreversible": irreversible,
    }

    # 종합 충돌 = end-to-end + 대규모 스트레스 합산.
    combined_collisions = roundtrip["surrogate_collisions"] + collision["collisions"]

    acceptance = {
        "roundtrip_exact==1.0": roundtrip["roundtrip_exact"] >= 1.0,
        "streaming_match==1.0": streaming["streaming_match"] >= 1.0,
        "surrogate_collision_rate==0": combined_collisions == 0,
        "delimiter_corpus_collision==0": roundtrip["delimiter_corpus_collision"] == 0,
        "reversible_determinism": bool(determinism["reversible_determinism"]
                                       and collision["same_original_stable"]),
        "block_retention==1.0": block["block_retention"] >= 1.0,
        "pseudonymize_leak==0": block["pseudonymize_leak"] == 0,
        "irreversible_consistency==1.0": irreversible["irreversible_consistency"] >= 1.0,
        "irreversible_collision_rate==0": irreversible["irreversible_collisions"] == 0,
        "irreversible_structure_preserved==1.0": irreversible["irreversible_structure_preserved"] >= 1.0,
        "irreversible_non_restorable": bool(irreversible["irreversible_non_restorable"]),
    }
    report = {
        "benchmark": "pseudonymize-quality",
        "surface": ["egress_audit/surrogate.py", "egress_audit/pseudonymize.py",
                    "config/presets/pseudonymize-roundtrip.yaml"],
        "seed": SEED,
        "source": "synth",
        "targets": TARGETS,
        "scores": scores,
        "combined_surrogate_collisions": combined_collisions,
        "acceptance": acceptance,
        "acceptance_pass": all(acceptance.values()),
    }
    return report


# --------------------------------------------------------------------------- 레이턴시 측정
def measure_latency(sizes=(256, 1024, 4096, 16384), repeats=20):
    """입력 크기별 가명화 latency 측정 — p50/p95/p99."""
    import statistics
    rng = random.Random(SEED + 99)
    # PII가 포함된 텍스트 생성 (크기별)
    base_phrases = [
        "고객 {name}님 연락처 {phone} 으로 안내드립니다. ",
        "담당자 {name} 이메일 {email} 로 회신 바랍니다. ",
        "사업자등록번호 {brn} 세금계산서 발행 요청합니다. ",
    ]
    results = {}
    for sz in sizes:
        # 합성 텍스트 구성
        text = ""
        while len(text) < sz:
            phrase = rng.choice(base_phrases).format(
                name=_person(rng),
                phone=G.make_phone(rng),
                email=G.make_email(rng),
                brn=G.make_brn(rng),
            )
            text += phrase
        text = text[:sz]
        timings = []
        for r in range(repeats):
            rev = ReversibleEgress()
            sid = f"lat-{sz}-{r}"
            import time
            t0 = time.perf_counter()
            res = rev.pseudonymize(text, sid)
            if not res.blocked:
                rev.deanonymize(res.transformed_text, sid)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            rev.end_session(sid)
        timings.sort()
        n = len(timings)
        results[str(sz)] = {
            "input_chars": sz,
            "repeats": repeats,
            "p50_ms": round(timings[n // 2], 2),
            "p95_ms": round(timings[int(n * 0.95)], 2),
            "p99_ms": round(timings[int(n * 0.99)], 2),
            "min_ms": round(timings[0], 2),
            "max_ms": round(timings[-1], 2),
        }
    # CI 게이트: p95 <= 200ms (16K자)
    gate_key = str(max(sizes))
    gate_pass = results[gate_key]["p95_ms"] <= 200.0
    return {"sizes": results, "ci_gate_16k_p95_le_200ms": gate_pass}


def main():
    ap = argparse.ArgumentParser(description="I4 가명화 품질 벤치마크")
    ap.add_argument("--json-out")
    ap.add_argument("--latency", action="store_true",
                    help="레이턴시 벤치마크 모드 (입력 크기별 p50/p95/p99)")
    args = ap.parse_args()
    report = run_all()

    if args.latency:
        latency = measure_latency()
        report["latency"] = latency
        # 레이턴시 결과 요약 출력
        print("=== Pseudonymize Latency Benchmark ===")
        for sz, data in latency["sizes"].items():
            print(f"  {sz:>5} chars: p50={data['p50_ms']:.1f}ms  "
                  f"p95={data['p95_ms']:.1f}ms  p99={data['p99_ms']:.1f}ms")
        gate = "PASS" if latency["ci_gate_16k_p95_le_200ms"] else "FAIL"
        print(f"  CI gate (16K p95 <= 200ms): {gate}")
        print()

    out = json.dumps(report, ensure_ascii=False, indent=2)
    print(out)
    if args.json_out:
        Path(args.json_out).write_text(out + "\n", encoding="utf-8")

    ok = report["acceptance_pass"]
    if args.latency and not report.get("latency", {}).get("ci_gate_16k_p95_le_200ms", True):
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
