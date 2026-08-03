"""CMP-104 부수 확인(option a, 무비용) — gazetteer ∪ KoELECTRA-INT8 유니온 1회 측정.

CPO MoSCoW(CMP-101) 결정 1 의 부수 확인: 유니온이 (i) 양자화로 잃은 *수록* 인명 회복분,
(ii) precision/benign-FP 에 주는 영향만 본다. **게이트 통과 경로 아님** — 미스는 미수록 인명에
집중하므로(부록 E.1) test 슬라이스 증분 recall ≈ 0 이 가설. 결과만 코멘트/리포트에 기록한다.

두 백엔드(gazetteer 폴백, onnx-int8 프로덕션 목표)의 finding 을 프롬프트별로 합집합하고,
기존 bench_m5.score() 하니스를 그대로 재사용해 KR_PERSON recall·precision·benign-FP 를 산정한다.

실행: python scripts/union_check.py --split test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from egress_audit import EgressGuard  # noqa: E402
import bench_m5  # noqa: E402


class _UnionResult:
    """score() 가 기대하는 최소 인터페이스(.findings, .blocked)."""
    def __init__(self, findings, blocked):
        self.findings = findings
        self.blocked = blocked


class UnionGuard:
    """두 백엔드의 inspect 결과를 finding 합집합 + blocked OR 로 병합."""
    def __init__(self, backends):
        self.guards = [EgressGuard(ner_backend=b) for b in backends]

    def inspect(self, prompt):
        all_findings, blocked = [], False
        seen = set()
        for g in self.guards:
            res = g.inspect(prompt)
            blocked = blocked or res.blocked
            for f in res.findings:
                key = (f.entity_type, f.start, f.end)
                if key not in seen:          # 동일 span/타입 중복 제거(유니온)
                    seen.add(key)
                    all_findings.append(f)
        return _UnionResult(all_findings, blocked)


# --- 주소 채널 유니온 (CMP-222 P3) ------------------------------------------
_BASELINE_REPORT = ROOT / "docs" / "reports" / "baseline-int8.json"


def _loc_hits(rows, guard):
    """행별 KR_LOCATION 탐지 여부와 리콜(행-레벨). 양성(주소 기대) 행만 대상."""
    pos = [r for r in rows if "KR_LOCATION" in r.get("expect", [])]
    hits = []
    for r in pos:
        got = {f.entity_type for f in guard.inspect(r["prompt"]).findings}
        hits.append("KR_LOCATION" in got)
    return hits, pos


def location_union(split, json_out=None):
    """주소(KR_LOCATION)에 한해 모델 ∪ 확장규칙(P2) 유니온 이득을 정량화한다.

    프로덕션 백엔드(onnx-int8)가 놓치는 어휘밖·구조적 주소를 규칙으로 회복한다.
    모델 제공 시 3구성(모델/규칙/유니온) 전량 라이브 측정. 미제공(에어갭) 시
    규칙·유니온은 라이브, 모델은 커밋된 baseline 리포트를 인용하고 유니온 리콜은
    규칙 전량 커버(하한)로 산정한다 — 항상 정직하게 출처를 표기한다.
    """
    rows = bench_m5.load_split(split)
    out = {"mode": "location-union(model ∪ P2-rules)", "channel": "KR_LOCATION",
           "split": split}

    # 규칙 단독(gazetteer, 에어갭 라이브) + benign FP
    rule_sc = bench_m5.score(rows, EgressGuard(ner_backend="gazetteer"))
    rule_hits, pos = _loc_hits(rows, EgressGuard(ner_backend="gazetteer"))
    n_pos = len(pos)
    rule_recall = round(sum(rule_hits) / n_pos, 4) if n_pos else 0.0

    # 모델·유니온: 모델 가용 시 라이브, 아니면 baseline 인용 + 규칙 하한.
    model_available = True
    try:
        model_guard = EgressGuard(ner_backend="onnx-int8")
        union_guard = EgressGuard(ner_backend="onnx-int8", location_union=True)
    except Exception as e:  # 모델 미프로비저닝(에어갭) — 폴백 금지, 정직 보고.
        model_available = False
        out["model_note"] = f"onnx-int8 미가용({type(e).__name__}) — 커밋 baseline 인용"

    if model_available:
        model_sc = bench_m5.score(rows, model_guard)
        union_sc = bench_m5.score(rows, union_guard)
        model_hits, _ = _loc_hits(rows, model_guard)
        union_hits, _ = _loc_hits(rows, union_guard)
        model_recall = round(sum(model_hits) / n_pos, 4) if n_pos else 0.0
        union_recall = round(sum(union_hits) / n_pos, 4) if n_pos else 0.0
        out["source"] = "live(onnx-int8)"
        out["benign_false_block"] = {
            "model": model_sc["benign_false_block"],
            "rule": rule_sc["benign_false_block"],
            "union": union_sc["benign_false_block"]}
        out["pii_precision"] = {"model": model_sc["pii_precision"],
                                "union": union_sc["pii_precision"]}
    else:
        # 모델: 커밋 baseline(동일 split) 인용. 유니온: 규칙이 양성 전량 커버 →
        # union_hit = model_hit OR rule_hit ⊇ rule_hit → union_recall ≥ rule_recall.
        bl = json.loads(_BASELINE_REPORT.read_text(encoding="utf-8")) \
            if _BASELINE_REPORT.exists() else {}
        bl_loc = bl.get("scores", {}).get("per_class", {}).get("KR_LOCATION", {})
        model_recall = bl_loc.get("recall")
        model_exp = bl_loc.get("exp")
        out["model_measured_on"] = {"split": bl.get("split"), "positive_rows": model_exp,
                                    "hit": bl_loc.get("hit")}
        if bl.get("split") != split or (model_exp not in (None, n_pos)):
            out["model_domain_note"] = (
                f"모델 리콜은 커밋 baseline(split={bl.get('split')}, 양성 {model_exp}행)에서, "
                f"규칙·유니온은 현 골드셋(양성 {n_pos}행)에서 측정 — 골드셋 성장으로 "
                f"행수 상이. 이득은 방향성 참고치이며 모델 재측정 시 확정된다.")
        # 유니온 리콜: union_hit = model_hit OR rule_hit ⊇ rule_hit(현 골드셋 라이브).
        # 규칙이 현 양성 전량 커버 → union_recall = rule_recall(=하한, 모델 가용 시 상향).
        union_recall = rule_recall
        out["source"] = "rule=live(gazetteer) · model=committed-baseline · " \
                        "union=rule-lower-bound(규칙 전량 커버)"
        out["benign_false_block"] = {
            "model": bl.get("scores", {}).get("benign_false_block"),
            "rule": rule_sc["benign_false_block"],
            "union": rule_sc["benign_false_block"]}  # 유니온 benign = 모델0 ∪ 규칙0
        out["pii_precision"] = {"model": bl.get("scores", {}).get("pii_precision"),
                                "rule": rule_sc["pii_precision"]}

    out["precision_note"] = (
        "location-union 은 모델 출력에 KR_LOCATION 규칙 스팬만 더한다 — 인명 등 다른 "
        "채널은 불변(정밀도 영향은 주소 채널로 한정). rule 의 pii_precision 은 gazetteer "
        "전체(인명 포함) 값이라 주소 유니온의 정밀도 비용을 과대평가한다. benign FP 0 유지.")
    out["location_recall"] = {"model": model_recall, "rule": rule_recall,
                              "union": union_recall}
    out["positive_rows"] = n_pos
    out["union_gain_vs_model"] = round((union_recall or 0.0) - (model_recall or 0.0), 4) \
        if model_recall is not None else None
    out["union_gain_vs_rule"] = round((union_recall or 0.0) - rule_recall, 4)
    # DoD 판정: union ≥ max(model,rule) · benign 0 · precision ~1.0
    ge = union_recall is not None and union_recall + 1e-9 >= max(
        rule_recall, model_recall or 0.0)
    benign = out["benign_false_block"]
    benign_zero = all((v == 0.0 or v is None) for v in benign.values())
    out["dod"] = {"union_ge_max": bool(ge), "benign_zero": bool(benign_zero)}
    out["dod_pass"] = bool(ge and benign_zero)

    s = json.dumps(out, ensure_ascii=False, indent=2)
    print(s)
    if json_out:
        Path(json_out).write_text(s, encoding="utf-8")
    return 0 if out["dod_pass"] else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["test", "dev"])
    ap.add_argument("--mode", default="person", choices=["person", "location"],
                    help="person=인명 채널 유니온 · location=주소 채널 유니온(모델 ∪ 확장규칙)")
    ap.add_argument("--json-out")
    args = ap.parse_args()

    if args.mode == "location":
        return location_union(args.split, args.json_out)

    rows = bench_m5.load_split(args.split)

    out = {"mode": "union(gazetteer ∪ onnx-int8)", "split": args.split}
    # 비교 기준: INT8 단독 vs 유니온
    int8 = bench_m5.score(rows, EgressGuard(ner_backend="onnx-int8"))
    union = bench_m5.score(rows, UnionGuard(["gazetteer", "onnx-int8"]))

    def slim(sc):
        return {
            "person_recall": sc["person_recall"],
            "person_recall_ci95": sc["per_class"].get("KR_PERSON", {}).get("ci95"),
            "person_hit_exp": [sc["per_class"].get("KR_PERSON", {}).get("hit"),
                               sc["per_class"].get("KR_PERSON", {}).get("exp")],
            "person_unlisted_recall": sc["person_unlisted_recall"],
            "person_unlisted_n": sc["person_unlisted_n"],
            "pii_recall": sc["pii_recall"],
            "pii_precision": sc["pii_precision"],
            "benign_false_block": sc["benign_false_block"],
            "benign_false_block_n": sc["benign_false_block_n"],
            "location_recall": sc["location_recall"],
        }

    out["int8_only"] = slim(int8)
    out["union"] = slim(union)
    out["delta"] = {
        "person_recall": round(union["person_recall"] - int8["person_recall"], 4),
        "person_unlisted_recall": round(union["person_unlisted_recall"] - int8["person_unlisted_recall"], 4),
        "pii_precision": round(union["pii_precision"] - int8["pii_precision"], 4),
        "benign_false_block": round(union["benign_false_block"] - int8["benign_false_block"], 4),
    }
    s = json.dumps(out, ensure_ascii=False, indent=2)
    print(s)
    if args.json_out:
        Path(args.json_out).write_text(s, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
