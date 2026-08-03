"""RouteLLM 복잡도 분류기 — Phase 2 비용·품질 최적화 (CMP-293).

프롬프트 복잡도를 0.0(단순)~1.0(복잡)으로 평가하고,
threshold 기준으로 저비용 모델 / 고성능 모델을 선택한다.

한국어 프롬프트에 특화된 휴리스틱 피처:
  - 문장 수·토큰 수·평균 문장 길이
  - 전문 용어 밀도 (기술·법률·의료 등)
  - 조건문·논리 구조 복잡도
  - 코드 블록·수식 포함 여부
  - 다단계 지시 패턴 ("먼저 … 그 다음 … 마지막으로")

설계 원칙:
  - 외부 ML 모델 의존 없이 빠른 휴리스틱 추론 (< 5ms)
  - 향후 RouteLLM 학습 모델로 교체 가능한 인터페이스
  - A/B 테스트 프레임워크와 통합
"""
from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger("nufi.complexity")

# ---------------------------------------------------------------------------
# 복잡도 분류 결과
# ---------------------------------------------------------------------------

COMPLEXITY_SIMPLE = "simple"
COMPLEXITY_MODERATE = "moderate"
COMPLEXITY_COMPLEX = "complex"


@dataclass
class ComplexityResult:
    """프롬프트 복잡도 평가 결과."""
    score: float                            # 0.0 (simple) ~ 1.0 (complex)
    label: str                              # simple | moderate | complex
    target_model: str                       # 선택된 모델
    original_model: str                     # 요청된 원본 모델
    features: Dict[str, float] = field(default_factory=dict)
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "label": self.label,
            "target_model": self.target_model,
            "original_model": self.original_model,
            "features": {k: round(v, 4) for k, v in self.features.items()},
            "latency_ms": round(self.latency_ms, 2),
        }


# ---------------------------------------------------------------------------
# 한국어 복잡도 피처 추출
# ---------------------------------------------------------------------------

# 전문 용어 패턴 (기술, 법률, 의료, 금융)
_TECHNICAL_TERMS = re.compile(
    r"(?:알고리즘|아키텍처|데이터베이스|마이크로서비스|쿠버네티스|도커|"
    r"API|SDK|REST|GraphQL|gRPC|CI/CD|DevOps|MLOps|"
    r"머신러닝|딥러닝|트랜스포머|임베딩|파인튜닝|"
    r"컨테이너|오케스트레이션|로드밸런서|캐시|인덱스|"
    r"리팩토링|디자인패턴|SOLID|DDD|TDD|"
    r"블록체인|스마트컨트랙트|토큰화|해시|암호화)",
    re.IGNORECASE,
)

_LEGAL_TERMS = re.compile(
    r"(?:개인정보보호법|GDPR|정보통신망법|전자금융거래법|"
    r"약관|계약서|손해배상|면책|저작권|특허|상표|"
    r"컴플라이언스|내부통제|감사|규정|조항|판례)",
    re.IGNORECASE,
)

_MEDICAL_TERMS = re.compile(
    r"(?:진단|처방|임상시험|부작용|투여|용량|"
    r"병리|세포|유전자|프로토콜|바이오마커|"
    r"FDA|IRB|GCP|ICH)",
    re.IGNORECASE,
)

# 다단계 지시 패턴
_MULTI_STEP = re.compile(
    r"(?:먼저|첫째|1단계|step\s*1|우선|시작으로)",
    re.IGNORECASE,
)

_SEQUENTIAL = re.compile(
    r"(?:그\s*다음|그리고\s*나서|이후에|그런\s*다음|두\s*번째|셋째|마지막으로|최종적으로)",
    re.IGNORECASE,
)

# 코드/수식 패턴
_CODE_BLOCK = re.compile(r"```[\s\S]*?```|`[^`]+`")
_MATH_EXPR = re.compile(r"[∑∏∫√∂∇≤≥≠±×÷]|\\(?:frac|sum|int|sqrt|partial)")

# 조건/논리 패턴
_CONDITIONAL = re.compile(
    r"(?:만약|경우에|조건|~이면|~라면|~한다면|if\b|when\b|unless\b|"
    r"그렇지\s*않으면|아니면|또는|혹은)",
    re.IGNORECASE,
)

# 비교/분석 요청
_COMPARISON = re.compile(
    r"(?:비교|차이점|장단점|트레이드오프|trade-?off|pros?\s*(?:and|&)\s*cons?|versus|vs\.?)",
    re.IGNORECASE,
)


def _count_sentences(text: str) -> int:
    """한국어/영어 문장 수 추정."""
    # 마침표, 물음표, 느낌표로 분리 (단, 소수점/URL 제외)
    sentences = re.split(r'[.!?。]\s+|[.!?。]$|\n\n+', text.strip())
    return max(1, len([s for s in sentences if s.strip()]))


def _count_tokens_approx(text: str) -> int:
    """토큰 수 근사 추정 (한국어: ~1.5 토큰/음절, 영어: ~1.3 토큰/단어)."""
    # 한국어 음절 수
    korean_chars = len(re.findall(r'[\uac00-\ud7af]', text))
    # 영어 단어 수
    ascii_words = len(re.findall(r'[a-zA-Z]+', text))
    return int(korean_chars * 1.5 + ascii_words * 1.3) or 1


def extract_features(text: str) -> Dict[str, float]:
    """프롬프트에서 복잡도 관련 피처를 추출한다."""
    text_len = len(text)
    if text_len == 0:
        return {k: 0.0 for k in [
            "token_count", "sentence_count", "avg_sentence_len",
            "technical_density", "legal_density", "medical_density",
            "multi_step_count", "code_block_count", "math_count",
            "conditional_count", "comparison_count", "question_mark_count",
        ]}

    tokens = _count_tokens_approx(text)
    sentences = _count_sentences(text)

    tech_matches = len(_TECHNICAL_TERMS.findall(text))
    legal_matches = len(_LEGAL_TERMS.findall(text))
    medical_matches = len(_MEDICAL_TERMS.findall(text))

    multi_step = len(_MULTI_STEP.findall(text)) + len(_SEQUENTIAL.findall(text))
    code_blocks = len(_CODE_BLOCK.findall(text))
    math_exprs = len(_MATH_EXPR.findall(text))
    conditionals = len(_CONDITIONAL.findall(text))
    comparisons = len(_COMPARISON.findall(text))
    questions = text.count("?") + text.count("？")

    return {
        "token_count": float(tokens),
        "sentence_count": float(sentences),
        "avg_sentence_len": tokens / sentences,
        "technical_density": tech_matches / max(sentences, 1),
        "legal_density": legal_matches / max(sentences, 1),
        "medical_density": medical_matches / max(sentences, 1),
        "multi_step_count": float(multi_step),
        "code_block_count": float(code_blocks),
        "math_count": float(math_exprs),
        "conditional_count": float(conditionals),
        "comparison_count": float(comparisons),
        "question_mark_count": float(questions),
    }


# ---------------------------------------------------------------------------
# 복잡도 점수 계산 (가중합 + sigmoid 정규화)
# ---------------------------------------------------------------------------

# 피처별 가중치 (총합이 1.0에 가까울 필요 없음, sigmoid로 정규화)
DEFAULT_WEIGHTS: Dict[str, float] = {
    "token_count": 0.003,           # 긴 프롬프트 = 복잡
    "sentence_count": 0.02,         # 문장 많음 = 복잡
    "avg_sentence_len": 0.01,       # 긴 문장 = 복잡
    "technical_density": 0.35,      # 전문 용어 밀도
    "legal_density": 0.30,          # 법률 용어 밀도
    "medical_density": 0.30,        # 의료 용어 밀도
    "multi_step_count": 0.25,       # 다단계 지시
    "code_block_count": 0.20,       # 코드 포함
    "math_count": 0.15,             # 수식 포함
    "conditional_count": 0.15,      # 조건문
    "comparison_count": 0.20,       # 비교/분석
    "question_mark_count": 0.05,    # 질문 수
}

# sigmoid 중심(bias): 이 값 이상이면 0.5 초과 → complex 경향
DEFAULT_BIAS = -1.5


def _sigmoid(x: float) -> float:
    """수치 안정 sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def compute_score(
    features: Dict[str, float],
    weights: Optional[Dict[str, float]] = None,
    bias: float = DEFAULT_BIAS,
) -> float:
    """피처 가중합 → sigmoid → [0, 1] 복잡도 점수."""
    w = weights or DEFAULT_WEIGHTS
    z = bias
    for feat, val in features.items():
        z += w.get(feat, 0.0) * val
    return _sigmoid(z)


# ---------------------------------------------------------------------------
# 복잡도 분류기 설정
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "complexity_routing.yaml"


def load_complexity_config(
    config_path: Optional[str] = None,
) -> Dict[str, Any]:
    """config/complexity_routing.yaml 을 읽는다."""
    import os
    path_str = config_path or os.environ.get("NUFI_COMPLEXITY_CONFIG")
    path = Path(path_str) if path_str else _DEFAULT_CONFIG_PATH
    if not path.is_file():
        logger.debug("Complexity config not found at %s — using defaults", path)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        logger.info("Loaded complexity config from %s", path)
        return data
    except Exception:
        logger.exception("Failed to load complexity config from %s", path)
        return {}


# ---------------------------------------------------------------------------
# 복잡도 분류기 (RouteLLM 호환 인터페이스)
# ---------------------------------------------------------------------------


class ComplexityClassifier:
    """프롬프트 복잡도 기반 모델 라우터.

    Parameters
    ----------
    strong_model : str
        복잡한 요청에 사용할 고성능 모델.
    weak_model : str
        단순한 요청에 사용할 저비용 모델.
    threshold : float
        simple/complex 분기 임계값 (0.0~1.0). 기본 0.5.
    moderate_threshold : float
        simple/moderate 분기 임계값. 기본은 threshold * 0.6.
    weights : dict, optional
        피처별 가중치 오버라이드.
    bias : float
        sigmoid bias 오버라이드.
    config_path : str, optional
        설정 파일 경로.
    """

    def __init__(
        self,
        strong_model: str = "gpt-4o",
        weak_model: str = "gpt-4o-mini",
        threshold: float = 0.5,
        moderate_threshold: Optional[float] = None,
        weights: Optional[Dict[str, float]] = None,
        bias: float = DEFAULT_BIAS,
        config_path: Optional[str] = None,
    ):
        cfg = load_complexity_config(config_path)

        self.strong_model = cfg.get("strong_model", strong_model)
        self.weak_model = cfg.get("weak_model", weak_model)
        self.threshold = cfg.get("threshold", threshold)
        self.moderate_threshold = (
            cfg.get("moderate_threshold")
            or moderate_threshold
            or self.threshold * 0.6
        )
        self.weights = cfg.get("weights") or weights or DEFAULT_WEIGHTS
        self.bias = cfg.get("bias", bias)
        self.enabled = cfg.get("enabled", True)

    def classify(
        self, text: str, requested_model: Optional[str] = None,
    ) -> ComplexityResult:
        """프롬프트 복잡도를 평가하고 모델을 선택한다."""
        original = requested_model or self.strong_model
        t0 = time.monotonic()

        if not self.enabled:
            return ComplexityResult(
                score=0.0,
                label=COMPLEXITY_SIMPLE,
                target_model=original,
                original_model=original,
                latency_ms=0.0,
            )

        features = extract_features(text)
        score = compute_score(features, self.weights, self.bias)

        if score >= self.threshold:
            label = COMPLEXITY_COMPLEX
            target = self.strong_model
        elif score >= self.moderate_threshold:
            label = COMPLEXITY_MODERATE
            target = self.strong_model  # moderate → 안전하게 strong
        else:
            label = COMPLEXITY_SIMPLE
            target = self.weak_model

        elapsed = (time.monotonic() - t0) * 1000

        logger.info(
            "Complexity: score=%.3f label=%s → %s (original=%s)",
            score, label, target, original,
        )

        return ComplexityResult(
            score=score,
            label=label,
            target_model=target,
            original_model=original,
            features=features,
            latency_ms=elapsed,
        )
