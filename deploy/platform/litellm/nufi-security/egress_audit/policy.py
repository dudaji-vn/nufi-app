"""정책 엔진 (SPEC M2 수용기준 4): block / redact / pseudonymize / warn + 결정 로그.

엔티티 클래스별 동작은 config/policy.yaml 에서 로드(NFR3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

from .pipeline import Finding, CONF_SOURCES
from . import pseudonymize as ps

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

_CLASS_RANK = {"RESTRICTED": 4, "CONFIDENTIAL": 3, "INTERNAL": 2, "PUBLIC": 1}


@dataclass
class Decision:
    blocked: bool
    actions: List[dict] = field(default_factory=list)   # 엔티티별 결정
    transformed_text: str = ""
    findings: List[dict] = field(default_factory=list)

    @property
    def summary(self) -> dict:
        counts: dict = {}
        for a in self.actions:
            counts[a["action"]] = counts.get(a["action"], 0) + 1
        out = {"blocked": self.blocked, "action_counts": counts,
               "finding_count": len(self.findings)}
        conf = [f for f in self.findings if f.get("source") in CONF_SOURCES]
        if conf:
            classes = [f.get("class") for f in conf if f.get("class")]
            max_class = max(classes, key=lambda c: _CLASS_RANK.get(c, 0)) if classes else None
            by_src = lambda s: sum(1 for f in conf if f.get("source") == s)
            out["confidential_summary"] = {
                "max_class": max_class,
                "keyword_hits": by_src("keyword"),
                "marking_hits": by_src("marking"),
                "edm_struct_hits": by_src("edm_struct"),
                "edm_doc_hits": by_src("edm_doc"),
            }
        return out


class PolicyEngine:
    def __init__(self, policy_path: Optional[str] = None):
        policy_path = policy_path or str(_CONFIG_DIR / "policy.yaml")
        with open(policy_path, "r", encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)
        self.entities = self.cfg.get("entities", {})
        self.default_action = self.cfg.get("default_action", "warn")
        self.blocking_actions = set(self.cfg.get("blocking_actions", ["block"]))
        # 기밀 class→action 보조표(§4.1): 명시 entity 가 없는 CONF_KEYWORD 등급 분기.
        self.conf_class_actions = self.cfg.get("conf_class_actions", {})

    def action_for(self, entity_type: str) -> str:
        ent = self.entities.get(entity_type)
        return ent["action"] if ent else self.default_action

    def severity_for(self, entity_type: str) -> str:
        ent = self.entities.get(entity_type)
        return ent.get("severity", "medium") if ent else "medium"

    def _resolve(self, f: Finding) -> tuple:
        """(action, severity) — entity 우선, 없으면 class 보조표(§4.1)."""
        ent = self.entities.get(f.entity_type)
        if ent:
            return ent["action"], ent.get("severity", "medium")
        cls = getattr(f, "conf_class", None)
        if cls and cls in self.conf_class_actions:
            c = self.conf_class_actions[cls]
            return c.get("action", self.default_action), c.get("severity", "medium")
        return self.default_action, "medium"

    def apply(self, text: str, findings: List[Finding]) -> Decision:
        decision = Decision(blocked=False, findings=[f.to_dict() for f in findings])
        # 텍스트 변환은 뒤에서 앞으로(offset 보존)
        edits = []  # (start, end, replacement)
        for f in findings:
            action, severity = self._resolve(f)
            decision.actions.append({
                "entity_type": f.entity_type, "action": action, "severity": severity,
                "span": [f.start, f.end], "source": f.source, "score": f.score,
            })
            if action in self.blocking_actions:
                decision.blocked = True
            # 기밀 신호는 본문 치환 대상 아님(block=요청 전면 차단, warn=무편집);
            # 정규화 뷰 span 이라 원문 offset 과 어긋날 수 있어 편집 금지(§2.2 메모).
            if f.source in CONF_SOURCES or f.end <= f.start:
                continue
            replacement = self._replacement(action, f)
            if replacement is not None:
                edits.append((f.start, f.end, replacement))

        out = text
        for start, end, rep in sorted(edits, key=lambda e: -e[0]):
            out = out[:start] + rep + out[end:]
        decision.transformed_text = out
        return decision

    @staticmethod
    def _replacement(action: str, f: Finding) -> Optional[str]:
        if action == "redact" or action == "block":
            return ps.redact(f.entity_type)
        if action == "pseudonymize":
            return ps.pseudo_token(f.entity_type, f.text)
        if action == "warn":
            return None  # 텍스트 보존, 경고만
        return None
