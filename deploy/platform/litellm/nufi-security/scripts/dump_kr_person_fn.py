"""KR_PERSON 오차 분석 — false-negative 덤프·클래스 분류 (측정 산출물).

인명(KR_PERSON) 정확도 트랙의 착수(값싼) 단계. 주소(KR_LOCATION)에서 통한 플레이북
—오차분석 → 규칙/유니온 → 골드셋 → 게이트—의 **첫 단계**만 수행한다. 골드셋의
KR_PERSON 을 선택 백엔드로 채점해 놓친 케이스(false negative)를 전량 덤프하고, 다음
minor 캠페인의 우선순위를 데이터로 확정할 수 있도록 이름 형태(성씨 유형)·수록 여부·
도메인·조사 경계로 분류한다. 코드/규칙은 바꾸지 않는다.

중요 — 백엔드별 대표성
----------------------
  gazetteer (기본/폴백)  순수 stdlib·에어갭·결정적. 사전 매칭 위주라 인명 recall 이 낮다
                         (본 골드셋 test 0.39). **프로덕션 프록시가 아니다** — 이 덤프는
                         이름 형태 분포의 구조적 참고치일 뿐, 프로덕션 FN 목록이 아니다.
  onnx-int8 (프로덕션)   KoELECTRA INT8. 학습형 NER 이라 미수록 인명도 대부분 잡는다
                         (커밋 baseline person recall 0.9127). 모델 프로비저닝 시에만 가용
                         (미가용 시 명시적 unavailable 보고, 폴백 금지).

프로덕션 FN 의 행 단위 확정은 onnx-int8 재실행이 필요하다. 모델 미가용 환경에서 본
스크립트는 (1) 커밋 baseline 의 프로덕션 집계·분해(수록/미수록 recall) 인용, (2) 프로덕션
FN 후보 풀(=미수록 인명 전량)의 구조 분류, (3) gazetteer FN 전량 덤프(구조 참고)를 낸다.

클래스 분류 (이름 형태 기준)
----------------------------
  compound_surname  복성(2음절 성: 선우·남궁·황보·제갈·독고·사공·서문·동방 등)
  rare_surname      희성/미수록 단성(탁·갈·어·견·옹·모·초·봉·범·피 등)
  common_surname    흔한 단성(김·이·박·최·정·강·조·윤·장·임·한·오)

부가 차원: 수록 여부(gazetteer_unlisted), 도메인(부장/선생님/환자/예금주/수신자/고객/
담당자/가입 신청자/명의), 조사 경계(이름 직후 조사·경칭 부착 여부).

재현:
  python3 scripts/dump_kr_person_fn.py                       # gazetteer(에어갭)
  python3 scripts/dump_kr_person_fn.py --backend onnx-int8   # 프로덕션(모델 필요)
  python3 scripts/dump_kr_person_fn.py --json-out docs/reports/kr-person-fn-dump.json

원칙: 실고객 데이터 0 · 외부 호출 0 · 결정적(gazetteer). 종료코드는 항상 0(측정 리포트).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from egress_audit import EgressGuard  # noqa: E402
from bench_m5 import wilson_ci  # noqa: E402

GOLD = ROOT / "samples" / "gold"
ENTITY = "KR_PERSON"
BASELINE = ROOT / "docs" / "reports" / "recall-int8.json"

# 2음절(복)성 — KR 표준 복성. 미수록 인명의 상당수가 여기에 속한다.
COMPOUND_SURNAMES = {
    "선우", "남궁", "독고", "제갈", "황보", "사공", "서문", "동방",
    "어금", "망절", "황목", "소봉",
}
# 사전에 흔히 수록되는 대표 단성(정보성 — 형태 분류용, 탐지 사전 아님).
COMMON_SURNAMES = set("김이박최정강조윤장임한오")

JOSA_TITLE = set("님씨군양께은는이가을를과와에의")


def surname_class(name: str) -> tuple[str, str]:
    """이름 문자열을 성씨 형태 클래스로 분류. (class_id, label)."""
    if name[:2] in COMPOUND_SURNAMES:
        return "compound_surname", "복성(2음절 성)"
    if name[:1] in COMMON_SURNAMES:
        return "common_surname", "흔한 단성"
    return "rare_surname", "희성/미수록 단성"


def domain_of(prompt: str) -> str:
    for k in ("부장", "선생님", "환자", "예금주", "수신자", "고객",
              "담당자", "가입 신청자", "명의"):
        if k in prompt:
            return k
    return "기타"


def josa_attached(prompt: str, end: int) -> bool:
    """이름 스팬 직후 문자가 조사/경칭이면(공백 없이 부착) True."""
    return end < len(prompt) and prompt[end] in JOSA_TITLE


def build_guard(backend: str):
    if backend == "onnx-int8":
        try:
            return EgressGuard(ner_backend="onnx-int8"), None
        except Exception as e:  # noqa: BLE001 — 명시 보고용
            return None, (f"onnx-int8 미가용(에어갭/미프로비저닝): {e} — "
                          "`python3 scripts/export_onnx_int8.py` 후 M5_ONNX_DIR 지정 재실행")
    return EgressGuard(ner_backend="gazetteer"), None


def _person_spans(row):
    return [(s[0], s[1]) for s in row.get("spans", []) if s[2] == ENTITY]


def _iter_rows(split: str):
    path = GOLD / f"{split}.jsonl"
    for line in path.open(encoding="utf-8"):
        if line.strip():
            row = json.loads(line)
            if ENTITY in row.get("expect", []):
                yield row


def production_baseline() -> dict:
    """커밋된 onnx-int8 baseline 에서 프로덕션 집계·분해 인용(권위 수치)."""
    if not BASELINE.exists():
        return {"available": False}
    b = json.loads(BASELINE.read_text(encoding="utf-8"))
    sc = b.get("scores", {})
    per = sc.get("per_class", {}).get(ENTITY, {})
    n = per.get("exp")
    hit = per.get("hit")
    unl_r = sc.get("person_unlisted_recall")
    unl_n = sc.get("person_unlisted_n")
    out = {
        "available": True,
        "source": str(BASELINE.relative_to(ROOT)),
        "split": b.get("scores", {}).get("split", "test"),
        "person_recall": per.get("recall"),
        "person_ci95": per.get("ci95"),
        "person_n": n,
        "person_hit": hit,
        "person_fn": (n - hit) if (n is not None and hit is not None) else None,
        "person_unlisted_recall": unl_r,
        "person_unlisted_n": unl_n,
    }
    # 수록/미수록 분해(정수 반올림 추정) — CI 하한 부족분의 귀인용.
    if unl_r is not None and unl_n:
        unl_hit = round(unl_r * unl_n)
        out["est_unlisted_hit"] = unl_hit
        out["est_unlisted_fn"] = unl_n - unl_hit
        out["est_unlisted_ci95"] = wilson_ci(unl_hit, unl_n)
        if n is not None and hit is not None:
            listed_n = n - unl_n
            listed_hit = hit - unl_hit
            out["est_listed_n"] = listed_n
            out["est_listed_hit"] = listed_hit
            out["est_listed_fn"] = listed_n - listed_hit
            out["est_listed_recall"] = round(listed_hit / listed_n, 4) if listed_n else None
    return out


def unlisted_population() -> dict:
    """프로덕션 FN 후보 풀 = 미수록 인명 전량. 형태·도메인·경계로 분류."""
    rows = []
    for split in ("test", "dev"):
        for r in _iter_rows(split):
            if not r.get("gazetteer_unlisted"):
                continue
            sp = _person_spans(r)
            if not sp:
                continue
            name = r["prompt"][sp[0][0]:sp[0][1]]
            cid, label = surname_class(name)
            rows.append({
                "id": r.get("id"), "split": split, "name": name,
                "surname_class": cid, "surname_label": label,
                "domain": domain_of(r["prompt"]),
                "josa_attached": josa_attached(r["prompt"], sp[0][1]),
            })
    return {
        "total": len(rows),
        "by_surname_class": dict(Counter(x["surname_class"] for x in rows)),
        "by_domain": dict(Counter(x["domain"] for x in rows)),
        "by_josa_attached": {str(k): v for k, v in
                             Counter(x["josa_attached"] for x in rows).items()},
        "rows": rows,
    }


def gazetteer_fn(backend: str) -> dict:
    guard, reason = build_guard(backend)
    if guard is None:
        return {"backend_status": "unavailable", "reason": reason}
    active = guard.ner_backend
    per_split = {}
    fn_rows = []
    for split in ("test", "dev"):
        rows = list(_iter_rows(split))
        hit = 0
        for r in rows:
            res = guard.inspect(r["prompt"])
            if ENTITY in {f.entity_type for f in res.findings}:
                hit += 1
                continue
            sp = _person_spans(r)
            name = r["prompt"][sp[0][0]:sp[0][1]] if sp else ""
            cid, label = surname_class(name) if name else ("other", "-")
            fn_rows.append({
                "id": r.get("id"), "split": split, "name": name,
                "surname_class": cid, "surname_label": label,
                "unlisted": r.get("gazetteer_unlisted"),
                "domain": domain_of(r["prompt"]),
                "josa_attached": josa_attached(r["prompt"], sp[0][1]) if sp else None,
            })
        per_split[split] = {"rows": len(rows), "hit": hit, "fn": len(rows) - hit,
                            "recall": round(hit / len(rows), 4) if rows else 0.0}
    return {
        "ner_backend_active": active,
        "representativeness": ("gazetteer 는 사전 매칭 위주라 인명 recall 이 낮다 — "
                               "프로덕션(onnx-int8, 학습형 NER) FN 프록시 아님. "
                               "이름 형태 분포의 구조 참고치로만 사용."),
        "per_split": per_split,
        "by_surname_class": dict(Counter(x["surname_class"] for x in fn_rows)),
        "by_unlisted": {str(k): v for k, v in
                        Counter(x["unlisted"] for x in fn_rows).items()},
        "false_negatives": fn_rows,
    }


def run(backend: str) -> dict:
    return {
        "entity": ENTITY,
        "backend_requested": backend,
        "production_baseline": production_baseline(),
        "production_fn_candidate_pool": unlisted_population(),
        "reference_fn_dump": gazetteer_fn(backend),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="KR_PERSON false-negative 덤프·분류")
    ap.add_argument("--backend", default="gazetteer",
                    choices=["gazetteer", "onnx-int8"])
    ap.add_argument("--json-out")
    args = ap.parse_args()
    report = run(args.backend)
    out = json.dumps(report, ensure_ascii=False, indent=2)
    print(out)
    if args.json_out:
        Path(args.json_out).write_text(out + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
