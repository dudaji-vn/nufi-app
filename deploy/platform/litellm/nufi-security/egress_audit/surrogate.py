"""가역 surrogate 발급 + 라운드트립 원복 (M3).

설계: docs/design/gateway/m3-reversible-pseudonymization-spec.md §2·§4 / CMP-76.

- 토큰화 스킴: 결정적(세션 스코프) + 세션별 salt + 불투명 델리미터 surrogate `⟦P1⟧`.
- 라운드트립: pre_call 가명화(mint+Vault 적재) ↔ post_call 원복(Vault 복호 후 정확 치환).
- 스트리밍: 청크 경계로 쪼개진 surrogate 를 경계 버퍼로 홀드 후 완결 시 원복.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from .pipeline import Finding
from .vault import MappingVault

# 가역 대상 약한 PII (spec §1; KR_LOCATION 은 M3 에서 가역으로 승격).
REVERSIBLE_ENTITIES = ("KR_PERSON", "KR_PHONE", "EMAIL", "KR_BRN", "KR_LOCATION")

# entity_type → surrogate 태그(1~2자, 충돌 없게).
TAG_OF: Dict[str, str] = {
    "KR_PERSON": "P",
    "KR_PHONE": "T",
    "EMAIL": "E",
    "KR_BRN": "B",
    "KR_LOCATION": "L",
}
_TYPE_OF_TAG = {v: k for k, v in TAG_OF.items()}

# 델리미터. 기본값은 U+27E6 ⟦ … U+27E7 ⟧ (일반 텍스트/코드에 거의 없음 → 충돌 0).
#
# 환경변수 NUFI_SURROGATE_DELIMS 로 교체 가능하다. 형식은 "<여는>,<닫는>"
# (예: "<,>"). 기본 동작은 바뀌지 않는다.
#
# 왜 필요한가 — 토큰이 그대로 돌아오는지는 이 라이브러리의 성질이 아니라 배포처
# 모델과 프롬프트의 성질이고, 라이브러리는 그 모델을 미리 알 수 없다. 따라서
# 델리미터는 라이브러리를 고치지 않고 바꿀 수 있어야 한다.
#
# 실패했을 때가 문제다. ⟦E1⟧ → E1 처럼 괄호가 벗겨지면 _LENIENT 는 양쪽 괄호를
# 요구하므로 매칭되지 않고, 복원이 조용히 실패한다 — 사용자는 자기 이메일 대신
# "E1" 을 보고, 호출측은 복원되었다고 기록한다.
#
# _LENIENT 를 괄호 없이 넓히는 것은 해법이 아니다 — 맨 E1/P1/T2 는 셀 참조·
# 부품번호 같은 평범한 문자열이므로 정상 텍스트를 손상시킨다. 양쪽 괄호 요구는
# 유지하고, 델리미터 쪽을 배포 환경에 맞게 고를 수 있게 한다.
#
# 측정 이력. 1차(2026-07-29, gemini-2.5-flash, 프롬프트 1종, n=6)에서 ⟦E1⟧ 0/6,
# [[E1]] 2/6, <E1> 6/6 이 나와 기본 델리미터의 결함으로 보고되었으나,
# 2차(2026-07-30, 같은 모델, 프롬프트 7종 — 재작성·요약·번역·표·repeat exactly·
# 한국어·장문, 델리미터 3종)에서 54/54 전부 그대로 반환되어 재현되지 않았다.
# 그 보고는 철회한다. 부분 반환(토큰 일부만 복원 가능)은 두 차수 모두 0건이었다.
#
# n 회 무실패는 보장이 아니다. 호출측은 복원 실패를 가정하지 말고 탐지해야 한다.
_DEFAULT_LB, _DEFAULT_RB = "⟦", "⟧"


def _load_delims() -> tuple[str, str]:
    raw = os.environ.get("NUFI_SURROGATE_DELIMS", "")
    if raw.count(",") == 1:
        left, right = (part.strip() for part in raw.split(","))
        if left and right:
            return left, right
    return _DEFAULT_LB, _DEFAULT_RB


def _compile(lb: str, rb: str) -> tuple[re.Pattern, re.Pattern]:
    exact = re.compile(re.escape(lb) + r"([A-Z]{1,2})(\d+)" + re.escape(rb))
    # 관용 매칭(LLM 이 토큰을 변형: ⟦P1⟧ → [P1] / (P1)). 안전망 폴백용.
    # 양쪽 괄호는 계속 요구한다 — 위 주석 참고.
    opens = "|".join(re.escape(c) for c in dict.fromkeys((lb, "[", "(")))
    closes = "|".join(re.escape(c) for c in dict.fromkeys((rb, "]", ")")))
    lenient = re.compile(f"(?:{opens})" + r"([A-Z]{1,2})(\d+)" + f"(?:{closes})")
    return exact, lenient


LB, RB = _load_delims()
_EXACT, _LENIENT = _compile(LB, RB)
# 미완결 토큰의 최대 길이 상한(스트리밍 홀드 상한). 델리미터 길이를 반영한다.
MAX_SURROGATE_LEN = 14 + len(LB) + len(RB)


def set_delimiters(lb: str, rb: str) -> None:
    """델리미터를 런타임에 교체(주로 테스트용). 정규식도 함께 재컴파일한다."""
    global LB, RB, _EXACT, _LENIENT, MAX_SURROGATE_LEN
    if not lb or not rb:
        raise ValueError("delimiters must both be non-empty")
    LB, RB = lb, rb
    _EXACT, _LENIENT = _compile(lb, rb)
    MAX_SURROGATE_LEN = 14 + len(lb) + len(rb)


def make_surrogate(tag: str, n: int) -> str:
    return f"{LB}{tag}{n}{RB}"


class SurrogateMinter:
    """세션 스코프 결정적 surrogate 발급기(spec §2.3). Vault 가 상태(salt·카운터·매핑) 보유."""

    def __init__(self, vault: MappingVault, session_id: str):
        self.vault = vault
        self.session_id = session_id

    def mint(self, entity_type: str, original: str, ttl: Optional[float] = None) -> str:
        # 세션 스코프 결정성: 같은 (type, original) 은 기존 surrogate 재사용.
        existing = self.vault.find_surrogate(self.session_id, entity_type, original)
        if existing:
            return existing
        tag = TAG_OF.get(entity_type, "X")
        surrogate = make_surrogate(tag, self.vault.next_index(self.session_id, tag))
        self.vault.store(self.session_id, surrogate, entity_type, original, ttl=ttl)
        return surrogate


def pseudonymize(text: str, findings: List[Finding], vault: MappingVault,
                 session_id: str, ttl: Optional[float] = None,
                 reversible: Tuple[str, ...] = REVERSIBLE_ENTITIES) -> Tuple[str, int]:
    """가역 대상 finding 을 surrogate 로 치환(뒤→앞, offset 보존). (변환텍스트, 치환수)."""
    minter = SurrogateMinter(vault, session_id)
    edits = []  # (start, end, surrogate)
    for f in findings:
        if f.entity_type not in reversible:
            continue
        edits.append((f.start, f.end, minter.mint(f.entity_type, f.text, ttl=ttl)))
    out = text
    for start, end, rep in sorted(edits, key=lambda e: -e[0]):
        out = out[:start] + rep + out[end:]
    return out, len(edits)


def _fallback_label(tag: str) -> str:
    et = _TYPE_OF_TAG.get(tag)
    return f"[{et}]" if et else "[REDACTED]"


def deanonymize(text: str, vault: MappingVault, session_id: str,
                lenient: bool = True) -> Tuple[str, dict]:
    """응답 내 surrogate 를 원본으로 무손실 원복. (원복텍스트, 통계).

    안전망: 매핑 없는 잔존 surrogate 는 타입 라벨로 폴백(미원복 노출 차단, spec §4.2).
    """
    stats = {"restored": 0, "fallback": 0}

    def _repl(m: "re.Match") -> str:
        tag, n = m.group(1), m.group(2)
        original = vault.resolve(session_id, make_surrogate(tag, int(n)))
        if original is not None:
            stats["restored"] += 1
            return original
        stats["fallback"] += 1
        return _fallback_label(tag)

    out = _EXACT.sub(_repl, text)
    if lenient and (LB in out or _LENIENT.search(out)):
        out = _LENIENT.sub(_repl, out)
    return out, stats


class StreamingDeanonymizer:
    """스트리밍 원복: surrogate 가 청크 경계로 쪼개져도 경계 버퍼로 홀드 후 원복.

    feed(chunk) 로 청크를 넣고 즉시 방출 가능한 안전 접두를 돌려받는다. 미완결
    surrogate 꼬리는 다음 청크까지 홀드(최대 MAX_SURROGATE_LEN). flush() 로 잔여 방출.
    """

    def __init__(self, vault: MappingVault, session_id: str, lenient: bool = True):
        self.vault = vault
        self.session_id = session_id
        self.lenient = lenient
        self._buf = ""
        self.stats = {"restored": 0, "fallback": 0}

    # 버퍼에 미완결 토큰이 시작될 수 있는 가장 이른 위치(여는 델리미터). 없으면 -1.
    def _earliest_open(self, s: str) -> int:
        idxs = [s.rfind(LB)]
        if self.lenient:
            idxs += [s.rfind("["), s.rfind("(")]
        cands = [i for i in idxs if i != -1]
        return min(cands) if cands else -1

    def feed(self, chunk: str) -> str:
        self._buf += chunk
        open_at = self._earliest_open(self._buf)
        if open_at == -1:
            out, self._buf = self._buf, ""
            return self._restore(out)
        # 여는 델리미터 이후가 이미 닫혔는지(완결됐는지) 확인 → 닫혔으면 그 지점까지 방출 가능.
        tail = self._buf[open_at:]
        closed = (RB in tail) or (self.lenient and ("]" in tail or ")" in tail))
        if closed:
            # 미완결 꼬리가 없으니 전체 처리 가능.
            out, self._buf = self._buf, ""
            return self._restore(out)
        # 미완결 꼬리: open_at 이전은 안전 방출, 이후는 홀드. 홀드 상한 초과 시 강제 방출.
        if len(tail) > MAX_SURROGATE_LEN:
            out, self._buf = self._buf, ""
            return self._restore(out)
        safe, self._buf = self._buf[:open_at], self._buf[open_at:]
        return self._restore(safe)

    def flush(self) -> str:
        out, self._buf = self._buf, ""
        return self._restore(out)

    def _restore(self, text: str) -> str:
        if not text:
            return text
        out, st = deanonymize(text, self.vault, self.session_id, lenient=self.lenient)
        self.stats["restored"] += st["restored"]
        self.stats["fallback"] += st["fallback"]
        return out
