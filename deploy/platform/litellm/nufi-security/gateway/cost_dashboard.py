"""실시간 비용 대시보드 — Phase 2 비용 모니터링 (CMP-293).

PII 라우팅 + 복잡도 라우팅의 비용 절감 효과를 실시간 추적하고,
터미널·JSON 포맷으로 비용 분석 리포트를 생성한다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from gateway.pii_router import CostRecord, DEFAULT_COST_TABLE


@dataclass
class RoutingStats:
    """라우팅 경로별 통계."""
    total_requests: int = 0
    pii_routed: int = 0          # PII → 로컬
    complexity_simple: int = 0   # 복잡도 단순 → 저비용
    complexity_complex: int = 0  # 복잡도 복잡 → 고성능
    direct: int = 0              # 직접 라우팅 (분류 미적용)


@dataclass
class CostSavings:
    """비용 절감 분석."""
    actual_cost_usd: float = 0.0
    baseline_cost_usd: float = 0.0      # 모든 요청을 strong 모델로 보냈을 때
    savings_usd: float = 0.0
    savings_pct: float = 0.0
    pii_savings_usd: float = 0.0        # PII 라우팅으로 절약
    complexity_savings_usd: float = 0.0  # 복잡도 라우팅으로 절약


class CostDashboard:
    """실시간 비용 모니터링 대시보드.

    PiiRouter 및 ComplexityClassifier의 비용 레코드를 통합하여
    라우팅 경로별 비용 절감 효과를 분석한다.
    """

    def __init__(
        self,
        cost_table: Optional[Dict[str, Dict[str, float]]] = None,
        baseline_model: str = "gpt-4o",
    ):
        self.cost_table = cost_table or DEFAULT_COST_TABLE
        self.baseline_model = baseline_model
        self._records: List[Dict[str, Any]] = []

    def record(
        self,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        routing_reason: str = "",
        complexity_label: str = "",
        is_local: bool = False,
        latency_ms: float = 0.0,
    ) -> Dict[str, Any]:
        """비용 레코드를 기록한다."""
        actual_cost = self._estimate_cost(model, prompt_tokens, completion_tokens)
        baseline_cost = self._estimate_cost(
            self.baseline_model, prompt_tokens, completion_tokens
        )

        entry = {
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "actual_cost_usd": actual_cost,
            "baseline_cost_usd": baseline_cost,
            "routing_reason": routing_reason,
            "complexity_label": complexity_label,
            "is_local": is_local,
            "latency_ms": latency_ms,
            "timestamp": time.time(),
        }
        self._records.append(entry)
        return entry

    def _estimate_cost(
        self, model: str, prompt_tokens: int, completion_tokens: int,
    ) -> float:
        """모델별 비용 추정."""
        costs = self.cost_table.get(model)
        if not costs:
            for key in self.cost_table:
                if key in model.lower():
                    costs = self.cost_table[key]
                    break
        if not costs:
            costs = self.cost_table.get("local", {"input": 0.0, "output": 0.0})
        return (prompt_tokens * costs["input"]) + (completion_tokens * costs["output"])

    def routing_stats(self) -> RoutingStats:
        """라우팅 경로별 통계."""
        stats = RoutingStats(total_requests=len(self._records))
        for r in self._records:
            reason = r.get("routing_reason", "")
            label = r.get("complexity_label", "")
            if reason == "pii_detected" or r.get("is_local"):
                stats.pii_routed += 1
            elif label == "simple":
                stats.complexity_simple += 1
            elif label in ("complex", "moderate"):
                stats.complexity_complex += 1
            else:
                stats.direct += 1
        return stats

    def cost_savings(self) -> CostSavings:
        """비용 절감 분석."""
        if not self._records:
            return CostSavings()

        actual = sum(r["actual_cost_usd"] for r in self._records)
        baseline = sum(r["baseline_cost_usd"] for r in self._records)
        savings = baseline - actual

        pii_savings = sum(
            r["baseline_cost_usd"] - r["actual_cost_usd"]
            for r in self._records
            if r.get("routing_reason") == "pii_detected" or r.get("is_local")
        )
        complexity_savings = sum(
            r["baseline_cost_usd"] - r["actual_cost_usd"]
            for r in self._records
            if r.get("complexity_label") == "simple"
        )

        return CostSavings(
            actual_cost_usd=round(actual, 6),
            baseline_cost_usd=round(baseline, 6),
            savings_usd=round(savings, 6),
            savings_pct=round((savings / baseline * 100) if baseline > 0 else 0.0, 2),
            pii_savings_usd=round(pii_savings, 6),
            complexity_savings_usd=round(complexity_savings, 6),
        )

    def summary(self) -> Dict[str, Any]:
        """전체 대시보드 요약 (JSON 직렬화 가능)."""
        stats = self.routing_stats()
        savings = self.cost_savings()

        by_model: Dict[str, Dict[str, Any]] = {}
        for r in self._records:
            model = r["model"]
            if model not in by_model:
                by_model[model] = {
                    "requests": 0,
                    "total_cost_usd": 0.0,
                    "total_tokens": 0,
                }
            by_model[model]["requests"] += 1
            by_model[model]["total_cost_usd"] += r["actual_cost_usd"]
            by_model[model]["total_tokens"] += (
                r["prompt_tokens"] + r["completion_tokens"]
            )

        for v in by_model.values():
            v["total_cost_usd"] = round(v["total_cost_usd"], 6)

        return {
            "total_requests": stats.total_requests,
            "routing": {
                "pii_routed": stats.pii_routed,
                "complexity_simple": stats.complexity_simple,
                "complexity_complex": stats.complexity_complex,
                "direct": stats.direct,
            },
            "cost": {
                "actual_usd": savings.actual_cost_usd,
                "baseline_usd": savings.baseline_cost_usd,
                "savings_usd": savings.savings_usd,
                "savings_pct": savings.savings_pct,
                "pii_savings_usd": savings.pii_savings_usd,
                "complexity_savings_usd": savings.complexity_savings_usd,
            },
            "by_model": by_model,
        }

    def render_ascii(self) -> str:
        """터미널용 ASCII 대시보드."""
        s = self.summary()
        stats = s["routing"]
        cost = s["cost"]

        lines = [
            "=" * 60,
            "  NuFi 비용 대시보드 (Phase 2)",
            "=" * 60,
            "",
            f"  총 요청 수:          {s['total_requests']}",
            f"  PII 로컬 라우팅:     {stats['pii_routed']}",
            f"  복잡도 단순 (저비용): {stats['complexity_simple']}",
            f"  복잡도 복잡 (고성능): {stats['complexity_complex']}",
            f"  직접 라우팅:         {stats['direct']}",
            "",
            "-" * 60,
            "  비용 분석",
            "-" * 60,
            f"  실제 비용:           ${cost['actual_usd']:.6f}",
            f"  기준 비용 (all GPT-4o): ${cost['baseline_usd']:.6f}",
            f"  절약 금액:           ${cost['savings_usd']:.6f}",
            f"  절약 비율:           {cost['savings_pct']:.1f}%",
            f"    - PII 라우팅 절약: ${cost['pii_savings_usd']:.6f}",
            f"    - 복잡도 절약:     ${cost['complexity_savings_usd']:.6f}",
            "",
        ]

        if s["by_model"]:
            lines.extend([
                "-" * 60,
                "  모델별 사용량",
                "-" * 60,
            ])
            for model, info in s["by_model"].items():
                lines.append(
                    f"  {model:25s}  {info['requests']:4d} req  "
                    f"${info['total_cost_usd']:.6f}  "
                    f"{info['total_tokens']:6d} tok"
                )

        lines.append("=" * 60)
        return "\n".join(lines)
