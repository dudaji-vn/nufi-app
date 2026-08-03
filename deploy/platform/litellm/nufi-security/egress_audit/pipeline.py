"""탐지 파이프라인: 정규식 선필터 → 체크섬 → NER → 비밀정보, 스팬 병합.

NFR2: 정규식/체크섬은 항상, 모델(NER)은 필요 시. gazetteer 백엔드는 경량.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

import yaml

from . import normalize as nz
from .detectors.korean_pii import KoreanPiiDetector, RawSpan
from .detectors.secrets import SecretsDetector
from .detectors.ner import KoreanNerDetector, MultilingualNerDetector
from .detectors.confidential import ConfidentialKeywordDetector
from .edm import EdmMatcher

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# M4 기밀 신호원 — 결정 로그/정책에서 PII 와 구분.
CONF_SOURCES = {"keyword", "marking", "edm_struct", "edm_doc"}


@dataclass
class Finding:
    entity_type: str
    text: str
    start: int
    end: int
    score: float
    source: str
    # M4 부가 메타(기밀 finding 만). PII/SECRET 는 None.
    conf_class: Optional[str] = None
    confidence: Optional[float] = None
    match_meta: Optional[dict] = None

    def __repr__(self) -> str:
        parts = [f"entity_type={self.entity_type!r}", f"text={self.text!r}",
                 f"start={self.start}", f"end={self.end}", f"score={self.score:.2f}"]
        if self.source != "ner:gazetteer":
            parts.append(f"source={self.source!r}")
        return f"Finding({', '.join(parts)})"

    def to_dict(self) -> dict:
        d = asdict(self)
        # 기밀 finding: 매치 원문 비기록(§4.2) — text 제거, class 키로 노출.
        if self.source in CONF_SOURCES:
            d["text"] = ""
        cls = d.pop("conf_class", None)
        if cls is not None:
            d["class"] = cls
        if d.get("confidence") is None:
            d.pop("confidence", None)
        if d.get("match_meta") is None:
            d.pop("match_meta", None)
        return d


def _overlaps(a: RawSpan, b: RawSpan) -> bool:
    return a.start < b.end and b.start < a.end


class DetectionPipeline:
    def __init__(self, patterns_path: Optional[str] = None, ner_backend: str = "auto",
                 enable_ner: bool = True, model_id: Optional[str] = None,
                 confidential_path: Optional[str] = None, edm_index_path: Optional[str] = None,
                 enable_confidential: bool = True, location_union: bool = False,
                 person_union: bool = False,
                 enable_multilingual_ner: bool = False,
                 multilingual_model_id: Optional[str] = None):
        patterns_path = patterns_path or str(_CONFIG_DIR / "patterns.yaml")
        with open(patterns_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.pii = KoreanPiiDetector(cfg.get("korean_pii", []))
        self.secrets = SecretsDetector(cfg.get("secrets", []))
        # location_union(CMP-222 P3): 주소 채널만 모델 백엔드 ∪ 확장 규칙(P2) 유니온.
        # 운영에서 게이트웨이가 파이프라인을 내부 구성하므로 kwarg 미도달 시 env 로도
        # 비활성화한다(M5_LOCATION_UNION=0). v0.5.0부터 기본 on(CMP-315 승인).
        # gazetteer 백엔드는 no-op.
        env_loc_union = os.environ.get("M5_LOCATION_UNION", "1").strip().lower() \
            not in ("0", "false", "no", "off")
        # person_union(CMP-236): 인명 채널만 모델 백엔드 ∪ 규칙(경칭/직함/문맥 게이팅) 유니온.
        # KR_LOCATION 유니온과 동일 플레이북. v0.5.0부터 기본 on(CMP-315 승인).
        # env M5_PERSON_UNION=0 으로 비활성화 가능.
        env_per_union = os.environ.get("M5_PERSON_UNION", "1").strip().lower() \
            not in ("0", "false", "no", "off")
        self.ner = KoreanNerDetector(
            backend=ner_backend, model_id=model_id,
            location_union=location_union or env_loc_union,
            person_union=person_union or env_per_union) if enable_ner else None

        # CMP-309: 다국어 NER — 영어/다국어 텍스트용. env M5_MULTILINGUAL_NER=1 로도 활성화.
        env_ml_ner = os.environ.get("M5_MULTILINGUAL_NER", "").strip().lower() \
            in ("1", "true", "yes", "on")
        self.multilingual_ner = None
        if (enable_multilingual_ner or env_ml_ner) and enable_ner:
            try:
                self.multilingual_ner = MultilingualNerDetector(
                    model_id=multilingual_model_id)
            except Exception:
                pass  # 모델 미가용 시 한국어 NER 만 사용(폴백)

        # --- M4 기밀 탐지 ---
        self.confidential = None
        self.edm = None
        self.conf_ruleset_version = None
        if enable_confidential:
            conf_path = confidential_path or str(_CONFIG_DIR / "confidential.yaml")
            if Path(conf_path).exists():
                self.confidential = ConfidentialKeywordDetector.from_path(conf_path)
                self.conf_ruleset_version = self.confidential.ruleset_version
            edm_path = edm_index_path or str(_CONFIG_DIR / "edm" / "index.json")
            self.edm = EdmMatcher.from_file(edm_path)

    @property
    def ner_backend(self) -> str:
        return self.ner.backend_name if self.ner else "disabled"

    @property
    def ner_pool_config(self):
        """모델 백엔드 동시성 풀 설정(CMP-127). gazetteer/disabled 는 None."""
        return self.ner.pool_config if self.ner else None

    def analyze(self, text: str) -> List[Finding]:
        spans: List[RawSpan] = []
        # 1) 결정적 탐지 우선(체크섬·비밀정보) — 병합 시 우선권
        spans.extend(self.pii.detect(text))
        spans.extend(self.secrets.detect(text))
        # 2) NER 보완 — 언어 기반 라우팅(CMP-309)
        if self.ner is not None or self.multilingual_ner is not None:
            lang = nz.detect_language(text) if self.multilingual_ner else "ko"
            if lang == "ko":
                # 한국어 → KoELECTRA/gazetteer
                if self.ner is not None:
                    spans.extend(self.ner.detect(text))
            elif lang == "en":
                # 영어 → 다국어 NER
                if self.multilingual_ner is not None:
                    spans.extend(self.multilingual_ner.detect(text))
                elif self.ner is not None:
                    spans.extend(self.ner.detect(text))  # 폴백
            else:
                # mixed → 양쪽 모두 실행
                if self.ner is not None:
                    spans.extend(self.ner.detect(text))
                if self.multilingual_ner is not None:
                    spans.extend(self.multilingual_ner.detect(text))
        merged = self._merge(spans)
        findings = [Finding(s.entity_type, s.text, s.start, s.end, round(s.score, 3), s.source)
                    for s in merged]
        # 3) M4 기밀 신호(별도 — PII 와 병합 dedup 하지 않음)
        findings.extend(self._confidential(text))
        return findings

    def _confidential(self, text: str) -> List[Finding]:
        """키워드/표식 선필터 → EDM 후단 (NFR2). 정규화 뷰에서 매칭."""
        out: List[Finding] = []
        if self.confidential is None and (self.edm is None or self.edm.empty):
            return out
        norm = nz.normalize(text)
        if self.confidential is not None:
            seen: set = set()
            for s in self.confidential.detect(norm):
                key = (s.entity_type, s.start, s.end, s.source)
                if key in seen:
                    continue
                seen.add(key)
                out.append(Finding(s.entity_type, "", s.start, s.end,
                                   round(s.score, 3), s.source,
                                   conf_class=s.conf_class, confidence=s.confidence,
                                   match_meta=s.match_meta))
        if self.edm is not None and not self.edm.empty:
            for m in self.edm.match(norm):
                out.append(Finding(m["entity_type"], "", 0, 0,
                                   round(m["confidence"], 3), m["source"],
                                   conf_class=m["class"], confidence=m["confidence"],
                                   match_meta=m["match_meta"]))
        return out

    @staticmethod
    def _merge(spans: List[RawSpan]) -> List[RawSpan]:
        """겹치는 스팬은 (점수, 길이) 우선으로 하나만 남긴다."""
        ordered = sorted(spans, key=lambda s: (-s.score, -(s.end - s.start), s.start))
        kept: List[RawSpan] = []
        for s in ordered:
            if any(_overlaps(s, k) for k in kept):
                continue
            kept.append(s)
        return sorted(kept, key=lambda s: s.start)
