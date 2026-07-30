"""외부 공신력 PII 데이터셋 로더 — 골드셋 고도화 (CMP-307).

외부 데이터셋을 NuFi 내부 PII 라벨로 정규화하여 별도 슬라이스(`source: "external:*"`)로
기존 합성 골드셋과 병합한다. 기존 sealed test 의 content_hash 를 깨지 않도록 zz_ 접두사보다
뒤에 정렬되는 zzz_ext_ 접두사 _cls 를 사용한다.

지원 데이터셋
-----------
- **ai4privacy/open-pii-masking-500k** (CC-BY-4.0): 19 PII 클래스, 580k 행, 8 언어.
  한국어 미포함이지만 EMAIL/CREDITCARD/PHONE/PASSPORT/DRIVERLICENSE 등 cross-lingual
  벤치마크 비교용.
- **KLUE-NER** (CC-BY-SA-4.0): 한국어 NER, PERSON/ORGANIZATION/LOCATION 엔터티.
  PII 전용은 아니지만 한국어 이름·지명 탐지 기준선.
- **KDPII** (CC-BY-4.0, CMP-310): 53,778건 한국어 대화 기반 PII 비식별화 데이터셋.
  33개 라벨 중 10개 NuFi 매핑(PS_NAME→KR_PERSON, QT_MOBILE/QT_PHONE→KR_PHONE,
  TMI_EMAIL→EMAIL, QT_CARD_NUMBER→CREDIT_CARD, QT_ACCOUNT_NUMBER→KR_ACCOUNT,
  QT_RESIDENT_NUMBER→KR_RRN, QT_ALIEN_NUMBER→KR_FOREIGNER_REG,
  QT_PASSPORT_NUMBER→KR_PASSPORT, QT_DRIVER_NUMBER→KR_DRIVER_LICENSE,
  LC_PLACE/LC_ADDRESS→KR_LOCATION).

향후 추가 예정
-----------
- K-LegalDeID (EACL 2026): 한국 법률문서 PII — 데이터셋 공개 확인 시 추가.
- PIIBench (arxiv 2604.15776): 48 canonical PII types — 영문 중심 보충.

라이선스 준수
-----------
CC0/Apache-2.0/CC-BY-4.0/CC-BY-SA-4.0 만 사용. manifest 에 출처·라이선스 명시.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Label mapping: 외부 데이터셋 라벨 → NuFi 내부 라벨
# ---------------------------------------------------------------------------

# ai4privacy/open-pii-masking-500k 라벨 → NuFi 라벨
AI4PRIVACY_LABEL_MAP: dict[str, str | None] = {
    # 이름 관련
    "GIVENNAME": "KR_PERSON",      # 이름 → 인물 (SURNAME 과 합쳐서 사용)
    "SURNAME": "KR_PERSON",        # 성씨 → 인물
    "TITLE": None,                 # Mr./Prof 등 경칭 — NuFi PII 타입 없음
    # 연락처
    "EMAIL": "EMAIL",
    "TELEPHONENUM": "KR_PHONE",    # cross-lingual: 전화번호 패턴 벤치마크
    # 식별번호
    "CREDITCARDNUMBER": "CREDIT_CARD",
    "PASSPORTNUM": "KR_PASSPORT",  # cross-lingual: 여권번호 패턴 벤치마크
    "DRIVERLICENSENUM": "KR_DRIVER_LICENSE",  # cross-lingual
    "SOCIALNUM": "KR_RRN",         # 사회보장번호 → 주민등록번호 (구조 비교용)
    "IDCARDNUM": None,             # 일반 ID 카드 — NuFi 매핑 불확실, 제외
    "TAXNUM": "KR_BRN",            # 세금번호 → 사업자등록번호 (구조 비교용)
    # 주소/위치
    "CITY": "KR_LOCATION",
    "STREET": "KR_LOCATION",
    "BUILDINGNUM": None,           # 건물번호 단독으로는 PII 아님
    "ZIPCODE": None,               # 우편번호 — NuFi PII 타입 없음
    # 기타
    "DATE": None,                  # 날짜 — PII 아님
    "TIME": None,                  # 시간 — PII 아님
    "AGE": None,                   # 나이 — NuFi PII 타입 없음
    "SEX": None,                   # 성별 — NuFi PII 타입 없음
    "GENDER": None,                # 성별 — NuFi PII 타입 없음
}

# KDPII (korean-guardrail-dataset) 라벨 → NuFi 라벨
# 데이터셋: https://github.com/skan0779/korean-guardrail-dataset (CC BY 4.0)
# 53,778건 한국어 대화 기반 PII 비식별화 데이터, 33개 라벨
KDPII_LABEL_MAP: dict[str, str | None] = {
    # 인물
    "PS_NAME": "KR_PERSON",
    "PS_NICKNAME": None,           # 닉네임 — NuFi PII 타입 없음
    "PS_ID": None,                 # 온라인 ID — NuFi PII 타입 없음
    # 연락처/통신
    "QT_MOBILE": "KR_PHONE",
    "QT_PHONE": "KR_PHONE",
    "TMI_EMAIL": "EMAIL",
    "TMI_SITE": None,              # URL — NuFi PII 타입 없음 (SECRET 별도)
    "QT_IP": None,                 # IP 주소 — NuFi PII 타입 없음
    # 식별번호
    "QT_RESIDENT_NUMBER": "KR_RRN",
    "QT_ALIEN_NUMBER": "KR_FOREIGNER_REG",
    "QT_PASSPORT_NUMBER": "KR_PASSPORT",
    "QT_DRIVER_NUMBER": "KR_DRIVER_LICENSE",
    "QT_CARD_NUMBER": "CREDIT_CARD",
    "QT_ACCOUNT_NUMBER": "KR_ACCOUNT",
    "QT_PLATE_NUMBER": None,       # 차량번호판 — NuFi PII 타입 없음
    # 위치
    "LC_PLACE": "KR_LOCATION",
    "LC_ADDRESS": "KR_LOCATION",
    "LCP_COUNTRY": None,           # 국가명 단독은 PII 아님
    # 조직/소속 (PII 분류 외)
    "OG_WORKPLACE": None,
    "OG_DEPARTMENT": None,
    "OGG_CLUB": None,
    "OGG_EDUCATION": None,
    "OGG_RELIGION": None,
    # 이력/인구통계 (PII 분류 외)
    "CV_POSITION": None,
    "CV_SEX": None,
    "CV_MILITARY_CAMP": None,
    "FD_MAJOR": None,
    # 수치/기타 (PII 아님)
    "DT_BIRTH": None,              # 생년월일 — NuFi PII 타입 없음
    "QT_AGE": None,
    "QT_GRADE": None,
    "QT_LENGTH": None,
    "QT_WEIGHT": None,
    "TM_BLOOD_TYPE": None,
}

# KLUE-NER 라벨 → NuFi 라벨 (BIO 태깅에서 B-/I- 접두사 제거 후 매핑)
KLUE_NER_LABEL_MAP: dict[str, str | None] = {
    "PS": "KR_PERSON",         # 인물
    "LC": "KR_LOCATION",       # 장소
    "OG": None,                # 기관 — NuFi PII 타입 없음 (기관명은 PII 분류 외)
    "DT": None,                # 날짜
    "TI": None,                # 시간
    "QT": None,                # 수량
    "O": None,                 # Outside (비엔터티)
}

# ---------------------------------------------------------------------------
# 데이터셋 메타데이터 (manifest 기록용)
# ---------------------------------------------------------------------------
DATASET_REGISTRY: dict[str, dict[str, Any]] = {
    "ai4privacy": {
        "name": "ai4privacy/open-pii-masking-500k-ai4privacy",
        "license": "CC-BY-4.0",
        "url": "https://huggingface.co/datasets/ai4privacy/open-pii-masking-500k-ai4privacy",
        "languages": ["en", "fr", "de", "it", "es", "nl", "hi", "te"],
        "pii_classes": 19,
        "note": "한국어 미포함. cross-lingual PII 패턴 벤치마크용.",
    },
    "klue_ner": {
        "name": "KLUE-NER (Korean Language Understanding Evaluation)",
        "license": "CC-BY-SA-4.0",
        "url": "https://huggingface.co/datasets/klue/ner",
        "languages": ["ko"],
        "pii_classes": 2,  # PS, LC만 PII 매핑
        "note": "한국어 NER 벤치마크. PII 전용 아님, PERSON/LOCATION 기준선.",
    },
    "kdpii": {
        "name": "KDPII (korean-guardrail-dataset)",
        "license": "CC-BY-4.0",
        "url": "https://github.com/skan0779/korean-guardrail-dataset",
        "languages": ["ko"],
        "pii_classes": 10,  # PS_NAME, QT_MOBILE, QT_PHONE, TMI_EMAIL, QT_CARD_NUMBER, QT_ACCOUNT_NUMBER, QT_RESIDENT_NUMBER, QT_ALIEN_NUMBER, QT_PASSPORT_NUMBER, QT_DRIVER_NUMBER + LC_*
        "note": "53,778건 한국어 대화 기반 PII 비식별화. 10개 NuFi 매핑 라벨.",
    },
}

# ---------------------------------------------------------------------------
# 캐시 디렉터리
# ---------------------------------------------------------------------------
CACHE_DIR = Path(__file__).resolve().parent / ".cache"


def _ensure_cache() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


# ---------------------------------------------------------------------------
# ai4privacy 로더
# ---------------------------------------------------------------------------

def _download_ai4privacy_sample(max_rows: int = 200) -> list[dict]:
    """ai4privacy 데이터셋에서 NuFi 매핑 가능한 PII 표본을 추출한다.

    HuggingFace Hub API 로 parquet 데이터를 직접 조회한다.
    네트워크 불가 시 캐시된 로컬 파일을 사용한다.
    """
    cache_file = _ensure_cache() / "ai4privacy_sample.jsonl"

    if cache_file.exists():
        with open(cache_file, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    try:
        import requests
    except ImportError:
        return []

    # HuggingFace Datasets Server API — max 100 rows/request, paginate
    PAGE_SIZE = 100
    results = []
    offset = 0
    while len(results) < max_rows:
        try:
            api_url = ("https://datasets-server.huggingface.co/rows"
                       "?dataset=ai4privacy/open-pii-masking-500k-ai4privacy"
                       "&config=default&split=train"
                       f"&offset={offset}&length={PAGE_SIZE}")
            resp = requests.get(api_url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break  # 네트워크 불가 — 수집된 것만 사용

        rows_raw = data.get("rows", [])
        if not rows_raw:
            break

        for item in rows_raw:
            row = item.get("row", item)
            converted = _convert_ai4privacy_row(row)
            if converted:
                results.append(converted)

        offset += PAGE_SIZE
        if len(rows_raw) < PAGE_SIZE:
            break  # 마지막 페이지

    # 캐시 저장
    with open(cache_file, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return results


def _convert_ai4privacy_row(row: dict) -> dict | None:
    """ai4privacy 행 → NuFi 골드셋 스키마로 변환.

    GIVENNAME+SURNAME 을 합쳐 KR_PERSON 으로 매핑하는 등, 라벨 정규화를 수행한다.
    NuFi 에 매핑되는 PII 가 하나도 없으면 None 반환.
    """
    source_text = row.get("source_text", "")
    privacy_mask = row.get("privacy_mask", [])
    if not source_text or not privacy_mask:
        return None

    spans = []
    expect_set = set()

    # GIVENNAME + SURNAME 인접 쌍을 병합하여 하나의 PERSON span 으로
    name_spans = []
    other_spans = []
    for entity in privacy_mask:
        label = entity.get("label", "")
        if label in ("GIVENNAME", "SURNAME"):
            name_spans.append(entity)
        else:
            other_spans.append(entity)

    # 이름 span 은 복잡한 병합 필요 — 단순히 개별 매핑
    for entity in name_spans:
        nufi_label = AI4PRIVACY_LABEL_MAP.get(entity.get("label", ""))
        if nufi_label:
            start = entity.get("start")
            end = entity.get("end")
            if start is not None and end is not None:
                spans.append([start, end, nufi_label])
                expect_set.add(nufi_label)

    for entity in other_spans:
        label = entity.get("label", "")
        nufi_label = AI4PRIVACY_LABEL_MAP.get(label)
        if nufi_label:
            start = entity.get("start")
            end = entity.get("end")
            if start is not None and end is not None:
                spans.append([start, end, nufi_label])
                expect_set.add(nufi_label)

    if not spans:
        return None

    # span 위치 순 정렬
    spans.sort(key=lambda s: (s[0], s[1]))

    return {
        "prompt": source_text,
        "expect": sorted(expect_set),
        "spans": spans,
        "language": row.get("language", "unknown"),
    }


# ---------------------------------------------------------------------------
# KLUE-NER 로더
# ---------------------------------------------------------------------------

def _download_klue_ner_sample(max_rows: int = 200) -> list[dict]:
    """KLUE-NER 데이터셋에서 PII 매핑 가능한 표본을 추출한다.

    HuggingFace Hub API 로 직접 조회한다.
    """
    cache_file = _ensure_cache() / "klue_ner_sample.jsonl"

    if cache_file.exists():
        with open(cache_file, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    try:
        import requests
        # KLUE 는 gated dataset — HuggingFace 인증 토큰이 필요할 수 있다.
        headers = {}
        hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"

        api_url = ("https://datasets-server.huggingface.co/rows"
                   "?dataset=klue&config=ner&split=train"
                   f"&offset=0&length={max_rows * 3}")
        resp = requests.get(api_url, headers=headers, timeout=30)
        if resp.status_code in (401, 403):
            # Gated dataset — 인증 없이 접근 불가. 조용히 건너뛴다.
            return []
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    rows_raw = data.get("rows", [])
    results = []
    for item in rows_raw:
        row = item.get("row", item)
        converted = _convert_klue_ner_row(row)
        if converted and len(results) < max_rows:
            results.append(converted)

    with open(cache_file, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return results


def _convert_klue_ner_row(row: dict) -> dict | None:
    """KLUE-NER 행 → NuFi 골드셋 스키마로 변환.

    KLUE-NER 는 BIO 태깅 형식:
      tokens: ["서울", "에서", ...]
      ner_tags: [5, 0, ...]  (정수 인코딩)
    태그 인덱스 → 라벨 매핑: 0=O, 1=B-DT, 2=I-DT, 3=B-LC, 4=I-LC,
                            5=B-OG, 6=I-OG, 7=B-PS, 8=I-PS,
                            9=B-QT, 10=I-QT, 11=B-TI, 12=I-TI
    """
    tokens = row.get("tokens", [])
    ner_tags = row.get("ner_tags", [])
    if not tokens or not ner_tags or len(tokens) != len(ner_tags):
        return None

    # 태그 인덱스 → 라벨 디코딩
    TAG_NAMES = ["O", "B-DT", "I-DT", "B-LC", "I-LC",
                 "B-OG", "I-OG", "B-PS", "I-PS",
                 "B-QT", "I-QT", "B-TI", "I-TI"]

    # 텍스트 재구성 + span 추적
    text_parts = []
    char_offset = 0
    token_offsets = []  # (start, end) per token

    for i, tok in enumerate(tokens):
        # 토큰 간 공백 (첫 토큰 제외)
        if i > 0:
            text_parts.append(" ")
            char_offset += 1
        start = char_offset
        text_parts.append(tok)
        char_offset += len(tok)
        token_offsets.append((start, char_offset))

    full_text = "".join(text_parts)

    # BIO 청크 추출
    entities = []
    current_entity = None

    for i, tag_idx in enumerate(ner_tags):
        if tag_idx >= len(TAG_NAMES):
            tag_name = "O"
        else:
            tag_name = TAG_NAMES[tag_idx]

        if tag_name.startswith("B-"):
            # 이전 엔터티 종료
            if current_entity:
                entities.append(current_entity)
            etype = tag_name[2:]  # "PS", "LC", etc.
            current_entity = {
                "type": etype,
                "start": token_offsets[i][0],
                "end": token_offsets[i][1],
            }
        elif tag_name.startswith("I-") and current_entity:
            etype = tag_name[2:]
            if etype == current_entity["type"]:
                current_entity["end"] = token_offsets[i][1]
            else:
                entities.append(current_entity)
                current_entity = None
        else:
            if current_entity:
                entities.append(current_entity)
                current_entity = None

    if current_entity:
        entities.append(current_entity)

    # NuFi 라벨 매핑
    spans = []
    expect_set = set()
    for ent in entities:
        nufi_label = KLUE_NER_LABEL_MAP.get(ent["type"])
        if nufi_label:
            spans.append([ent["start"], ent["end"], nufi_label])
            expect_set.add(nufi_label)

    if not spans:
        return None

    spans.sort(key=lambda s: (s[0], s[1]))

    return {
        "prompt": full_text,
        "expect": sorted(expect_set),
        "spans": spans,
        "language": "ko",
    }


# ---------------------------------------------------------------------------
# KDPII 로더 (CMP-310)
# ---------------------------------------------------------------------------

KDPII_RAW_URL = (
    "https://raw.githubusercontent.com/skan0779/korean-guardrail-dataset"
    "/main/data/processed/KDPII.jsonl"
)


def download_kdpii() -> list[dict]:
    """KDPII 전체 데이터셋(53k)을 다운로드하여 NuFi 스키마로 변환한다.

    GitHub raw URL 에서 직접 다운로드 + 로컬 캐시(goldset/.cache/kdpii_full.jsonl).
    NuFi 에 매핑 가능한 PII 가 있는 행만 반환한다.
    """
    cache_file = _ensure_cache() / "kdpii_full.jsonl"

    if cache_file.exists():
        rows = []
        with open(cache_file, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    try:
        import requests
    except ImportError:
        raise RuntimeError("KDPII 다운로드에 `requests` 라이브러리 필요: pip install requests")

    print("KDPII 다운로드 중...")
    resp = requests.get(KDPII_RAW_URL, timeout=120, stream=True)
    resp.raise_for_status()

    results = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        converted = _convert_kdpii_row(row)
        if converted:
            results.append(converted)

    # 캐시 저장
    with open(cache_file, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"KDPII 변환 완료: {len(results)}행 NuFi 매핑")
    return results


def _convert_kdpii_row(row: dict) -> dict | None:
    """KDPII 행 → NuFi 골드셋 스키마로 변환.

    KDPII 구조: {"id", "query", "answer": [{"form", "label"}], ...}
    NuFi 스키마: {"prompt", "expect", "spans", "language"}
    """
    query = row.get("query", "")
    answers = row.get("answer", [])
    if not query or not answers:
        return None

    spans = []
    expect_set = set()

    for entity in answers:
        form = entity.get("form", "")
        label = entity.get("label", "")
        if not form or not label:
            continue

        nufi_label = KDPII_LABEL_MAP.get(label)
        if not nufi_label:
            continue

        # query 에서 form 의 위치를 찾는다
        start = query.find(form)
        if start < 0:
            continue

        spans.append([start, start + len(form), nufi_label])
        expect_set.add(nufi_label)

    if not spans:
        return None

    spans.sort(key=lambda s: (s[0], s[1]))

    return {
        "prompt": query,
        "expect": sorted(expect_set),
        "spans": spans,
        "language": "ko",
    }


# ---------------------------------------------------------------------------
# 통합 로더
# ---------------------------------------------------------------------------

def load_external_rows(
    max_ai4privacy: int = 0,
    max_klue_ner: int = 100,
    max_kdpii: int = 0,
    full: bool = True,
) -> list[dict]:
    """외부 데이터셋에서 NuFi 골드셋 스키마 행을 로드·정규화한다.

    반환 행에는 generate.py 통합에 필요한 메타키가 포함된다:
      _cls: "zzz_ext_{dataset}_{nufi_label_lower}" (기존 sealed 행 뒤에 정렬)
      source: "external:{dataset_name}"

    Parameters
    ----------
    max_ai4privacy : int
        ai4privacy 에서 가져올 최대 행 수. 0이면 전체(full=True 시).
    max_klue_ner : int
        KLUE-NER 에서 가져올 최대 행 수.
    max_kdpii : int
        KDPII 에서 가져올 최대 행 수. 0이면 전체.
    full : bool
        True 이면 전체 데이터셋 다운로드. False 이면 샘플만.
    """
    all_rows = []
    ext_id = 0

    # --- ai4privacy ---
    if full:
        ai4p_rows = download_ai4privacy_full()
    else:
        ai4p_rows = _download_ai4privacy_sample(max_rows=max(max_ai4privacy * 3, 300))
    count = 0
    for row in ai4p_rows:
        if max_ai4privacy > 0 and count >= max_ai4privacy:
            break
        ext_id += 1
        primary_type = row["expect"][0] if row["expect"] else "UNKNOWN"
        cls_suffix = primary_type.lower().replace("kr_", "")
        all_rows.append({
            "id": f"zzz_ext_ai4privacy-{ext_id:04d}",
            "prompt": row["prompt"],
            "expect": row["expect"],
            "spans": row["spans"],
            "source": "external:ai4privacy",
            "_cls": f"zzz_ext_ai4privacy_{cls_suffix}",
            "_language": row.get("language", "unknown"),
        })
        count += 1

    # --- KLUE-NER ---
    klue_rows = _download_klue_ner_sample(max_rows=max_klue_ner * 3)
    count = 0
    for row in klue_rows:
        if count >= max_klue_ner:
            break
        ext_id += 1
        primary_type = row["expect"][0] if row["expect"] else "UNKNOWN"
        cls_suffix = primary_type.lower().replace("kr_", "")
        all_rows.append({
            "id": f"zzz_ext_klue_ner-{ext_id:04d}",
            "prompt": row["prompt"],
            "expect": row["expect"],
            "spans": row["spans"],
            "source": "external:klue_ner",
            "_cls": f"zzz_ext_klue_ner_{cls_suffix}",
            "_language": "ko",
        })
        count += 1

    # --- KDPII (CMP-310) ---
    kdpii_rows = download_kdpii()
    count = 0
    for row in kdpii_rows:
        if max_kdpii > 0 and count >= max_kdpii:
            break
        ext_id += 1
        primary_type = row["expect"][0] if row["expect"] else "UNKNOWN"
        cls_suffix = primary_type.lower().replace("kr_", "")
        all_rows.append({
            "id": f"zzz_ext_kdpii-{ext_id:04d}",
            "prompt": row["prompt"],
            "expect": row["expect"],
            "spans": row["spans"],
            "source": "external:kdpii",
            "_cls": f"zzz_ext_kdpii_{cls_suffix}",
            "_language": "ko",
        })
        count += 1

    return all_rows


def get_external_manifest_info(rows: list[dict]) -> dict:
    """외부 데이터 행에 대한 manifest 보충 정보를 생성한다."""
    by_source: dict[str, int] = {}
    by_cls: dict[str, int] = {}
    for r in rows:
        src = r.get("source", "external")
        by_source[src] = by_source.get(src, 0) + 1
        for t in r.get("expect", []):
            by_cls[t] = by_cls.get(t, 0) + 1

    datasets_used = []
    for key, meta in DATASET_REGISTRY.items():
        src_key = f"external:{key}"
        if by_source.get(src_key, 0) > 0:
            datasets_used.append({
                "name": meta["name"],
                "license": meta["license"],
                "url": meta["url"],
                "rows_used": by_source[src_key],
                "note": meta["note"],
            })

    return {
        "external_total": len(rows),
        "external_by_source": by_source,
        "external_by_type": by_cls,
        "external_datasets": datasets_used,
    }


# ---------------------------------------------------------------------------
# 전체 ai4privacy 데이터셋 로더 (CMP-308)
# ---------------------------------------------------------------------------

def download_ai4privacy_full() -> list[dict]:
    """ai4privacy/open-pii-masking-500k 전체 데이터셋을 다운로드·변환한다.

    HuggingFace `datasets` 라이브러리로 스트리밍/전체 다운로드하여
    NuFi 골드셋 스키마로 변환한다. 변환 가능한 행(매핑된 PII ≥1)만 반환.

    캐시: goldset/.cache/ai4privacy_full.jsonl (재실행 시 재사용).
    """
    cache_file = _ensure_cache() / "ai4privacy_full.jsonl"

    if cache_file.exists():
        rows = []
        with open(cache_file, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    try:
        from datasets import load_dataset
    except ImportError:
        raise RuntimeError(
            "전체 다운로드에 `datasets` 라이브러리 필요: pip install datasets"
        )

    # HF 캐시 디렉터리 lock 권한 문제 우회
    locks_dir = os.path.expanduser("~/.cache/huggingface/hub/.locks")
    if not os.access(locks_dir, os.W_OK):
        hf_home = "/tmp/hf_cache"
        os.environ["HF_HOME"] = hf_home
        os.makedirs(os.path.join(hf_home, "hub", ".locks"), exist_ok=True)

    ds = load_dataset(
        "ai4privacy/open-pii-masking-500k-ai4privacy",
        split="train",
    )

    results = []
    for row in ds:
        converted = _convert_ai4privacy_row(row)
        if converted:
            results.append(converted)

    # 캐시 저장
    with open(cache_file, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return results
