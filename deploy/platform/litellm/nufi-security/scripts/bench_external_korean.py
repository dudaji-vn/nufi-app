"""외부 한국어 NER 데이터셋 기반 PII 탐지 성능 벤치마크 (CMP-307).

공개 접근 가능한 한국어 NER 데이터셋을 다운로드하고, NuFi 파이프라인의
KR_PERSON / KR_LOCATION 탐지 성능(recall/precision/F1)을 측정한다.

데이터셋
-------
- **datasciathlete/corpus4everyone-korean-NER** (HuggingFace, 공개)
  117K train + 29K validation. 문자 단위 BIO 태깅.
  PII 관련 태그: PS(인물) → KR_PERSON, LC(장소) → KR_LOCATION.

사용법
------
  python3 scripts/bench_external_korean.py                  # 기본 (validation 전체)
  python3 scripts/bench_external_korean.py --max-rows 500   # 표본 제한
  python3 scripts/bench_external_korean.py --split train     # 학습셋 벤치마크
  python3 scripts/bench_external_korean.py --backend auto    # NER 백엔드 지정
  python3 scripts/bench_external_korean.py --json-out results.json  # JSON 결과 출력
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# 데이터셋 메타
# ---------------------------------------------------------------------------
DATASET_ID = "datasciathlete/corpus4everyone-korean-NER"
CACHE_DIR = ROOT / "data" / "external_datasets" / "corpus4everyone-korean-NER"

# BIO 태그 → NuFi PII 타입 매핑
# corpus4everyone 태그: PS(인물), LC(장소), OG(기관), FD(음식), TR(교통),
#                       AF(인공물), CV(문명), DT(날짜), TI(시간), QT(수량),
#                       EV(사건), AM(동물), PT(식물), MT(소재), TM(학술용어)
TAG_TO_NUFI: dict[str, str | None] = {
    "PS": "KR_PERSON",
    "LC": "KR_LOCATION",
    # 나머지는 NuFi PII 타입에 해당하지 않음
    "OG": None, "FD": None, "TR": None, "AF": None, "CV": None,
    "DT": None, "TI": None, "QT": None, "EV": None, "AM": None,
    "PT": None, "MT": None, "TM": None,
}

# corpus4everyone ner_tags ClassLabel 인덱스
TAG_NAMES = [
    "B-PS,", "I-PS,", "B-FD,", "I-FD,", "B-TR,", "I-TR,",
    "B-AF,", "I-AF,", "B-OG,", "I-OG,", "B-LC,", "I-LC,",
    "B-CV,", "I-CV,", "B-DT,", "I-DT,", "B-TI,", "I-TI,",
    "B-QT,", "I-QT,", "B-EV,", "I-EV,", "B-AM,", "I-AM,",
    "B-PT,", "I-PT,", "B-MT,", "I-MT,", "B-TM,", "I-TM,",
    "O",
]


# ---------------------------------------------------------------------------
# 데이터 다운로드
# ---------------------------------------------------------------------------

def download_dataset(split: str = "validation", max_rows: int = 0) -> list[dict]:
    """HuggingFace Datasets Server API로 데이터셋을 다운로드·캐시한다."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{max_rows}" if max_rows > 0 else ""
    cache_file = CACHE_DIR / f"{split}{suffix}.jsonl"

    if cache_file.exists():
        print(f"캐시 사용: {cache_file}")
        with open(cache_file, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    import requests

    PAGE_SIZE = 100
    results: list[dict] = []
    offset = 0
    target = max_rows if max_rows > 0 else float("inf")

    print(f"다운로드 중: {DATASET_ID} ({split})...")
    while len(results) < target:
        url = (
            f"https://datasets-server.huggingface.co/rows"
            f"?dataset={DATASET_ID}"
            f"&config=default&split={split}"
            f"&offset={offset}&length={PAGE_SIZE}"
        )
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  다운로드 중단 (offset={offset}): {e}")
            break

        rows_raw = data.get("rows", [])
        if not rows_raw:
            break

        for item in rows_raw:
            row = item.get("row", item)
            results.append(row)

        offset += PAGE_SIZE
        if len(results) % 1000 == 0 or len(rows_raw) < PAGE_SIZE:
            print(f"  {len(results)}건 다운로드 완료")

        if len(rows_raw) < PAGE_SIZE:
            break

    # 캐시 저장
    with open(cache_file, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"다운로드 완료: {len(results)}건 → {cache_file}")
    return results


# ---------------------------------------------------------------------------
# 데이터 변환 (BIO → span)
# ---------------------------------------------------------------------------

def convert_row(row: dict) -> dict | None:
    """corpus4everyone 행을 NuFi 벤치마크 포맷으로 변환.

    tokens: 문자 단위 리스트 (공백 포함)
    ner_tags: 정수 인코딩 BIO 태그

    반환: {"text": str, "gold_spans": [(start, end, nufi_type), ...]} or None
    """
    tokens = row.get("tokens", [])
    ner_tags = row.get("ner_tags", [])

    if not tokens or not ner_tags or len(tokens) != len(ner_tags):
        return None

    # 텍스트 재구성 (문자 단위이므로 단순 이어붙이기)
    text = "".join(tokens)

    # BIO 청크 추출
    entities: list[dict] = []
    current: dict | None = None

    char_offset = 0
    for i, (tok, tag_idx) in enumerate(zip(tokens, ner_tags)):
        if tag_idx >= len(TAG_NAMES):
            tag_name = "O"
        else:
            tag_name = TAG_NAMES[tag_idx].rstrip(",")  # trailing comma 제거

        start = char_offset
        end = char_offset + len(tok)

        if tag_name.startswith("B-"):
            if current:
                entities.append(current)
            etype = tag_name[2:]
            current = {"type": etype, "start": start, "end": end}
        elif tag_name.startswith("I-") and current:
            etype = tag_name[2:]
            if etype == current["type"]:
                current["end"] = end
            else:
                entities.append(current)
                current = None
        else:
            if current:
                entities.append(current)
                current = None

        char_offset = end

    if current:
        entities.append(current)

    # NuFi PII 타입으로 매핑
    gold_spans = []
    for ent in entities:
        nufi_type = TAG_TO_NUFI.get(ent["type"])
        if nufi_type:
            gold_spans.append((ent["start"], ent["end"], nufi_type))

    if not gold_spans:
        return None

    return {
        "text": text,
        "gold_spans": gold_spans,
    }


# ---------------------------------------------------------------------------
# 벤치마크 실행
# ---------------------------------------------------------------------------

def _span_overlap(pred_start: int, pred_end: int, gold_start: int, gold_end: int) -> bool:
    """겹침 판정 (부분 겹침도 매치로 간주)."""
    return pred_start < gold_end and gold_start < pred_end


def run_benchmark(
    rows: list[dict],
    ner_backend: str = "gazetteer",
    model_id: str | None = None,
) -> dict[str, Any]:
    """NuFi 파이프라인으로 벤치마크를 실행한다.

    반환: per-type recall/precision/F1 + 전체 요약.
    """
    from egress_audit.pipeline import DetectionPipeline

    pipeline = DetectionPipeline(
        ner_backend=ner_backend,
        model_id=model_id,
        enable_confidential=False,
    )
    print(f"파이프라인 초기화: ner_backend={pipeline.ner_backend}")

    # 타입별 카운터
    stats: dict[str, dict[str, int]] = {}  # {type: {tp, fp, fn, gold, pred}}

    total_rows = 0
    rows_with_pii = 0
    start_time = time.time()

    for i, row in enumerate(rows):
        converted = convert_row(row)
        if converted is None:
            continue

        total_rows += 1
        text = converted["text"]
        gold_spans = converted["gold_spans"]
        rows_with_pii += 1

        # NuFi 탐지 실행
        findings = pipeline.analyze(text)

        # 예측 스팬
        pred_spans = [
            (f.start, f.end, f.entity_type)
            for f in findings
            if f.entity_type in ("KR_PERSON", "KR_LOCATION")
        ]

        # 매칭 (부분 겹침 기준, 타입 일치 필수)
        gold_matched = [False] * len(gold_spans)
        pred_matched = [False] * len(pred_spans)

        for gi, (gs, ge, gt) in enumerate(gold_spans):
            for pi, (ps, pe, pt) in enumerate(pred_spans):
                if gt == pt and _span_overlap(ps, pe, gs, ge) and not pred_matched[pi]:
                    gold_matched[gi] = True
                    pred_matched[pi] = True
                    break

        # 카운터 업데이트
        for gi, (gs, ge, gt) in enumerate(gold_spans):
            if gt not in stats:
                stats[gt] = {"tp": 0, "fp": 0, "fn": 0, "gold": 0, "pred": 0}
            stats[gt]["gold"] += 1
            if gold_matched[gi]:
                stats[gt]["tp"] += 1
            else:
                stats[gt]["fn"] += 1

        for pi, (ps, pe, pt) in enumerate(pred_spans):
            if pt not in stats:
                stats[pt] = {"tp": 0, "fp": 0, "fn": 0, "gold": 0, "pred": 0}
            stats[pt]["pred"] += 1
            if not pred_matched[pi]:
                stats[pt]["fp"] += 1

        if (i + 1) % 1000 == 0:
            elapsed = time.time() - start_time
            print(f"  {i + 1}건 처리 ({elapsed:.1f}s)")

    elapsed = time.time() - start_time

    # 결과 집계
    per_type: dict[str, dict[str, Any]] = {}
    total_tp = total_fp = total_fn = 0

    for ptype, s in sorted(stats.items()):
        recall = s["tp"] / s["gold"] if s["gold"] > 0 else 0.0
        precision = s["tp"] / s["pred"] if s["pred"] > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        # Wilson CI 95%
        ci_low = _wilson_ci_low(s["tp"], s["gold"]) if s["gold"] > 0 else 0.0

        per_type[ptype] = {
            "recall": round(recall, 4),
            "precision": round(precision, 4),
            "f1": round(f1, 4),
            "tp": s["tp"],
            "fp": s["fp"],
            "fn": s["fn"],
            "gold": s["gold"],
            "pred": s["pred"],
            "recall_ci95_low": round(ci_low, 4),
        }
        total_tp += s["tp"]
        total_fp += s["fp"]
        total_fn += s["fn"]

    overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    overall_f1 = (
        2 * overall_precision * overall_recall / (overall_precision + overall_recall)
        if (overall_precision + overall_recall) > 0
        else 0.0
    )

    return {
        "benchmark": "external_korean_ner",
        "dataset": DATASET_ID,
        "ner_backend": pipeline.ner_backend,
        "total_rows_evaluated": total_rows,
        "rows_with_pii": rows_with_pii,
        "elapsed_seconds": round(elapsed, 2),
        "overall": {
            "recall": round(overall_recall, 4),
            "precision": round(overall_precision, 4),
            "f1": round(overall_f1, 4),
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
        },
        "per_type": per_type,
    }


def _wilson_ci_low(hits: int, total: int, z: float = 1.96) -> float:
    """Wilson score interval 하한 (95%)."""
    if total == 0:
        return 0.0
    p = hits / total
    denom = 1 + z * z / total
    center = p + z * z / (2 * total)
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return (center - spread) / denom


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="외부 한국어 NER 데이터셋 PII 벤치마크")
    parser.add_argument("--split", default="validation", choices=["train", "validation"],
                        help="데이터셋 분할 (기본: validation)")
    parser.add_argument("--max-rows", type=int, default=0,
                        help="최대 행 수 (0=전체)")
    parser.add_argument("--backend", default="gazetteer",
                        help="NER 백엔드 (gazetteer/onnx/auto)")
    parser.add_argument("--model-id", default=None,
                        help="모델 ID (onnx 백엔드 시)")
    parser.add_argument("--json-out", default=None,
                        help="JSON 결과 출력 경로")
    args = parser.parse_args()

    # 1. 데이터 다운로드
    rows = download_dataset(split=args.split, max_rows=args.max_rows)
    if not rows:
        print("ERROR: 데이터 다운로드 실패")
        return 1

    # 2. 벤치마크 실행
    result = run_benchmark(rows, ner_backend=args.backend, model_id=args.model_id)

    # 3. 결과 출력
    print("\n" + "=" * 70)
    print(f"벤치마크 결과: {DATASET_ID} ({args.split})")
    print(f"NER 백엔드: {result['ner_backend']}")
    print(f"평가 행: {result['total_rows_evaluated']} (PII 포함: {result['rows_with_pii']})")
    print(f"소요 시간: {result['elapsed_seconds']}s")
    print("=" * 70)

    print(f"\n전체  recall={result['overall']['recall']:.4f}  "
          f"precision={result['overall']['precision']:.4f}  "
          f"F1={result['overall']['f1']:.4f}  "
          f"(TP={result['overall']['tp']} FP={result['overall']['fp']} FN={result['overall']['fn']})")

    print(f"\n{'Type':<20} {'Recall':>8} {'Prec':>8} {'F1':>8} "
          f"{'TP':>6} {'FP':>6} {'FN':>6} {'Gold':>6} {'CI95low':>8}")
    print("-" * 90)
    for ptype, m in sorted(result["per_type"].items()):
        print(f"{ptype:<20} {m['recall']:>8.4f} {m['precision']:>8.4f} {m['f1']:>8.4f} "
              f"{m['tp']:>6} {m['fp']:>6} {m['fn']:>6} {m['gold']:>6} {m['recall_ci95_low']:>8.4f}")

    # 4. JSON 출력
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n결과 저장: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
