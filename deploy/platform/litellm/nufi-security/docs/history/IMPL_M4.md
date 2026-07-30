# 구현 노트 — M4 기밀 1차 탐지 (키워드 / EDM)

설계: [`SPEC_M4.md`](SPEC_M4.md).

M2(PII·비밀) 위에 **회사 고유 기밀**(키워드·표식·EDM) 탐지 3 신호원을 동일 `Finding` 스키마로 얹는다. M3(가역 가명화)와 같은 파이프라인·결정 로그를 공유한다.

## 추가/변경 모듈
| 파일 | 역할 |
|---|---|
| `egress_audit/normalize.py` | 한국어 정규화(NFC·제로폭·중점/하이픈·공백) + 조사 허용 단어경계 매처(§2.2) |
| `egress_audit/detectors/confidential.py` | 키워드/표식 탐지 — 사전 로드, 등급(class)·confidence 운반, 매치 원문 비기록 |
| `egress_audit/edm.py` | EDM 인덱스 빌더 + 읽기전용 매처. Structured(솔티드 HMAC 셀해시 + k-of-n) / Unstructured(shingling→winnowing→MinHash 유사도) — **순수 stdlib**(datasketch 불요, NFR4) |
| `egress_audit/detectors/korean_pii.py` | `RawSpan` 에 `conf_class/confidence/match_meta` 선택필드 추가 |
| `egress_audit/pipeline.py` | `Finding` 동일 확장 + 기밀 신호 통합(키워드 선필터→EDM 후단, NFR2). `to_dict`: 기밀 매치 원문 제거·`class` 노출 |
| `egress_audit/policy.py` | entity 우선 + `conf_class_actions` 보조표(§4.1) 등급 분기. 기밀 신호는 본문 치환 비대상(block=전면차단/warn=무편집). `confidential_summary` 적재 |
| `config/confidential.yaml` | markings/keywords/allowlist 사전 외부화(NFR3), `ruleset_version` |
| `config/policy.yaml` | M4 entity(CONF_MARKING_*, CONF_EDM_*) + `conf_class_actions` |
| `config/edm/register.yaml`, `config/edm/index.json` | EDM 등록 명세 / 빌드 산출 인덱스(해시·시그니처만) |
| `scripts/build_edm_index.py` | 오프라인 EDM 인덱스 빌더 (등록=원문 비저장) |
| `samples/edm/*`, `samples/confidential_samples.jsonl` | 합성 테스트 픽스처(등록셋+매치 프롬프트) |

## 신호원 → entity → 정책
- `marking` → `CONF_MARKING_{RESTRICTED|CONFIDENTIAL|INTERNAL}` (등급 직결, block/block/warn)
- `keyword` → `CONF_KEYWORD` (+class) → `conf_class_actions` 로 등급 분기
- `edm_struct` → `CONF_EDM_STRUCT_STRONG`(k-of-n 충족, block) / `_WEAK`(단일·warn)
- `edm_doc` → `CONF_EDM_DOC_HIGH`(고유사도, block) / `_MED`(중유사도, warn)
- M2(PII)+M4 **합산**, 하나라도 block 이면 요청 차단. 결정 로그에 전 finding 적재.

## 프라이버시/보안 (NFR1)
- EDM 인덱스는 **해시/MinHash 시그니처만** — 원문(이름·전화·단가·문서)을 저장하지 않음. salt(`EGRESS_EDM_SALT`)는 등록·조회 공유, 인덱스 외부.
- 결정 로그의 기밀 finding 은 **필드명/k_of_n/지문 id/유사도/ruleset_version 만** — 매치 원문 비기록(`text:""`).
- 인라인 조회 외부 호출 0. 등록은 오프라인 배치(`build_edm_index.py`)로 인라인과 분리.

## 운영
```bash
# 사전/임계 수정 → config/confidential.yaml, config/policy.yaml, config/edm/register.yaml
# EDM 등록 자료 갱신 후 인덱스 재빌드(ruleset_version 증가):
python3 scripts/build_edm_index.py
# 검증:
python3 tests/test_unit.py && python3 tests/run_acceptance.py
```

## 수용 기준 (SPEC_M4 §5) — 검증 결과
`tests/run_acceptance.py` 의 **M4.1–M4.9 전부 PASS** (20/20 기준), `tests/test_unit.py` 12/12 PASS.
- M4.2 키워드/표식/EDM 라벨 탐지(조사 "오로라는/오로라의", 공백삽입 "대 외 비", 영문 코드명) hit 13/13.
- M4.3 오탐 0 (allowlist "오로라 공주", stop_value 단독 "김").
- M4.4 Structured k-of-n(2/3) block + 단일필드 강등. M4.5 문서지문 고유사도 block.
- M4.6 인덱스 평문 부재. M4.7 M2+M4 합산 block. M4.8 결정 로그 확장 + 원문 미기록.
- M4.9 NFR2 기밀 추가 지연 p95 ≈ 2ms (≤ 150ms 예산).

## 비범위(설계대로) — 후속
임베딩/의미 분류기·recall/precision 튜닝(M5), 형태소 분석(라이선스 격리 필요 시 사이드카), OCR/이미지/바이너리, 정책 GUI, 자동 discovery.
