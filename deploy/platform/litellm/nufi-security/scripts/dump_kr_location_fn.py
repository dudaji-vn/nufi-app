"""KR_LOCATION 오차 분석 — false-negative 전량 덤프·클래스 분류 (측정 산출물).

v0.2.0 주소 정확도 트랙의 착수(값싼) 단계. 골드셋의 KR_LOCATION 을 선택 백엔드로
채점해 놓친 케이스(false negative)를 전량 덤프하고, 후속 대응단계 우선순위를
데이터로 확정할 수 있도록 클래스로 분류한다. 코드/규칙은 바꾸지 않는다.

클래스 분류 (도메인 기준)
-------------------------
  a. road_address   — 도로명주소(로/길 + 번지)
  b. detail_address — 상세주소(동/호·건물명이 주소 일부)
  c. oov_proper     — 어휘밖 고유지명(신도시·개발지구·랜드마크·복합몰 등)
  d. boundary       — 경계/부분매치(탐지는 됐으나 스팬 경계가 어긋남)
  e. other

백엔드
------
  gazetteer (기본/폴백) — 순수 stdlib, 에어갭 동작. 접미사 규칙 + 알려진 지명.
  onnx-int8 (프로덕션)  — KoELECTRA INT8. 모델 프로비저닝 시에만 가용
                          (미가용 시 명시적으로 unavailable 보고, 폴백 금지).

재현:
  python3 scripts/dump_kr_location_fn.py                       # gazetteer(에어갭)
  python3 scripts/dump_kr_location_fn.py --backend onnx-int8   # 프로덕션(모델 필요)
  python3 scripts/dump_kr_location_fn.py --json-out docs/reports/kr-location-fn-dump.json

원칙: 실고객 데이터 0 · 외부 호출 0 · 결정적(gazetteer). 종료코드는 항상 0(측정 리포트).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import EgressGuard  # noqa: E402

GOLD = ROOT / "samples" / "gold"
ENTITY = "KR_LOCATION"

# --- 어휘밖 고유지명(class c) 하위 유형 힌트(접미사 기반, 정보성) ------------------
_OOV_SUFFIX_HINTS = (
    ("신도시/국제도시", re.compile(r"(?:신도시|국제도시)$")),
    ("개발지구",        re.compile(r"지구$")),
    ("산업/테크노단지",  re.compile(r"(?:테크노밸리|밸리|단지|파크)$")),
    ("복합몰/상업",      re.compile(r"(?:몰|플라자|타워|센터|시티)$")),
    ("공원/랜드마크",    re.compile(r"(?:공원|광장|경기장|역)$")),
)
# 도로명주소/상세주소 판별(정보성).
_ROAD_RE = re.compile(r"[가-힣A-Za-z0-9]+(?:로|길)\s*\d")
_DETAIL_RE = re.compile(r"\d+\s*(?:동|호)\b|[가-힣]+(?:빌딩|아파트|오피스텔|타워)\s*\d")


def classify(loc_text: str) -> tuple[str, str]:
    """골드 스팬 텍스트를 도메인 클래스로 분류. (class_id, subtype) 반환."""
    if _ROAD_RE.search(loc_text):
        return "a_road_address", "도로명+번지"
    if _DETAIL_RE.search(loc_text):
        return "b_detail_address", "동/호·건물명"
    for sub, rx in _OOV_SUFFIX_HINTS:
        if rx.search(loc_text):
            return "c_oov_proper", sub
    # 접미사에 안 걸리는 고유지명(라틴 혼용/짧은 지명 등)도 어휘밖으로 본다.
    if re.search(r"[A-Za-z]", loc_text):
        return "c_oov_proper", "라틴 혼용 고유지명"
    return "c_oov_proper", "기타 고유지명"


def build_guard(backend: str):
    """백엔드 빌드. onnx-int8 미가용 시 (None, reason)."""
    if backend == "onnx-int8":
        try:
            return EgressGuard(ner_backend="onnx-int8"), None
        except Exception as e:  # noqa: BLE001 — 명시 보고용
            return None, (f"onnx-int8 미가용(에어갭/미프로비저닝): {e} — "
                          "`python3 scripts/export_onnx_int8.py` 후 M5_ONNX_DIR 지정 재실행")
    return EgressGuard(ner_backend="gazetteer"), None


def gold_loc_spans(row) -> list[tuple[int, int]]:
    return [(s[0], s[1]) for s in row.get("spans", []) if s[2] == ENTITY]


def run(backend: str) -> dict:
    guard, reason = build_guard(backend)
    if guard is None:
        return {"entity": ENTITY, "backend": backend, "backend_status": "unavailable",
                "reason": reason}

    active = guard.ner_backend
    per_split = {}
    fn_rows = []          # false negative(클래스 미탐지) 전량
    boundary_rows = []    # class d: 탐지됐으나 스팬 경계 불일치
    class_counts: dict[str, int] = {}

    for split in ("test", "dev"):
        path = GOLD / f"{split}.jsonl"
        rows = [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]
        loc_rows = [r for r in rows if ENTITY in r.get("expect", [])]
        hit = 0
        for r in loc_rows:
            res = guard.inspect(r["prompt"])
            got_types = {f.entity_type for f in res.findings}
            got_spans = [(f.start, f.end) for f in res.findings
                         if f.entity_type == ENTITY and f.end > f.start]
            gold = gold_loc_spans(r)
            gold_texts = [r["prompt"][a:b] for a, b in gold]

            if ENTITY in got_types:
                hit += 1
                # class d 후보: 클래스는 맞췄으나 어떤 골드 스팬과도 경계 정확 일치가 없음
                exact = any(gs in got_spans for gs in gold)
                overlap = any(a < gb and ga < b for (ga, gb) in gold for (a, b) in got_spans)
                if not exact and overlap:
                    cid = "d_boundary"
                    class_counts[cid] = class_counts.get(cid, 0) + 1
                    boundary_rows.append({
                        "id": r.get("id"), "split": split, "class": cid,
                        "gold": gold_texts, "gazetteer_unlisted": r.get("gazetteer_unlisted"),
                    })
                continue

            # false negative(클래스 미탐지)
            cid, sub = ("e_other", "-") if not gold_texts else classify(gold_texts[0])
            class_counts[cid] = class_counts.get(cid, 0) + 1
            fn_rows.append({
                "id": r.get("id"), "split": split, "class": cid, "subtype": sub,
                "gold": gold_texts, "gazetteer_unlisted": r.get("gazetteer_unlisted"),
            })
        per_split[split] = {"loc_rows": len(loc_rows), "hit": hit,
                            "fn": len(loc_rows) - hit,
                            "recall": round(hit / len(loc_rows), 4) if loc_rows else 0.0}

    total_rows = sum(v["loc_rows"] for v in per_split.values())
    total_hit = sum(v["hit"] for v in per_split.values())
    return {
        "entity": ENTITY,
        "backend_requested": backend,
        "ner_backend_active": active,
        "note": ("gazetteer per_class recall 은 행-레벨(행에 KR_LOCATION finding 이 "
                 "하나라도 있으면 hit) — 골드 스팬 자체를 잡았다는 뜻은 아니다. "
                 "false negative = 행에 KR_LOCATION 이 전혀 안 잡힌 케이스."),
        "per_split": per_split,
        "totals": {"loc_rows": total_rows, "hit": total_hit, "fn": total_rows - total_hit,
                   "recall": round(total_hit / total_rows, 4) if total_rows else 0.0},
        "class_counts": class_counts,
        "false_negatives": fn_rows,
        "boundary_cases": boundary_rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="KR_LOCATION false-negative 덤프·분류")
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
