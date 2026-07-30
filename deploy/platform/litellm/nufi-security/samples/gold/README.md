# NuFi 한국어 PII 골드 평가셋 (공개 배포 형태)

NuFi 탐지 엔진의 한국어 PII/DLP 정확도를 정직하게 측정하기 위한 **전량 합성** 평가셋입니다.
생성기 단일 실행으로 결정적으로 재현되며, 매니페스트 해시로 재현 일치를 검증합니다.

- **라이선스:** [CC0 1.0](./LICENSE) — 전량 합성이므로 퍼블릭 도메인 헌정. 실고객 데이터 0.
- **생성기:** [`goldset/generate.py`](../../goldset/generate.py) (고정 시드 `20260625`).
- **산출물:** `dev.jsonl`, `test.jsonl`, `manifest.json` (본 디렉터리).

## 재현 (단일 결정적 명령)

```bash
# 평가셋 + manifest(content_hash 포함) 재생성
python3 goldset/generate.py

# 커밋본과 결정적 재현 일치 검증 (불일치 시 비-0 종료 → CI/배포 게이트)
python3 goldset/generate.py --verify
```

`--verify` 는 동일 시드로 재생성한 바이트열을 커밋된 `dev.jsonl`/`test.jsonl` 과 대조하고,
`manifest.json` 의 `content_hash`(= dev+test 직렬화 바이트의 SHA-256)가 일치하는지 확인합니다.
추가로 Must 7종 분할 충분 표본과 KR_PERSON 누수방지 비율도 함께 게이트합니다.

## 스키마

각 행은 JSONL 한 줄이며 다음 키를 가집니다.

| 키 | 타입 | 설명 |
|----|------|------|
| `id` | string | `"{CLASS}-{NNNN}"` 안정적 행 식별자 |
| `prompt` | string | 모델/탐지기에 입력되는 한국어 자연어 프롬프트 |
| `expect` | string[] | 이 프롬프트에서 탐지되어야 하는 PII 타입 목록(음성 표본은 `[]`) |
| `spans` | [start,end,type][] | `prompt` 내 정답 문자 오프셋 구간(반열림 `[start,end)`, UTF 코드포인트) |
| `source` | string | 항상 `"synth"` (합성 출처) |
| `gazetteer_unlisted` | bool? | (KR_PERSON/KR_LOCATION 한정) gazetteer 사전 미수록 표본 여부 — 누수방지 슬라이스 |

예시:

```json
{"id":"KR_RRN-0001","prompt":"주민등록번호 900101-1234567 본인확인 처리 바랍니다.","expect":["KR_RRN"],"spans":[[8,22,"KR_RRN"]],"source":"synth"}
```

## 클래스 커버리지

`manifest.json` → `class_counts` 가 권위값입니다(아래는 시드 `20260625`, v0.4.16 기준).

| 클래스 | 총 | dev | test | 비고 |
|--------|----|-----|------|------|
| **KR_RRN** | 57 | 22 | 35 | Must · 체크섬 유효 |
| **KR_FOREIGNER_REG** | 57 | 22 | 35 | Must · 체크섬 유효(성별자리 5–8) |
| **KR_BRN** | 57 | 22 | 35 | Must · 체크섬 유효 |
| **KR_PASSPORT** | 57 | 22 | 35 | Must · 구조형 |
| **KR_DRIVER_LICENSE** | 57 | 22 | 35 | Must · 구조형 |
| **KR_ACCOUNT** | 60 | 24 | 36 | Must · 구조형 |
| **CREDIT_CARD** | 57 | 22 | 35 | Must · Luhn 유효 |
| KR_PHONE | 60 | 24 | 36 | 강한 PII |
| EMAIL | 60 | 24 | 36 | 강한 PII |
| KR_PERSON | 580 | 232 | 348 | NER · 미수록 성씨 56.2% (118/210 기본) |
| KR_LOCATION | 102 | 40 | 62 | NER · gazetteer 가용/미수록 혼합 |
| SECRET | 60 | 24 | 36 | 비밀키/토큰 패턴 |
| benign / benign_hard | 120 / 30 | — | — | 음성 · 하드네거티브 포함(precision 분모) |
| **합계** | **1,414** | **560** | **854** | |

**Must 7종**(체크섬/구조형 강한 PII)은 dev·test 양쪽에 충분 표본(dev ≥ 5, test ≥ 8)을 보장하며
`manifest.json` → `must_coverage` 에 분할별 표본 수가 기록됩니다.

## 측정 무결성 원칙

- **실고객 데이터 0** — 전량 합성. 체크섬이 필요한 식별번호(RRN/외국인등록/BRN/카드)는 **유효
  검증숫자**로 생성해 탐지기 선필터→체크섬 검증 경로를 실제로 통과시킵니다(과적합이 아닌 진짜 탐지).
- **층화 분할 dev 40% / test 60%** — 클래스별 층화. **test 셋은 튜닝 중 열람 금지**(누수 방지).
- **누수 방지** — KR_PERSON 표본의 **≥ 50%**(현재 0.562)는 gazetteer 성씨 사전 **미수록** 성씨로
  구성합니다. 사전 백엔드가 구조적으로 못 잡으므로 사전 과적합을 배제하고 NER 백엔드의 필요를 실측합니다.
- **결정성** — 고정 시드 + `content_hash`. 동일 실행 → 동일 산출 → 동일 해시.

## 프로그래밍 방식 로드

```python
import json, pathlib

gold_dir = pathlib.Path("samples/gold")

def load_split(split: str):
    """split = 'dev' 또는 'test'"""
    with open(gold_dir / f"{split}.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

test_rows = load_split("test")   # 854행

# 양성 표본(expect 비어있지 않음)
positive = [r for r in test_rows if r["expect"]]

# 음성 표본(benign)
negative = [r for r in test_rows if not r["expect"]]

# gazetteer 미수록 성씨 슬라이스 (KR_PERSON 누수방지)
unlisted = [r for r in positive if r.get("gazetteer_unlisted")]

# 특정 클래스만 필터
rrn_rows = [r for r in positive if "KR_RRN" in r["expect"]]
```

`manifest.json` → `class_counts` 로 분할별 행 수를 검증할 수 있습니다:

```python
with open(gold_dir / "manifest.json", encoding="utf-8") as f:
    manifest = json.load(f)

print(manifest["class_counts"])   # {"KR_RRN": {"dev": 22, "test": 35}, ...}
print(manifest["content_hash"])   # SHA-256 (재현 일치 검증용)
```

## 인용

```
NuFi Korean PII Gold Evaluation Set (synthetic), Dudaji/NuFi, 2026. CC0-1.0.
seed=20260625, manifest content_hash 로 버전 고정.
```

---

## 관련 문서

| 문서 | 역할 |
|---|---|
| [`docs/reports/README.md`](../../docs/reports/README.md) | 정확도 보고서 인덱스 — recall-int8.json 등 측정 결과 권위 |
| [`docs/HANDS_ON.md`](../../docs/HANDS_ON.md) | Part J — 골드셋 검증·벤치마크 재실행 실습 |
| [`docs/reports/kr-person-error-analysis.md`](../../docs/reports/kr-person-error-analysis.md) | KR_PERSON FN 분석 + v0.4.16 잔여 FN §7.6 |
