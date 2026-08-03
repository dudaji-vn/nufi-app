"""M5 산출물 B·C — 측정 하니스: recall/precision + span P/R/F1 + Wilson CI + 지연.

설계: docs/design/gateway/m5-bench-hardening-spec.md §2·§3 (CMP-78).
구현: CMP-99 (Engineer, 보안 상시승인 CMP-96).

기존 scripts/bench.py(M2 스텁)를 대체하는 본격 측정 하니스.

채점 (§3)
---------
- **엔티티-클래스 recall/precision**: 프롬프트가 기대 클래스를 탐지했는가 + benign FP.
- **span 단위 P/R/F1**: 경계까지 맞는가(exact) + partial overlap 별도 집계.
- **Wilson 95% CI**: 점추정 단독 합격 판정 금지(표본 출렁임 보정).
- **분모 고정**: test 셋만 평가. dev 는 --split dev 로 참고 측정.

지연 (§2)
---------
- 입력 길이 버킷(≤128/512/2048자) × N회, p50/p95/p99 + req/s. 워밍업 분리.
- 정규식 선필터 효과 분리: enable_ner off(정규식만) vs on(항상 NER) 지연 비교.

백엔드 (§2.1)
-------------
- gazetteer(폴백 베이스라인) / transformers(KoELECTRA FP32) / onnx-int8(프로덕션 목표).
- transformers·onnx-int8 미설치 시 명시적으로 "unavailable" 보고(침묵 금지).

실행:
  python3 scripts/bench_m5.py --backend gazetteer --split test
  python3 scripts/bench_m5.py --backend gazetteer --baseline write   # 회귀 기준선 등록
  python3 scripts/bench_m5.py --backend gazetteer --baseline check   # CI 회귀 게이트(-2%p)
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import EgressGuard, DetectionPipeline, PolicyEngine  # noqa: E402

GOLD = ROOT / "samples" / "gold"
BASELINE = ROOT / "samples" / "gold" / "baseline.json"

PII_UNIVERSE = {"KR_RRN", "KR_FOREIGNER_REG", "KR_BRN", "KR_PASSPORT", "KR_DRIVER_LICENSE",
                "CREDIT_CARD", "KR_ACCOUNT", "KR_PHONE", "EMAIL", "KR_PERSON",
                "KR_LOCATION", "SECRET"}
STRONG_PII = {"KR_RRN", "KR_FOREIGNER_REG", "KR_PASSPORT", "KR_DRIVER_LICENSE",
              "CREDIT_CARD", "KR_ACCOUNT"}

# §1.3 합격 기준 (test 셋, KoELECTRA 백엔드 기준)
TARGETS = {
    "pii_recall": 0.90, "pii_precision": 0.85, "strong_recall": 0.98,
    "person_recall": 0.85, "location_recall": 0.85, "secret_recall": 0.90,
    "benign_false_block": 0.02,  # 이하
}
REGRESSION_DELTA = 0.02  # recall -2%p 이상 하락 시 회귀 실패


def load_split(name):
    path = GOLD / f"{name}.jsonl"
    if not path.exists():
        sys.exit(f"골드셋 없음: {path} — 먼저 `python3 goldset/generate.py` 실행")
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def wilson_ci(hits, n, z=1.96):
    """Wilson score 95% CI (stdlib). 표본 부족 시 점추정 출렁임 보정(§3)."""
    if n == 0:
        return (0.0, 0.0)
    p = hits / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4))


def span_overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def score(rows, guard):
    """엔티티-클래스 recall/precision + span P/R/F1 + benign FP."""
    cls_exp, cls_hit = {}, {}             # 클래스별 분모/적중 (recall)
    cls_fp = {}                            # benign 등에서의 오탐(클래스별)
    person_unlisted_exp = person_unlisted_hit = 0
    benign_total = benign_false_block = 0
    # span 단위
    span_gold = span_pred = span_exact = span_partial = 0
    # precision 분모(양성 프롬프트에서 emit 된 PII-universe finding 총수)
    emit_total = emit_correct = 0

    for r in rows:
        res = guard.inspect(r["prompt"])
        got_types = {f.entity_type for f in res.findings if f.entity_type in PII_UNIVERSE}
        got_spans = [(f.start, f.end, f.entity_type) for f in res.findings
                     if f.entity_type in PII_UNIVERSE and f.end > f.start]
        expect = r.get("expect", [])

        # benign(음성)
        if not expect:
            benign_total += 1
            if res.blocked:
                benign_false_block += 1
            for t in got_types:
                cls_fp[t] = cls_fp.get(t, 0) + 1
            emit_total += len(got_spans)  # 양성 기대 없음 → 전부 오탐
            continue

        # 양성: 클래스 recall
        for e in expect:
            cls_exp[e] = cls_exp.get(e, 0) + 1
            if e in got_types:
                cls_hit[e] = cls_hit.get(e, 0) + 1
        if r.get("gazetteer_unlisted") and "KR_PERSON" in expect:
            person_unlisted_exp += 1
            if "KR_PERSON" in got_types:
                person_unlisted_hit += 1

        # precision: emit 된 finding 중 기대 클래스에 부합?
        for s in got_spans:
            emit_total += 1
            if s[2] in expect:
                emit_correct += 1

        # span 단위(경계)
        gold_spans = [tuple(g) for g in r.get("spans", [])]
        span_gold += len(gold_spans)
        span_pred += len(got_spans)
        for g in gold_spans:
            best = None
            for p in got_spans:
                if p[2] == g[2] and span_overlap(p, g):
                    best = p
                    break
            if best:
                if best[0] == g[0] and best[1] == g[1]:
                    span_exact += 1
                else:
                    span_partial += 1

    # --- 집계 ---
    def recall(keys):
        exp = sum(cls_exp.get(k, 0) for k in keys)
        hit = sum(cls_hit.get(k, 0) for k in keys)
        return hit, exp

    per_class = {}
    for c in sorted(cls_exp):
        exp, hit = cls_exp[c], cls_hit.get(c, 0)
        per_class[c] = {"recall": round(hit / exp, 4), "hit": hit, "exp": exp,
                        "ci95": wilson_ci(hit, exp), "fp": cls_fp.get(c, 0)}

    pii_hit, pii_exp = recall(PII_UNIVERSE)
    strong_hit, strong_exp = recall(STRONG_PII)
    pr_correct, pr_total = emit_correct, emit_total
    precision = round(pr_correct / pr_total, 4) if pr_total else 1.0
    span_recall = round((span_exact + span_partial) / span_gold, 4) if span_gold else 0.0
    span_prec = round((span_exact + span_partial) / span_pred, 4) if span_pred else 0.0
    span_exact_recall = round(span_exact / span_gold, 4) if span_gold else 0.0

    return {
        "n_rows": len(rows),
        "pii_recall": round(pii_hit / pii_exp, 4) if pii_exp else 0.0,
        "pii_recall_ci95": wilson_ci(pii_hit, pii_exp),
        "pii_precision": precision,
        "strong_recall": round(strong_hit / strong_exp, 4) if strong_exp else 0.0,
        "strong_recall_ci95": wilson_ci(strong_hit, strong_exp),
        "person_recall": per_class.get("KR_PERSON", {}).get("recall", 0.0),
        "person_unlisted_recall": round(person_unlisted_hit / person_unlisted_exp, 4) if person_unlisted_exp else 0.0,
        "person_unlisted_n": person_unlisted_exp,
        "location_recall": per_class.get("KR_LOCATION", {}).get("recall", 0.0),
        "secret_recall": per_class.get("SECRET", {}).get("recall", 0.0),
        "benign_false_block": round(benign_false_block / benign_total, 4) if benign_total else 0.0,
        "benign_false_block_n": f"{benign_false_block}/{benign_total}",
        "span_exact_recall": span_exact_recall,
        "span_recall_incl_partial": span_recall,
        "span_precision": span_prec,
        "span_partial": span_partial,
        "per_class": per_class,
    }


def latency(guard, ner_label):
    """입력 길이 버킷별 지연 (§2). 워밍업 분리, p50/p95/p99 + req/s."""
    base_pii = "고객 연락처 010-1234-5678 이메일 user@company.co.kr 확인 부탁드립니다. "
    filler = "이 문서는 분기 운영 리뷰를 위한 일반 업무 텍스트입니다. "
    buckets = {}
    for label, approx in (("<=128", 128), ("512", 512), ("2048", 2048)):
        body = base_pii
        while len(body) < approx:
            body += filler
        body = body[:approx]
        # 워밍업
        for _ in range(20):
            guard.inspect(body)
        lat = []
        n_iter = 200
        t_start = time.perf_counter()
        for _ in range(n_iter):
            t0 = time.perf_counter()
            guard.inspect(body)
            lat.append((time.perf_counter() - t0) * 1000)
        wall = time.perf_counter() - t_start
        lat.sort()
        buckets[label] = {
            "p50": round(statistics.median(lat), 2),
            "p95": round(lat[int(len(lat) * 0.95)], 2),
            "p99": round(lat[int(len(lat) * 0.99)], 2),
            "req_per_s": round(n_iter / wall, 1),
            "len_chars": len(body),
        }
    return {"backend": ner_label, "buckets": buckets,
            "p95_512_target_150ms": "PASS" if buckets["512"]["p95"] <= 150 else "FAIL"}


def prefilter_compare():
    """정규식 선필터 효과 분리(§2.2): (a)정규식만 vs (c)항상 NER 의 512자 p95 비교."""
    body = ("고객 연락처 010-1234-5678 이메일 user@company.co.kr 확인 바랍니다. "
            "이 문서는 분기 운영 리뷰를 위한 일반 업무 텍스트입니다. ") * 6
    body = body[:512]
    out = {}
    for label, kwargs in (("regex_only(ner_off)", {"enable_ner": False}),
                          ("always_ner(gazetteer)", {"enable_ner": True, "ner_backend": "gazetteer"})):
        g = EgressGuard(**kwargs)
        for _ in range(20):
            g.inspect(body)
        lat = []
        for _ in range(200):
            t0 = time.perf_counter()
            g.inspect(body)
            lat.append((time.perf_counter() - t0) * 1000)
        lat.sort()
        out[label] = round(lat[int(len(lat) * 0.95)], 3)
    out["prefilter_faster"] = out["regex_only(ner_off)"] <= out["always_ner(gazetteer)"]
    return out


def build_guard(backend, *, person_union=False, location_union=False):
    """백엔드 빌드. transformers/onnx-int8 미설치 시 (guard=None, reason) 반환."""
    union_kwargs = {"person_union": person_union, "location_union": location_union}
    if backend in ("transformers", "onnx-int8"):
        try:
            import transformers  # noqa: F401
        except Exception:
            return None, f"{backend} 백엔드 미설치(transformers 없음) — 에어갭 환경. 모델 프로비저닝 후 측정."
        if backend == "onnx-int8":
            try:
                import onnxruntime  # noqa: F401
                import optimum.onnxruntime  # noqa: F401
            except Exception:
                return None, "onnx-int8 미설치(onnxruntime/optimum 없음) — 모델 양자화·프로비저닝 후 측정."
            try:
                # 실제 INT8 ONNX 세션 로드(FP32 스텁 아님). 산출: scripts/export_onnx_int8.py
                return EgressGuard(ner_backend="onnx-int8", **union_kwargs), None
            except Exception as e:
                return None, f"onnx-int8 모델 미산출 — `python3 scripts/export_onnx_int8.py` 후 측정 ({e})"
        try:
            return EgressGuard(ner_backend="transformers", **union_kwargs), None
        except Exception as e:
            return None, f"{backend} 백엔드 로드 실패: {e}"
    return EgressGuard(ner_backend="gazetteer", **union_kwargs), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="gazetteer",
                    choices=["gazetteer", "transformers", "onnx-int8"])
    ap.add_argument("--split", default="test", choices=["test", "dev"])
    ap.add_argument("--baseline", choices=["write", "check"])
    ap.add_argument("--no-latency", action="store_true")
    ap.add_argument("--person-union", action="store_true",
                    help="인명 채널 규칙∪모델 유니온 활성")
    ap.add_argument("--location-union", action="store_true",
                    help="주소 채널 규칙∪모델 유니온 활성")
    ap.add_argument("--json-out")
    args = ap.parse_args()

    guard, reason = build_guard(args.backend,
                                person_union=args.person_union,
                                location_union=args.location_union)
    report = {"backend": args.backend, "split": args.split, "targets": TARGETS}

    if guard is None:
        report["backend_status"] = "unavailable"
        report["reason"] = reason
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\n[SKIP] {args.backend}: {reason}")
        return 0

    report["ner_backend_active"] = guard.ner_backend
    rows = load_split(args.split)
    sc = score(rows, guard)
    report["scores"] = sc

    if not args.no_latency:
        report["latency"] = latency(guard, guard.ner_backend)
        report["prefilter"] = prefilter_compare()

    # --- 합격 판정 (test 셋만 binary) ---
    if args.split == "test":
        # CMP-262 수용기준: KR_PERSON Wilson CI '하한' ≥0.93 (0.90 → 0.93 상향).
        person_ci_low = sc["per_class"].get("KR_PERSON", {}).get("ci95", [0.0, 0.0])[0]
        sc["person_recall_ci_low"] = person_ci_low
        person_ci_target = 0.93
        # CMP-241: KR_ACCOUNT·SECRET CI 하한 게이트 (표본 확장 후 ≥0.90).
        account_ci_low = sc["per_class"].get("KR_ACCOUNT", {}).get("ci95", [0.0, 0.0])[0]
        secret_ci_low = sc["per_class"].get("SECRET", {}).get("ci95", [0.0, 0.0])[0]
        sc["account_recall_ci_low"] = account_ci_low
        sc["secret_recall_ci_low"] = secret_ci_low
        ci_low_target = 0.90
        chk = {
            "pii_recall>=0.90": sc["pii_recall"] >= TARGETS["pii_recall"],
            "pii_precision>=0.85": sc["pii_precision"] >= TARGETS["pii_precision"],
            "strong_recall>=0.98": sc["strong_recall"] >= TARGETS["strong_recall"],
            "person_recall>=0.85": sc["person_recall"] >= TARGETS["person_recall"],
            f"person_recall_ci_low>={person_ci_target}": person_ci_low >= person_ci_target,
            f"account_recall_ci_low>={ci_low_target}": account_ci_low >= ci_low_target,
            "location_recall>=0.85": sc["location_recall"] >= TARGETS["location_recall"],
            "secret_recall>=0.90": sc["secret_recall"] >= TARGETS["secret_recall"],
            f"secret_recall_ci_low>={ci_low_target}": secret_ci_low >= ci_low_target,
            "benign_false_block<=0.02": sc["benign_false_block"] <= TARGETS["benign_false_block"],
        }
        report["acceptance"] = chk
        report["acceptance_pass"] = all(chk.values())

    # --- 회귀 기준선 ---
    if args.baseline == "write":
        BASELINE.write_text(json.dumps({
            "backend": args.backend, "split": args.split,
            "per_class_recall": {c: v["recall"] for c, v in sc["per_class"].items()},
            "pii_recall": sc["pii_recall"], "strong_recall": sc["strong_recall"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        report["baseline"] = f"written:{BASELINE}"
    elif args.baseline == "check":
        if not BASELINE.exists():
            sys.exit("기준선 없음 — 먼저 --baseline write")
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
        regressions = []
        for c, bv in base["per_class_recall"].items():
            cur = sc["per_class"].get(c, {}).get("recall", 0.0)
            if cur < bv - REGRESSION_DELTA:
                regressions.append(f"{c}: {bv:.3f}→{cur:.3f}")
        report["regression_check"] = {"regressions": regressions, "pass": not regressions}

    out = json.dumps(report, ensure_ascii=False, indent=2)
    print(out)
    if args.json_out:
        Path(args.json_out).write_text(out, encoding="utf-8")

    # exit code: test 합격/회귀 게이트
    if args.split == "test" and report.get("acceptance_pass") is False and args.baseline != "check":
        return 0  # 측정 리포트는 항상 0(미달은 리스크 등록 대상, CI 차단 아님)
    if args.baseline == "check" and report.get("regression_check", {}).get("pass") is False:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
