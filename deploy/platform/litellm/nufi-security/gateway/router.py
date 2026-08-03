"""라우팅 + public/private 판정 (SPEC M1 기준 1·3).

config/routing.yaml 에서 라우트·백엔드·egress 분류를 로드(NFR3).
private 기본, 실패 시 public 폴백.

CMP-247: PII 감지 시 로컬 모델 강제 라우팅 (LLM 라우팅 Phase 1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@dataclass
class RouteDecision:
    requested_model: str
    backend: str
    provider: str
    egress_class: str          # public | private
    api_base: Optional[str]
    is_fallback: bool
    pii_routed: bool = False   # CMP-247: PII 감지로 로컬 강제 라우팅 여부
    pii_entity_types: List[str] = field(default_factory=list)

    @property
    def is_public(self) -> bool:
        return self.egress_class == "public"


@dataclass
class PIIRoutingConfig:
    """PII 기반 라우팅 설정 (CMP-247)."""
    enabled: bool = False
    local_backend: str = "private-llm"
    entity_types: List[str] = field(default_factory=list)  # 빈 리스트 = 모든 엔티티


class Router:
    def __init__(self, routing_path: Optional[str] = None):
        routing_path = routing_path or str(_CONFIG_DIR / "routing.yaml")
        with open(routing_path, "r", encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)
        self.routes = self.cfg.get("routes", {})
        self.backends = self.cfg.get("backends", {})
        self.provider_egress = self.cfg.get("provider_egress", {})
        # CMP-247: PII 라우팅 설정 로드
        pii_cfg = self.cfg.get("pii_routing", {})
        self.pii_routing = PIIRoutingConfig(
            enabled=pii_cfg.get("enabled", False),
            local_backend=pii_cfg.get("local_backend", "private-llm"),
            entity_types=pii_cfg.get("entity_types") or [],
        )

    def _backend_decision(self, requested_model: str, backend: str,
                          is_fallback: bool, *, pii_routed: bool = False,
                          pii_entity_types: Optional[List[str]] = None) -> RouteDecision:
        b = self.backends.get(backend, {})
        provider = b.get("provider", "unknown")
        egress = b.get("egress_class") or self.provider_egress.get(provider, "public")
        return RouteDecision(requested_model, backend, provider, egress,
                             b.get("api_base"), is_fallback,
                             pii_routed=pii_routed,
                             pii_entity_types=pii_entity_types or [])

    def resolve(self, requested_model: str, force_fallback: bool = False) -> RouteDecision:
        """기본은 primary(private). force_fallback 또는 폴백 호출 시 public."""
        route = self.routes.get(requested_model)
        if route is None:
            # 라우트 미정의 → 모델명을 백엔드로 직접 취급
            return self._backend_decision(requested_model, requested_model, force_fallback)
        backend = route["fallback"] if force_fallback else route["primary"]
        return self._backend_decision(requested_model, backend, force_fallback)

    def resolve_for_pii(self, requested_model: str,
                        detected_entity_types: List[str]) -> Optional[RouteDecision]:
        """PII 감지 시 로컬 백엔드로 강제 라우팅 (CMP-247).

        PII 라우팅이 비활성이거나 감지된 엔티티가 대상이 아니면 None 반환.
        """
        if not self.pii_routing.enabled:
            return None
        if not detected_entity_types:
            return None
        # entity_types 필터가 설정되어 있으면 해당 타입만 대상
        if self.pii_routing.entity_types:
            matched = [e for e in detected_entity_types
                       if e in self.pii_routing.entity_types]
            if not matched:
                return None
            detected_entity_types = matched
        return self._backend_decision(
            requested_model, self.pii_routing.local_backend,
            is_fallback=False, pii_routed=True,
            pii_entity_types=detected_entity_types)

    def fallback_of(self, requested_model: str) -> Optional[RouteDecision]:
        route = self.routes.get(requested_model)
        if not route or "fallback" not in route:
            return None
        return self._backend_decision(requested_model, route["fallback"], True)
