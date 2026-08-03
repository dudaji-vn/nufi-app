"""A/B 테스트 프레임워크 — Phase 2 모델 선택 실험 (CMP-293).

실험(Experiment) 단위로 트래픽을 control/treatment 그룹에 분배하고,
모델별 비용·품질·지연 메트릭을 수집하여 최적 라우팅 전략을 검증한다.

설계 원칙:
  - 결정론적 분배: session/user ID 해싱으로 같은 사용자는 같은 그룹
  - 다중 실험 지원: 여러 실험을 동시 실행 가능
  - 메트릭 수집: 비용, 지연, 만족도(옵션) 추적
  - 최소 의존성: 표준 라이브러리만 사용 (외부 A/B 서비스 불필요)
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger("nufi.ab_testing")


# ---------------------------------------------------------------------------
# 실험 그룹 할당
# ---------------------------------------------------------------------------


@dataclass
class ExperimentVariant:
    """실험 변형 (control 또는 treatment)."""
    name: str                        # "control", "treatment_a", etc.
    model: str                       # 해당 변형에 사용할 모델
    weight: float = 0.5             # 트래픽 비율 (0.0 ~ 1.0)


@dataclass
class Assignment:
    """사용자/세션의 실험 그룹 할당 결과."""
    experiment_id: str
    variant: str                     # variant name
    model: str                       # 할당된 모델
    hash_value: float               # 결정론적 해시 (디버깅용)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "variant": self.variant,
            "model": self.model,
            "hash_value": round(self.hash_value, 6),
        }


@dataclass
class ExperimentMetric:
    """실험 메트릭 레코드."""
    experiment_id: str
    variant: str
    model: str
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    quality_score: Optional[float] = None  # 사용자 피드백 기반 (옵션)
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# 실험 정의
# ---------------------------------------------------------------------------


@dataclass
class Experiment:
    """A/B 테스트 실험."""
    id: str
    name: str
    description: str = ""
    enabled: bool = True
    variants: List[ExperimentVariant] = field(default_factory=list)

    def __post_init__(self):
        if not self.variants:
            self.variants = [
                ExperimentVariant("control", "gpt-4o", 0.5),
                ExperimentVariant("treatment", "gpt-4o-mini", 0.5),
            ]


def _deterministic_hash(experiment_id: str, session_id: str) -> float:
    """실험 ID + 세션 ID → [0, 1) 결정론적 해시."""
    h = hashlib.sha256(f"{experiment_id}:{session_id}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


# ---------------------------------------------------------------------------
# A/B 테스트 매니저
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "complexity_routing.yaml"


class ABTestManager:
    """A/B 테스트 실험 관리자.

    Parameters
    ----------
    experiments : list, optional
        실험 목록. None이면 config에서 로드.
    config_path : str, optional
        설정 파일 경로.
    """

    def __init__(
        self,
        experiments: Optional[List[Experiment]] = None,
        config_path: Optional[str] = None,
    ):
        self.experiments: Dict[str, Experiment] = {}
        self._metrics: List[ExperimentMetric] = []

        if experiments:
            for exp in experiments:
                self.experiments[exp.id] = exp
        else:
            self._load_from_config(config_path)

    def _load_from_config(self, config_path: Optional[str] = None) -> None:
        """config/complexity_routing.yaml의 ab_tests 섹션에서 실험 로드."""
        import os
        path_str = config_path or os.environ.get("NUFI_COMPLEXITY_CONFIG")
        path = Path(path_str) if path_str else _DEFAULT_CONFIG_PATH
        if not path.is_file():
            return
        try:
            with open(path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            logger.exception("Failed to load AB test config from %s", path)
            return

        for exp_cfg in cfg.get("ab_tests", []):
            variants = [
                ExperimentVariant(
                    name=v["name"],
                    model=v["model"],
                    weight=v.get("weight", 0.5),
                )
                for v in exp_cfg.get("variants", [])
            ]
            exp = Experiment(
                id=exp_cfg["id"],
                name=exp_cfg.get("name", exp_cfg["id"]),
                description=exp_cfg.get("description", ""),
                enabled=exp_cfg.get("enabled", True),
                variants=variants,
            )
            self.experiments[exp.id] = exp

    def assign(
        self, experiment_id: str, session_id: str,
    ) -> Optional[Assignment]:
        """세션을 실험 그룹에 할당한다.

        Returns None if experiment not found or disabled.
        """
        exp = self.experiments.get(experiment_id)
        if not exp or not exp.enabled:
            return None

        h = _deterministic_hash(experiment_id, session_id)

        # 가중 누적으로 variant 선택
        cumulative = 0.0
        chosen = exp.variants[-1]  # 폴백
        for variant in exp.variants:
            cumulative += variant.weight
            if h < cumulative:
                chosen = variant
                break

        return Assignment(
            experiment_id=experiment_id,
            variant=chosen.name,
            model=chosen.model,
            hash_value=h,
        )

    def record_metric(
        self,
        experiment_id: str,
        variant: str,
        model: str,
        cost_usd: float = 0.0,
        latency_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        quality_score: Optional[float] = None,
    ) -> ExperimentMetric:
        """실험 메트릭을 기록한다."""
        metric = ExperimentMetric(
            experiment_id=experiment_id,
            variant=variant,
            model=model,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            quality_score=quality_score,
        )
        self._metrics.append(metric)
        return metric

    def summary(self, experiment_id: Optional[str] = None) -> Dict[str, Any]:
        """실험 메트릭 요약."""
        metrics = self._metrics
        if experiment_id:
            metrics = [m for m in metrics if m.experiment_id == experiment_id]

        if not metrics:
            return {"total_observations": 0, "variants": {}}

        by_variant: Dict[str, List[ExperimentMetric]] = {}
        for m in metrics:
            key = f"{m.experiment_id}:{m.variant}"
            by_variant.setdefault(key, []).append(m)

        variants = {}
        for key, ms in by_variant.items():
            n = len(ms)
            total_cost = sum(m.cost_usd for m in ms)
            avg_latency = sum(m.latency_ms for m in ms) / n
            total_tokens = sum(m.prompt_tokens + m.completion_tokens for m in ms)
            quality_scores = [m.quality_score for m in ms if m.quality_score is not None]
            avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else None

            variants[key] = {
                "observations": n,
                "total_cost_usd": round(total_cost, 6),
                "avg_cost_usd": round(total_cost / n, 6),
                "avg_latency_ms": round(avg_latency, 2),
                "total_tokens": total_tokens,
                "avg_quality": round(avg_quality, 4) if avg_quality is not None else None,
                "model": ms[0].model,
            }

        return {
            "total_observations": len(metrics),
            "variants": variants,
        }

    def list_experiments(self) -> List[Dict[str, Any]]:
        """등록된 실험 목록."""
        return [
            {
                "id": exp.id,
                "name": exp.name,
                "enabled": exp.enabled,
                "variants": [
                    {"name": v.name, "model": v.model, "weight": v.weight}
                    for v in exp.variants
                ],
            }
            for exp in self.experiments.values()
        ]
