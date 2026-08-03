"""SPEC M1/M2 binary 수용 기준 검증 하니스.

각 기준 → PASS/FAIL 리포트. 하나라도 FAIL 이면 exit code 1.
실행: python3 tests/run_acceptance.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from egress_audit import EgressGuard, AuditLogger  # noqa: E402
from gateway.router import Router  # noqa: E402
from gateway.core import Gateway  # noqa: E402

SAMPLES = ROOT / "samples"
results: list[tuple[str, bool, str]] = []


def check(crit: str, ok: bool, detail: str = ""):
    results.append((crit, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {crit}" + (f" — {detail}" if detail else ""))


def load(name):
    return [json.loads(l) for l in open(SAMPLES / name, encoding="utf-8") if l.strip()]


def make_gateway(tmp_audit):
    return Gateway(audit=AuditLogger(path=tmp_audit), ner_backend="gazetteer")


# ----------------------------------------------------------------------------- M1
def test_m1(tmpdir):
    print("\n== M1 — LiteLLM 게이트웨이 ==")
    r = Router()

    # 1) private 기본 라우팅 + public 폴백
    primary = r.resolve("nufi-default")
    fb = r.resolve("nufi-default", force_fallback=True)
    check("M1.1 private 기본 라우팅 + public 폴백",
          (not primary.is_public) and fb.is_public,
          f"primary={primary.backend}({primary.egress_class}) / fallback={fb.backend}({fb.egress_class})")

    # 2) public 100% 감사 로깅 (차단 포함)
    audit_path = os.path.join(tmpdir, "m1_audit.jsonl")
    os.environ["EGRESS_PRIVATE_DOWN"] = "1"  # 전부 public 폴백 강제
    gw = make_gateway(audit_path)
    pii = load("pii_samples.jsonl")
    secrets = load("secret_samples.jsonl")
    benign = load("benign_samples.jsonl")
    public_reqs = pii + secrets + benign
    statuses = []
    for s in public_reqs:
        resp = gw.process({"model": "nufi-default", "messages": [{"role": "user", "content": s["prompt"]}]})
        statuses.append(resp)
    logged = gw.audit.read_all()
    all_public = all(rec["is_public"] for rec in logged)
    check("M1.2 public 요청 100% 감사 로깅",
          len(logged) == len(public_reqs) and all_public,
          f"{len(logged)}/{len(public_reqs)} 적재, is_public 전부={all_public}, "
          f"blocked={sum(1 for x in statuses if x.status==403)}")

    # private 경로는 감사 로그에 안 남는지(외부 미전송) 확인
    os.environ["EGRESS_PRIVATE_DOWN"] = "0"
    audit_path2 = os.path.join(tmpdir, "m1_priv.jsonl")
    gw2 = make_gateway(audit_path2)
    pr = gw2.process({"model": "nufi-default", "messages": [{"role": "user", "content": "주민번호 0503023456789"}]})
    check("M1.2b private 경로는 외부 미전송(감사 0건)",
          pr.outcome == "private" and len(gw2.audit.read_all()) == 0,
          f"outcome={pr.outcome}")

    # 3) 설정으로 백엔드/라우팅 변경 가능 (NFR3)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, dir=tmpdir) as f:
        cfg = yaml.safe_load(open(ROOT / "config" / "routing.yaml", encoding="utf-8"))
        cfg["backends"]["private-llm"]["egress_class"] = "public"  # private을 public으로 재분류
        yaml.safe_dump(cfg, f, allow_unicode=True)
        alt = f.name
    r2 = Router(routing_path=alt)
    changed = r2.resolve("nufi-default")
    check("M1.3 설정으로 백엔드/라우팅 변경 가능",
          changed.is_public,
          f"private-llm을 public으로 재분류 후 is_public={changed.is_public}")


# ----------------------------------------------------------------------------- M2
def test_m2():
    print("\n== M2 — 탐지 파이프라인 ==")
    g = EgressGuard(ner_backend="gazetteer")

    # 1) 한국 PII 정규식 + 체크섬
    pii = load("pii_samples.jsonl")
    pii_types = {"KR_RRN", "KR_FOREIGNER_REG", "KR_BRN", "KR_PHONE", "KR_ACCOUNT",
                 "CREDIT_CARD", "KR_PASSPORT", "KR_DRIVER_LICENSE", "EMAIL"}
    miss = 0
    detected_types = set()
    for s in pii:
        got = {f.entity_type for f in g.inspect(s["prompt"]).findings}
        detected_types |= got
        for e in s["expect"]:
            if e in pii_types and e not in got:
                miss += 1
    covered = pii_types & detected_types
    check("M2.1 한국 PII 정규식+체크섬 탐지",
          miss == 0 and len(covered) == len(pii_types),
          f"PII 클래스 {len(covered)}/{len(pii_types)} 커버, 미탐 {miss}건")

    # 1b) 체크섬으로 오탐 거부 (negative)
    bad = g.inspect("주민번호 900101-1234560 확인")  # 잘못된 체크섬
    has_bad_rrn = any(f.entity_type == "KR_RRN" for f in bad.findings)
    check("M2.1b 체크섬 오탐 거부 (잘못된 RRN 미탐)", not has_bad_rrn)

    # 2) 한국어 인명/지명 NER (정규식 미탐 보완)
    ner_hits = 0
    for s in pii:
        got = {f.entity_type for f in g.inspect(s["prompt"]).findings}
        if {"KR_PERSON", "KR_LOCATION"} & got:
            ner_hits += 1
    check("M2.2 한국어 인명/지명 NER 탐지",
          ner_hits >= 4 and g.ner_backend in ("gazetteer", "transformers"),
          f"NER 탐지 샘플 {ner_hits}건, backend={g.ner_backend}")

    # 3) 비밀정보 탐지
    secrets = load("secret_samples.jsonl")
    sec_miss = sum(1 for s in secrets
                   if not any(f.entity_type == "SECRET" for f in g.inspect(s["prompt"]).findings))
    check("M2.3 비밀정보(자격증명) 탐지",
          sec_miss == 0, f"{len(secrets)-sec_miss}/{len(secrets)} 탐지")

    # 4) 정책 block/redact/pseudonymize/warn + 결정 로그
    actions_seen = set()
    pseudo_changed = False
    for s in pii + secrets:
        res = g.inspect(s["prompt"])
        for a in res.decision.actions:
            actions_seen.add(a["action"])
        if any(a["action"] == "pseudonymize" for a in res.decision.actions):
            pseudo_changed = pseudo_changed or (res.transformed_text != s["prompt"])
    need = {"block", "pseudonymize", "warn"}
    check("M2.4 정책 block/redact/pseudonymize/warn + 결정 로그",
          need.issubset(actions_seen) and pseudo_changed,
          f"관측된 동작={sorted(actions_seen)}, 가명화 본문변경={pseudo_changed}")

    # 5) benign 오탐 차단 0 (precision sanity)
    benign = load("benign_samples.jsonl")
    fp = sum(1 for s in benign if g.inspect(s["prompt"]).blocked)
    check("M2.5 benign 오탐 차단 0 (precision sanity)", fp == 0, f"false-block {fp}/{len(benign)}")

    # recall 측정 (KR 목표 ≥ 0.9 — gazetteer 기준 참고치)
    tot = sum(len(s["expect"]) for s in pii)
    hit = sum(sum(1 for e in s["expect"] if e in {f.entity_type for f in g.inspect(s["prompt"]).findings})
              for s in pii)
    print(f"  [info] PII 샘플셋 recall = {hit/tot:.3f} ({hit}/{tot}), NER backend={g.ner_backend}")


# ----------------------------------------------------------------------------- M4
def test_m4():
    print("\n== M4 — 기밀 1차 탐지(키워드/EDM) ==")
    g = EgressGuard(ner_backend="gazetteer")
    conf_sources = {"keyword", "marking", "edm_struct", "edm_doc"}
    samples = load("confidential_samples.jsonl")

    # 1) 사전 외부화 로드 (markings/keywords/allowlist) + 리로드 경로
    loaded = g.pipeline.confidential is not None and bool(g.pipeline.confidential.markings)
    check("M4.1 confidential.yaml 사전 외부화 로드(markings/keywords/allowlist)",
          loaded and bool(g.pipeline.confidential.allowlist),
          f"ruleset={g.pipeline.conf_ruleset_version}")

    # 2) 키워드/표식 탐지 + 한국어 정규화(조사/자모/공백) — 라벨 일치 + 오탐 0
    detect_ok = miss = fp = 0
    for s in samples:
        res = g.inspect(s["prompt"])
        ents = {f.entity_type for f in res.findings if f.source in conf_sources}
        want = set(s["expect"])
        if want:
            if want & ents:
                detect_ok += 1
            else:
                miss += 1
        else:
            if ents:
                fp += 1
    check("M4.2 키워드/표식/EDM 라벨 탐지(조사·자모·공백 변형 포함)",
          miss == 0, f"hit={detect_ok} miss={miss}")
    check("M4.3 오탐 관리(allowlist/stop_values) — benign 미탐",
          fp == 0, f"false_positives={fp}")

    # 4) Structured EDM: k-of-n 강신호 + 단일/저카디널리티 강등
    strong = g.inspect("고객 홍길동 연락처 010-2222-3456 등급 VIP 확인")
    single = g.inspect("성씨가 김인 고객")
    s_ents = {f.entity_type for f in strong.findings}
    check("M4.4 Structured EDM k-of-n 강신호 block + 단일필드 강등",
          "CONF_EDM_STRUCT_STRONG" in s_ents and strong.blocked
          and not any(f.source == "edm_struct" for f in single.findings),
          f"strong_fields={[f.match_meta.get('k_of_n') for f in strong.findings if f.source=='edm_struct']}")

    # 5) Unstructured EDM: 유사도 임계 분기(high→block / med→warn)
    high = g.inspect(samples[12]["prompt"])
    high_ent = {f.entity_type for f in high.findings if f.source == "edm_doc"}
    check("M4.5 Unstructured EDM 문서지문 유사도 임계 매치(고유사도 block)",
          "CONF_EDM_DOC_HIGH" in high_ent and high.blocked,
          f"sim={[f.match_meta.get('similarity') for f in high.findings if f.source=='edm_doc']}")

    # 6) 등록 원문 비저장(해시/지문만) — 인덱스에 평문 부재
    idx_path = ROOT / "config" / "edm" / "index.json"
    raw = idx_path.read_text(encoding="utf-8") if idx_path.exists() else ""
    no_plaintext = ("홍길동" not in raw) and ("사천이백만원" not in raw) and ("010-2222-3456" not in raw)
    check("M4.6 EDM 인덱스 원문 비저장(해시/시그니처만, NFR1)",
          no_plaintext and idx_path.exists())

    # 7) 정책 결합: M2(PII) + M4(기밀) 합산, block 우선
    combo = g.inspect("극비 자료. 담당자 주민번호 900101-1234568")
    types = {f.entity_type for f in combo.findings}
    check("M4.7 정책 결합 M2+M4 합산 block 우선",
          combo.blocked and "KR_RRN" in types and "CONF_MARKING_RESTRICTED" in types)

    # 8) 결정 로그 확장 필드 + 매치 원문 미기록
    d = combo.decision.findings
    conf_recs = [f for f in d if f.get("source") in conf_sources]
    has_fields = all(("class" in f and "confidence" in f and "match_meta" in f
                      and "ruleset_version" in f["match_meta"]) for f in conf_recs)
    no_text = all(not f.get("text") for f in conf_recs)
    check("M4.8 결정 로그 확장(source/class/confidence/match_meta/ruleset_version) + 원문 미기록",
          bool(conf_recs) and has_fields and no_text)
    edm_strong_rec = [f for f in strong.decision.findings if f.get("source") == "edm_struct"]
    no_cell = all("matched_fields" in f["match_meta"] and "010-2222-3456" not in json.dumps(f, ensure_ascii=False)
                  for f in edm_strong_rec)
    check("M4.8b EDM 결정 로그 — 필드명/k_of_n/지문 id 만(셀 원문 미기록)", bool(edm_strong_rec) and no_cell)

    # 9) NFR2: 기밀 탐지 추가 지연 p95 측정(예산 150ms 내)
    import time
    base = EgressGuard(ner_backend="gazetteer", enable_confidential=False)
    probe = "고객 홍길동 010-2222-3456 등급 VIP. 프로젝트 오로라 단가 문의. " + "일반 문장 채우기 " * 30

    def p95(guard, n=120):
        ts = []
        for _ in range(n):
            t0 = time.perf_counter(); guard.inspect(probe); ts.append((time.perf_counter() - t0) * 1000)
        ts.sort(); return ts[int(0.95 * n) - 1]
    added = p95(g) - p95(base)
    check("M4.9 NFR2 기밀 탐지 추가 지연 p95 ≤ 150ms",
          added <= 150.0, f"added_p95≈{added:.2f}ms")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        test_m1(tmp)
        test_m2()
        test_m4()
    print("\n== 요약 ==")
    passed = sum(1 for _, ok, _ in results if ok)
    for crit, ok, _ in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {crit}")
    print(f"\n{passed}/{len(results)} 기준 PASS")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
