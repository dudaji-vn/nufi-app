"""비밀정보(자격증명) 탐지기 (SPEC M2 수용기준 3).

기본: config/patterns.yaml 의 키 패턴 + Shannon 엔트로피 휴리스틱 (순수 stdlib).
선택: detect-secrets(Apache-2.0) 설치 시 플러그인 스캔을 병행.
  ※ TruffleHog(AGPL)은 인라인 금지(NFR4) — 사용하지 않음.
"""
from __future__ import annotations

import math
import re
from typing import Iterator, List

from .korean_pii import RawSpan


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


# 엔트로피 후보 토큰(긴 base64/hex 류)
_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9+/=_\-])([A-Za-z0-9+/=_\-]{20,})(?![A-Za-z0-9+/=_\-])")


class SecretsDetector:
    def __init__(self, rules: List[dict], entropy_threshold: float = 4.3,
                 use_detect_secrets: bool = True):
        self.rules = [
            {"name": r["name"], "regex": re.compile(r["regex"])} for r in rules
        ]
        self.entropy_threshold = entropy_threshold
        self._ds = None
        if use_detect_secrets:
            self._ds = self._try_load_detect_secrets()

    @staticmethod
    def _try_load_detect_secrets():
        try:  # 선택 의존(NFR4 호환: Apache-2.0)
            from detect_secrets.core.scan import scan_line  # type: ignore
            return scan_line
        except Exception:
            return None

    def detect(self, text: str) -> Iterator[RawSpan]:
        seen: set[tuple[int, int]] = set()

        # 1) 명시 키 패턴
        for rule in self.rules:
            for m in rule["regex"].finditer(text):
                # 그룹 1이 있으면 그 위치(키 값)를 우선
                if m.groups():
                    s, e = m.span(1)
                else:
                    s, e = m.span(0)
                if (s, e) in seen:
                    continue
                seen.add((s, e))
                yield RawSpan("SECRET", m.group(0), m.start(), m.end(), 0.95,
                              source=f"pattern:{rule['name']}")

        # 2) 고엔트로피 토큰 (키 패턴에 안 걸린 것만)
        for m in _TOKEN_RE.finditer(text):
            token = m.group(1)
            if any(s <= m.start(1) < e for (s, e) in seen):
                continue
            ent = shannon_entropy(token)
            if ent >= self.entropy_threshold and len(token) >= 24:
                seen.add(m.span(1))
                yield RawSpan("SECRET", token, m.start(1), m.end(1),
                              min(0.9, 0.6 + (ent - self.entropy_threshold) / 5),
                              source=f"entropy:{ent:.2f}")

        # 3) detect-secrets (설치 시) — 보강
        if self._ds is not None:
            try:
                for secret in self._ds(text):  # type: ignore
                    val = getattr(secret, "secret_value", None)
                    if not val:
                        continue
                    idx = text.find(val)
                    if idx < 0 or (idx, idx + len(val)) in seen:
                        continue
                    seen.add((idx, idx + len(val)))
                    yield RawSpan("SECRET", val, idx, idx + len(val), 0.97,
                                  source=f"detect-secrets:{getattr(secret,'type','?')}")
            except Exception:
                pass
