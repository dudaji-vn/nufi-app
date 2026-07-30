# 구현 명세 (SPEC) — Egress-Audit M4: 기밀 1차 탐지 (키워드 / EDM)

상위 PoC 명세: [`SPEC.md`](SPEC.md) (M1 게이트웨이 + M2 PII/비밀 탐지, 수용 기준 10/10 PASS).

---

## 0. 범위 — M4 (기밀 탐지 1차)

M2는 **PII·자격증명**(누가 봐도 민감)을 탐지했다. M4는 그 위에 **회사 고유의 사내 기밀**을 얹는다. 핵심 차이: 기밀은 *정규식으로 알 수 없고, 그 회사가 등록해야만* 안다.

- **In**: 기밀 분류 체계, 키워드/표식 사전(외부화·NFR3), EDM(문서 지문) 2종(구조화·비구조화), 정책 결합(block/warn), 결정 로그 스키마 확장, 한국어 기밀 패턴·라이선스(NFR4) 검토.
- **Out (이번 비범위)**: 임베딩/의미 기반 기밀 분류기(M5 후보), 완전 DLP, 정책 GUI, OCR·이미지·바이너리 첨부 스캔, 자동 데이터 발견(discovery).

### 준수 NFR (SPEC.md §공통 원칙 승계)
- **NFR1** 외부 네트워크 호출 0. 사전·지문 인덱스 전부 로컬, 등록 원문 비저장(해시/지문만).
- **NFR2** 인라인 추가 지연 p95 ≤ 150ms(CPU). 키워드/표식은 선필터, EDM은 그 뒤 단계.
- **NFR3** 사전·임계·예외를 설정 파일로 외부화, 운영자 갱신·리로드 가능.
- **NFR4** 상업 사용 가능 라이선스만. GPL/AGPL/NC 인라인 의존 금지(§6).

---

## 1. 기밀 분류 체계 (Classification taxonomy)

탐지 대상을 4 등급 × 3 신호원으로 정규화한다. 등급은 정책 severity·기본 동작에 직결된다.

### 1.1 보안 등급(class)
| class | 한국어 표기 예 | 기본 정책 | severity |
|---|---|---|---|
| `RESTRICTED` | 극비 / 관계자외 열람금지 | block | critical |
| `CONFIDENTIAL` | 기밀 / 사외비 | block | high |
| `INTERNAL` | 대외비 / 사내한(限) / 내부용 | warn (운영 선택 시 block) | medium |
| `PUBLIC` | 공개 | allow | — |

등급은 운영자가 사전 항목·EDM 등록 단위로 부여한다. 미부여 매치는 `default_conf_action`(기본 warn)로 처리.

### 1.2 신호원(source) — M2 Finding 스키마 재사용
M4는 새 detector 3종을 M2 파이프라인에 **동일 `Finding` 스키마**로 추가한다(`source` 값으로 구분).

| source | 무엇 | 대표 entity_type |
|---|---|---|
| `keyword` | 사내 기밀 키워드/구문 사전 매치 | `CONF_KEYWORD` |
| `marking` | 문서 분류 표식 매치("대외비" 등) | `CONF_MARKING` |
| `edm_struct` | 등록 데이터셋 셀 값 해시 매치(고객명단·급여·단가) | `CONF_EDM_STRUCT` |
| `edm_doc` | 등록 문서 지문 유사도 매치(인용·일부 복붙) | `CONF_EDM_DOC` |

각 finding은 `class`(§1.1)와 `confidence`(0–1)를 부가 메타로 운반(§4).

---

## 2. 키워드 / 표식 사전 — 외부화 (NFR3)

### 2.1 설정 파일 `config/confidential.yaml` (설계 스케치 — 구현 시 작성)
`patterns.yaml`과 동일한 외부화 패턴. 코어는 사전 로드만 하고, 항목은 운영자가 갱신.

```yaml
version: 1
default_conf_action: warn          # 미지정 등급 매치 기본 동작

markings:                          # 문서 분류 표식 (강신호, 고정밀)
  - name: MARK_RESTRICTED
    class: RESTRICTED
    phrases: ["극비", "관계자외 열람금지", "관계자 외 열람 금지"]
  - name: MARK_CONFIDENTIAL
    class: CONFIDENTIAL
    phrases: ["기밀", "사외비", "Confidential", "Company Confidential"]
  - name: MARK_INTERNAL
    class: INTERNAL
    phrases: ["대외비", "사내한", "사내 한", "내부용", "Internal Use Only", "[내부용]"]

keywords:                          # 회사 고유 기밀어 (운영자 등록)
  - name: PROJECT_CODENAMES
    class: CONFIDENTIAL
    match_mode: word               # exact | word | substring | regex
    case_sensitive: false
    terms: ["프로젝트 오로라", "Aurora", "NuFi-X2"]
    min_len: 4                     # 너무 짧은 일반어 충돌 방지
    allow_context: []              # 예외 문맥(아래 등장 시 무시)
  - name: UNRELEASED_SKU
    class: CONFIDENTIAL
    match_mode: regex
    terms: ['(?i)\bSKU-NX-\d{4}\b']

allowlist:                         # 전역 오탐 예외 (일반어/공개어)
  terms: ["서울", "오로라(자연현상)"]
```

### 2.2 한국어 정규화 (매칭 정확도)
한국어는 조사 결합·자모 분리·공백/중점 변형 때문에 단순 문자열 비교로 누락된다. 매칭 전 **정규화 파이프**를 통과시킨다.
- NFC 유니코드 정규화(자모 결합), 양끝 공백·제로폭 문자 제거, 중점(·)/하이픈 변형 통일.
- `match_mode: word`는 **한국어 단어 경계**를 조사 허용으로 처리(예: "오로라는/오로라의" → "오로라" 매치). 단순 `\b`는 한글에 부정확하므로, 등록어 뒤 0–3 음절의 조사 후보를 허용하는 경계 규칙 또는 정규화 후 substring + 길이/문맥 가드를 사용.
- `case_sensitive:false`는 영문 코드명에만 적용.

### 2.3 키워드 오탐 관리
| 위험 | 완화 |
|---|---|
| 코드명이 일반어와 충돌(예: "Aurora") | `min_len`, `match_mode: word`, 등급별 `allow_context`, 전역 `allowlist` |
| 짧은 약어 과탐 | 최소 길이 게이트 + 동시신호 요구(같은 메시지 내 2+ 매치 시 신뢰도↑) |
| 조사/형태 변형 누락(과소탐) | §2.2 정규화 + 음절 경계 허용 |
| 운영자 사전 품질 편차 | recall/precision 측정 스크립트(§5)로 사전 등록 후 회귀 검증 |

---

## 3. EDM — 문서 지문 (Exact Data Match)

EDM = 회사가 **사전에 등록한** 민감 자료를 식별. 키워드가 "단어"라면 EDM은 "이 특정 명단/이 특정 문서"를 탐지. 등록은 **오프라인 배치**(NFR1: 등록·조회 모두 로컬, 원문 비저장).

### 3.1 Structured EDM — 데이터셋 셀 매치
대상: 고객명단·급여표·미공개 단가·계약 상대 목록 등 표 형식.
- **등록**: CSV/시트 → 셀 값 정규화 → **솔티드 해시**(HMAC-SHA256, per-deployment salt)로 인덱싱. 컬럼별 메타(field name, class, cardinality) 보존. 원문 셀 미저장.
- **조회**: 프롬프트 토큰을 같은 정규화·해시로 인덱스 조회.
- **k-of-n 동시매치(핵심)**: 단일 값(예: 성씨 "김")이 아니라, **같은 레코드의 N개 필드 중 K개 이상**이 한 메시지에 함께 등장할 때만 강신호. 예) "(이름)+(전화)+(직급)" 동시 → `CONF_EDM_STRUCT` strong(block).
- **오탐 관리**: `stop_values`(공통 성씨·"서울"·0/1 등 저(低)카디널리티 값 제외), 컬럼별 `min_cardinality`, k-of-n 임계, 단일 필드 단독 매치는 warn 이하로 강등.

### 3.2 Unstructured EDM — 문서 지문 유사도
대상: 계약서·설계서·내부 보고서 등 산문. 부분 인용·일부 복붙·경미한 편집을 탐지.
- **등록**: 문서 → 정규화 → **shingling**(n-gram, 예 5-gram) → rolling hash → **winnowing**으로 대표 지문 선택 → **MinHash**(또는 SimHash) 시그니처 인덱스. 원문 미저장(지문만).
- **조회**: 프롬프트를 같은 방식으로 지문화 → 등록 문서와 **Jaccard(MinHash)/Hamming(SimHash) 유사도** 계산 → 임계 초과 시 매치.
- **임계 분기(정책 연동)**: 고유사도 → block, 중유사도 → warn(§4). 임계는 NFR3 설정값.
- **오탐 관리**: 최소 shingle 길이(짧은 공통 문구 무시), winnowing window 크기, 흔한 보일러플레이트 문구 stoplist, 문서별 idf 가중, 유사도 임계 튜닝 + 측정(§5).

### 3.3 등록 자료 보호 (설계 제약)
- 인덱스는 **해시/지문만** 보관. 인덱스가 유출돼도 원문 복원 불가(역상 저항 + salt).
- 등록 파이프는 게이트웨이 인라인 경로와 분리(오프라인). 인라인은 **읽기 전용 조회**만.
- 인덱스 버전(`ruleset_version`)을 결정 로그에 기록(§4) — 어떤 사전/지문으로 판정했는지 감사 추적.

### 3.4 라이브러리 후보 (NFR4 §6 참조)
- MinHash/LSH: **datasketch (MIT)** 사용 가능. 또는 stdlib 자작.
- Rolling hash/winnowing/SimHash: **자작 권장**(stdlib, 라이선스 무관).
- 형태소 분석은 EDM에 불필요(문자 n-gram 기반). 키워드 경계용 선택 사용은 §6에서 격리.

---

## 4. 정책 결합 + 결정 로그 확장

### 4.1 정책 결합 (`config/policy.yaml` 확장)
M4 entity를 기존 entities 맵에 추가. M2 PII와 **같은 요청에서 합산**: 결정 규칙은 기존과 동일 — 하나라도 `blocking_actions`(block)이면 요청 차단, 최고 severity 우선.

```yaml
entities:
  # --- M4 기밀 (신규) ---
  CONF_MARKING_RESTRICTED:   { action: block, severity: critical }
  CONF_MARKING_CONFIDENTIAL: { action: block, severity: high }
  CONF_MARKING_INTERNAL:     { action: warn,  severity: medium }   # 운영 선택 시 block
  CONF_KEYWORD:              { action: block, severity: high }      # class로 세분(아래)
  CONF_EDM_STRUCT_STRONG:    { action: block, severity: high }      # k-of-n 충족
  CONF_EDM_STRUCT_WEAK:      { action: warn,  severity: medium }    # 단일 필드
  CONF_EDM_DOC_HIGH:         { action: block, severity: high }      # 고유사도
  CONF_EDM_DOC_MED:          { action: warn,  severity: low }       # 중유사도
```
- entity별 고정 매핑이 거친 경우, detector가 `class`/`confidence`를 실어 보내고 PolicyEngine이 `class→action` 보조 테이블로 분기(설계 옵션). 1차는 위 entity 세분으로 충분.
- **block 우선순위**: M2(주민번호 등) + M4(기밀) 동시 발생 시 결정은 합집합 — 둘 중 하나라도 block이면 block. 결정 로그에 모든 finding 적재.

### 4.2 결정 로그 스키마 확장 (`audit.py` record)
기존 레코드(§SPEC M1)에 다음을 **추가**(원문·셀값·문서 원문은 절대 미기록):
```jsonc
{
  "findings": [
    {
      "entity_type": "CONF_EDM_STRUCT_STRONG",
      "source": "edm_struct",          // keyword | marking | edm_struct | edm_doc
      "class": "CONFIDENTIAL",
      "confidence": 0.94,
      "match_meta": {
        "matched_fields": ["name","phone","grade"],   // structured k-of-n (값 아님, 필드명만)
        "k_of_n": "3/4",
        "fingerprint_id": "doc:contract-2026-q2#sig",  // 지문 식별자만
        "similarity": 0.88,
        "ruleset_version": "conf-2026.06.24"
      }
      // 주의: matched text/원문 미기록 — 해시·필드명·지문 id만
    }
  ],
  "decision": {
    "confidential_summary": { "max_class": "CONFIDENTIAL", "keyword_hits": 1, "edm_struct_hits": 1, "edm_doc_hits": 0 }
  }
}
```
- 감사성: `ruleset_version`로 재현. 운영자가 사전·인덱스 갱신 시 버전 증가.
- 프라이버시: 결정 로그도 기밀을 다시 누설하면 안 됨 — **매치 위치/필드명/지문 id/유사도만**, 매치 원문 비기록(M2의 마스킹 원칙 연장).

---

## 5. 수용 기준 (binary)

> 아래는 구현의 완료 정의. 설계의 완료 정의는 §7.

- [ ] `config/confidential.yaml` 사전 외부화 — markings/keywords/allowlist 로드, 운영자 갱신·리로드(NFR3).
- [ ] 키워드·표식 탐지 + 한국어 정규화(조사/자모/공백 변형) — 샘플셋 recall/precision 측정.
- [ ] Structured EDM: 데이터셋 셀 솔티드 해시 인덱스 + k-of-n 동시매치 + stop_values/min_cardinality 가드.
- [ ] Unstructured EDM: 문서 지문(MinHash/winnowing 또는 SimHash) + 유사도 임계 매치.
- [ ] 등록 원문 비저장(해시/지문만), 인라인 조회 외부호출 0(NFR1) 검증.
- [ ] 정책 결합: M2+M4 합산, block 우선, `policy.yaml` 신규 entity 동작.
- [ ] 결정 로그 확장 필드(`source`,`class`,`confidence`,`match_meta`,`ruleset_version`) 적재 — 매치 원문 미기록 확인.
- [ ] 오탐 관리 설정화(allowlist/stop_values/임계) + 회귀 측정.
- [ ] NFR2 영향: 키워드 선필터·EDM 후단의 추가 지연 p95 측정(예산 내).
- [ ] `samples/`에 기밀 키워드·표식·EDM(등록셋+매치 프롬프트) 테스트 픽스처 추가.

---

## 6. 한국어 기밀 패턴 · 라이선스 검토 (NFR4)

### 6.1 한국어 기밀 패턴 (등록 시드)
- 분류 표식: `대외비`, `사내한(限)`, `사내 한정`, `관계자외 열람금지`, `극비`, `기밀`, `[내부용]`, `사외비`, 영문 혼용 `Confidential` / `Internal Use Only`.
- 변형: 자모 분리·공백 삽입("대 외 비")·중점, 조사 결합 → §2.2 정규화로 흡수.

### 6.2 라이선스 게이트 (인라인 배포 가능 여부)
| 구성요소 | 후보 | 라이선스 | 판정 |
|---|---|---|---|
| MinHash/LSH | datasketch | MIT | **가능** |
| Rolling hash·winnowing·SimHash | 자작(stdlib) | — | **가능(권장)** |
| 정규화/매칭 코어 | 자작(stdlib + PyYAML) | MIT/BSD | **가능** |
| 형태소 분석(선택) | KoNLPy / mecab-ko-dic / soynlp | GPL 계열 혼재 | **인라인 주의 — 1차 비채택**, 필요 시 별도 프로세스 격리(AGPL/GPL 인라인 링크 회피, TruffleHog 사례 원칙) |
| 형태소 분석(선택) | Kiwi(kiwipiepy) | 자체/LGPL성 — **구현 단계 재확인** | 보류 |

- **결론**: M4 1차는 **무라이선스 자작 + MIT(datasketch) 한정**으로 NFR4를 만족. 한국어 단어 경계는 형태소기 없이 §2.2 정규화 + 음절 경계 규칙으로 처리. 형태소 분석이 정밀도에 필요하면 별도 사이드카로 격리(인라인 의존 금지)하고 라이선스를 구현 착수 시 재검증.

---

## 7. 설계 완료 정의 · 다음 단계

- **설계 완료 조건**: §1–§6 명세 확정 + 구현 수용기준(§5) 작성 + 라이선스 판정 + 결정 로그 스키마 확정. → 본 문서로 충족.
- **연계**: M3(가역 가명화 원복) 결정 로그와 스키마 정합 유지. M5(임베딩/의미 분류기·recall·precision 측정 스크립트)는 본 EDM 임계 튜닝 데이터를 입력으로 사용.

> 스펙 변경은 본 문서 갱신으로 추적한다.
