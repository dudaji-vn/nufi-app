"""한국 PII 정규식 + 체크섬 탐지기 (SPEC M2 수용기준 1).

선필터(정규식) → 체크섬 검증으로 오탐 억제(NFR2 지연 전략).
패턴은 config/patterns.yaml 에서 로드(NFR3).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, List, Optional

from .. import checksums


@dataclass
class RawSpan:
    entity_type: str
    text: str
    start: int
    end: int
    score: float
    source: str = "regex"
    # M4 기밀 신호용 부가 메타(없으면 None) — PII/SECRET 경로는 미사용.
    conf_class: Optional[str] = None       # RESTRICTED|CONFIDENTIAL|INTERNAL|PUBLIC
    confidence: Optional[float] = None
    match_meta: Optional[dict] = None


class KoreanPiiDetector:
    def __init__(self, rules: List[dict]):
        self.rules = []
        for r in rules:
            self.rules.append(
                {
                    "name": r["name"],
                    "regex": re.compile(r["regex"]),
                    "checksum": r.get("checksum", "none"),
                    # CMP-103: 구조적/문맥 오탐 제외 (KR_ACCOUNT 정밀화). 미지정 시 no-op.
                    "exclude_match_regex": (
                        re.compile(r["exclude_match_regex"])
                        if r.get("exclude_match_regex")
                        else None
                    ),
                    "exclude_context": list(r.get("exclude_context", [])),
                }
            )

    # 비계좌 문맥 키워드 탐지 시 살펴볼 매치 인접 윈도(자). 운송장/ISBN 라벨이
    # 보통 번호 바로 앞/뒤에 붙으므로 좁게 잡아 과억제를 막는다.
    _CONTEXT_WINDOW = 12

    def detect(self, text: str) -> Iterator[RawSpan]:
        for rule in self.rules:
            for m in rule["regex"].finditer(text):
                matched = m.group(0)
                if not checksums.verify(rule["checksum"], matched):
                    continue
                # CMP-103: 구조적 오탐 제외(ISBN 등 매치 형태 자체로 비계좌).
                exc = rule["exclude_match_regex"]
                if exc is not None and exc.match(matched):
                    continue
                # CMP-103: 인접 비계좌 문맥(운송장/ISBN/도서 등) 제외.
                #   '맨 계좌번호'(키워드 무인접)는 영향 없음 → 강한PII recall 보존.
                if rule["exclude_context"]:
                    lo = max(0, m.start() - self._CONTEXT_WINDOW)
                    hi = min(len(text), m.end() + self._CONTEXT_WINDOW)
                    window = text[lo:hi]
                    if any(kw in window for kw in rule["exclude_context"]):
                        continue
                # 체크섬 통과 = 고신뢰, 없으면 정규식 신뢰도
                score = 0.99 if rule["checksum"] != "none" else 0.85
                yield RawSpan(
                    entity_type=rule["name"],
                    text=matched,
                    start=m.start(),
                    end=m.end(),
                    score=score,
                    source="regex+checksum" if rule["checksum"] != "none" else "regex",
                )
