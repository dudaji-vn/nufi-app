# egress_audit/detectors/ — 탐지기 모듈 인덱스

LLM 입출력에서 민감 정보·위협을 식별하는 탐지기 모음.

## 탐지기 목록

### 입력측 (Input-side)

| 파일 | 클래스 | 설명 |
|------|--------|------|
| `korean_pii.py` | `KoreanPiiDetector` | 한국어 PII 패턴 탐지 — 주민번호, 계좌번호, 전화번호 등 12종. 정규식 + 체크섬 검증 |
| `secrets.py` | `SecretsDetector` | 비밀정보 탐지 — 명시적 키 패턴 + Shannon 엔트로피 휴리스틱 + detect-secrets 연동 |
| `confidential.py` | `ConfidentialKeywordDetector` | 기밀 분류 마킹(대외비 등) + 운영자 등록 키워드 매칭 (EDM) |
| `prompt_injection.py` | `PromptInjectionDetector` | 프롬프트 인젝션/탈옥 탐지 18종 — 한/영 패턴, 동사 활용, 유니코드 우회, 코드스위칭 |
| `ner.py` | `KoreanNerDetector` | 한국어 NER (인명·지명) — ONNX-INT8 / transformers / 가제티어 3단 백엔드 |

### 출력측 (Output-side)

| 파일 | 클래스 | 설명 |
|------|--------|------|
| `output_scanners.py` | `SystemPromptLeakDetector` | 시스템 프롬프트 유출 탐지 — 직접 노출, 명령어 누출, 구분자 태그, 내부 도구명 |
| `output_scanners.py` | `HarmfulContentDetector` | 유해 콘텐츠 탐지 — 무기·약물 제조, 자해, 불법 해킹, 독싱, 피싱 |

### 내부 인프라

| 파일 | 설명 |
|------|------|
| `_infer_pool.py` | ML 추론 동시성 제어 — 세마포어 기반 intra-op 스레드 과다 생성 방지 |
| `_proc_pool.py` | 멀티프로세스 NER 워커 풀 — GIL 우회를 통한 진정한 병렬 추론 (PoC) |
| `__init__.py` | 공개 API: `KoreanPiiDetector`, `SecretsDetector`, `KoreanNerDetector`, `PromptInjectionDetector` |

## 입출력 스키마

### RawSpan (입력측 공통)

`korean_pii.py`에 정의된 공유 스키마. 모든 입력측 탐지기가 `Iterator[RawSpan]`을 반환.

```python
@dataclass
class RawSpan:
    entity_type: str   # "KR_RRN", "SECRET", "KR_PERSON" 등
    text: str          # 매칭된 원본 텍스트
    start: int         # 시작 오프셋
    end: int           # 종료 오프셋
    score: float       # 신뢰도 (0.0–1.0)
    source: str        # 탐지기 식별자
    # 선택 필드
    conf_class: str | None     # 기밀 등급 (confidential 전용)
    confidence: float | None
    match_meta: dict | None    # 추가 메타 (규칙명, 버전 등)
```

### Finding (출력측 / 인젝션)

`prompt_injection.py`와 `output_scanners.py`는 `Finding` 데이터클래스를 반환.

```python
@dataclass
class Finding:
    entity_type: str   # "PROMPT_INJECTION", "SYSTEM_PROMPT_LEAK", "HARMFUL_CONTENT"
    text: str
    start: int
    end: int
    score: float
    source: str
    match_meta: dict   # {"severity": "high", "category": "role_override", ...}
```

## 설정 파일 연결

| 탐지기 | 설정 파일 | 비고 |
|--------|-----------|------|
| `KoreanPiiDetector` | `config/patterns.yaml` | 규칙별 `name`, `regex`, `checksum`, `exclude_*` |
| `SecretsDetector` | `config/patterns.yaml` | secrets 섹션. 엔트로피 임계값은 생성자 파라미터 |
| `ConfidentialKeywordDetector` | `config/confidential.yaml` | `markings[]`, `keywords[]`, `allowlist` |
| `PromptInjectionDetector` | `config/injection_patterns.yaml` | 커스텀 패턴 추가용. 내장 패턴은 코드 내 정의 |
| `KoreanNerDetector` | 환경 변수 | `M5_NER_MODEL_ID`, `M5_ONNX_DIR`, `NUFI_NER_*` |
| `SystemPromptLeakDetector` | — | 패턴 하드코딩 (코드 직접 수정 필요) |
| `HarmfulContentDetector` | — | 패턴 하드코딩 (코드 직접 수정 필요) |

## 새 탐지기 추가 방법

1. `detect(text: str) -> Iterator[RawSpan]` (입력측) 또는 `detect(text: str) -> List[Finding]` (출력측) 메서드를 구현한 클래스 작성
2. `__init__.py`의 `__all__`에 추가
3. `egress_audit/pipeline.py`에서 파이프라인에 연결
4. 설정 기반 탐지기는 `config/` 아래 YAML 파일만 수정하면 새 규칙 추가 가능 (코드 변경 불필요)
