"""기밀 키워드 / 분류표식 탐지기 (SPEC_M4 §1,§2).

신호원 2종 — 동일 RawSpan 스키마로 파이프라인에 합류:
  - marking : 문서 분류 표식("대외비" 등) — 강신호·고정밀, class 직결.
  - keyword : 회사 고유 기밀어(코드명·미공개 SKU 등) — 운영자 등록 사전.

사전은 config/confidential.yaml 로 외부화(NFR3), 코어는 로드만. 순수 stdlib + PyYAML(NFR4).
매치 원문은 finding.text 에 싣지 않는다(§4.2) — 규칙 name·class 만 운반.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, List, Optional

import yaml

from .korean_pii import RawSpan
from .. import normalize as nz

# 등급 → entity_type (policy.yaml 정렬). keyword 는 class→action 보조표로 분기.
_MARKING_ENTITY = {
    "RESTRICTED": "CONF_MARKING_RESTRICTED",
    "CONFIDENTIAL": "CONF_MARKING_CONFIDENTIAL",
    "INTERNAL": "CONF_MARKING_INTERNAL",
    "PUBLIC": "CONF_MARKING_INTERNAL",
}
_CLASS_RANK = {"RESTRICTED": 4, "CONFIDENTIAL": 3, "INTERNAL": 2, "PUBLIC": 1}


class ConfidentialKeywordDetector:
    """markings + keywords + allowlist 를 로드해 정규화 텍스트에서 매치."""

    def __init__(self, cfg: dict):
        cfg = cfg or {}
        self.ruleset_version = str(cfg.get("ruleset_version", cfg.get("version", "conf-dev")))
        self.default_action = cfg.get("default_conf_action", "warn")
        # 전역 오탐 예외(정규화 토큰 기준)
        self.allowlist = {nz.normalize_token(t) for t in (cfg.get("allowlist", {}) or {}).get("terms", [])}

        self.markings: List[dict] = []
        for m in cfg.get("markings", []) or []:
            self.markings.append({
                "name": m["name"],
                "class": m.get("class", "CONFIDENTIAL"),
                "phrases": list(m.get("phrases", [])),
            })

        self.keywords: List[dict] = []
        for k in cfg.get("keywords", []) or []:
            entry = {
                "name": k["name"],
                "class": k.get("class", "CONFIDENTIAL"),
                "match_mode": k.get("match_mode", "word"),
                "case_sensitive": bool(k.get("case_sensitive", False)),
                "terms": list(k.get("terms", [])),
                "min_len": int(k.get("min_len", 0)),
                "allow_context": [nz.normalize(c) for c in k.get("allow_context", [])],
                "_regexes": None,
            }
            if entry["match_mode"] == "regex":
                flags = 0 if entry["case_sensitive"] else re.IGNORECASE
                entry["_regexes"] = [re.compile(t, flags) for t in entry["terms"]]
            self.keywords.append(entry)

    @classmethod
    def from_path(cls, path: str) -> "ConfidentialKeywordDetector":
        with open(path, "r", encoding="utf-8") as f:
            return cls(yaml.safe_load(f) or {})

    # ---- 매칭 ----
    def detect(self, norm_text: str) -> Iterator[RawSpan]:
        """norm_text 는 nz.normalize() 결과(매칭 뷰)여야 한다."""
        # 공백 삽입 난독화("대 외 비") 흡수용 압축 뷰 (§2.2). 경계검사는 그대로 적용.
        compact = norm_text.replace(" ", "")
        # 1) 분류 표식 (고정밀 강신호)
        for mk in self.markings:
            cls = mk["class"]
            entity = _MARKING_ENTITY.get(cls, "CONF_MARKING_CONFIDENTIAL")
            for ph in mk["phrases"]:
                term = nz.normalize(ph)
                if not term:
                    continue
                hits = list(nz.find_word(norm_text, term, case_sensitive=False))
                if not hits:   # 공백 삽입 변형은 압축 뷰에서 재시도(경계검사 유지)
                    compact_term = term.replace(" ", "")
                    hits = list(nz.find_word(compact, compact_term, case_sensitive=False))
                for s, e in hits:
                    yield self._span(entity, s, e, cls, 0.97, "marking", mk["name"])

        # 2) 회사 고유 기밀어
        for kw in self.keywords:
            cls = kw["class"]
            # allow_context: 예외 문맥이 메시지에 있으면 이 규칙 전체 스킵
            if kw["allow_context"] and any(ctx and ctx in norm_text for ctx in kw["allow_context"]):
                continue
            if kw["match_mode"] == "regex":
                for rx in kw["_regexes"]:
                    for m in rx.finditer(norm_text):
                        s, e = m.span()
                        if e - s < kw["min_len"]:
                            continue
                        if nz.normalize_token(m.group(0)) in self.allowlist:
                            continue
                        yield self._span("CONF_KEYWORD", s, e, cls, 0.9, "keyword", kw["name"])
                continue
            for raw_term in kw["terms"]:
                term = nz.normalize(raw_term)
                if len(term) < max(1, kw["min_len"]):
                    continue
                if nz.normalize_token(term) in self.allowlist:
                    continue
                for s, e in nz.find_word(norm_text, term, case_sensitive=kw["case_sensitive"]):
                    yield self._span("CONF_KEYWORD", s, e, cls, 0.88, "keyword", kw["name"])

    def _span(self, entity: str, s: int, e: int, cls: str, conf: float,
              source: str, rule_name: str) -> RawSpan:
        return RawSpan(
            entity_type=entity, text="", start=s, end=e, score=conf, source=source,
            conf_class=cls, confidence=conf,
            match_meta={"rule": rule_name, "ruleset_version": self.ruleset_version},
        )


def class_rank(cls: Optional[str]) -> int:
    return _CLASS_RANK.get(cls or "", 0)
