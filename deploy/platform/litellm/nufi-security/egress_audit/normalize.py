"""한국어/혼용 텍스트 정규화 (SPEC_M4 §2.2).

기밀 키워드·표식·EDM 매칭 정확도를 위해 매칭 전에 통과시키는 정규화 파이프.
순수 stdlib (NFR4). 외부 호출 0 (NFR1).

설계 메모: 정규화는 매칭용 *뷰*를 만든다. 정규화 후 좌표(span)는 원문과 다를 수 있으나,
기밀 finding 은 본문 치환(redact) 대상이 아니라(block=요청 전면 차단, warn=무편집)
span 은 감사 참고용으로만 쓰인다(§4.2: 매치 위치만, 원문 비기록).
"""
from __future__ import annotations

import re
import unicodedata

# 제로폭/서식 문자 (조사·자모 변형 회피용 삽입 흔히 사용)
_ZERO_WIDTH = "".join([
    "​",  # ZERO WIDTH SPACE
    "‌",  # ZERO WIDTH NON-JOINER
    "‍",  # ZERO WIDTH JOINER
    "﻿",  # ZERO WIDTH NO-BREAK SPACE
    "­",  # SOFT HYPHEN
])
_ZERO_WIDTH_RE = re.compile("[" + re.escape(_ZERO_WIDTH) + "]")

# 중점/유사 구분기호 → 통일 제거 대상 (예: "대·외·비")
_MIDDOT_RE = re.compile(r"[·•‧・･]")
# 다양한 하이픈/대시 → ASCII '-'
_HYPHEN_RE = re.compile(r"[‐‑‒–—―−－]")
# 연속 공백류 → 단일 공백
_WS_RE = re.compile(r"\s+")

# 한글 음절 + 영숫자 = '단어 문자'(경계 판정용)
_WORDCHAR_RE = re.compile(r"[0-9A-Za-z가-힣]")
_HANGUL_RE = re.compile(r"[가-힣]")


def detect_language(text: str) -> str:
    """텍스트의 주 언어를 Unicode 기반으로 판별 (CMP-309).

    Hangul 비율 기준:
      > 0.3  → "ko"
      < 0.05 → "en"
      그 외   → "mixed" (양쪽 NER 모두 실행)

    오버헤드 < 1ms (순수 stdlib, 정규식 카운트).
    """
    if not text:
        return "en"
    total = len(text)
    hangul_count = len(_HANGUL_RE.findall(text))
    ratio = hangul_count / total
    if ratio > 0.3:
        return "ko"
    if ratio < 0.05:
        return "en"
    return "mixed"


def normalize(text: str, *, collapse_ws: bool = True, drop_middot: bool = True) -> str:
    """매칭용 정규화 뷰를 만든다.

    NFC 결합 → 제로폭 제거 → 하이픈/중점 통일 → (선택) 공백 정리.
    drop_middot=True 면 중점을 제거해 "대·외·비"→"대외비" 흡수.
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text)
    t = _ZERO_WIDTH_RE.sub("", t)
    t = _HYPHEN_RE.sub("-", t)
    if drop_middot:
        t = _MIDDOT_RE.sub("", t)
    else:
        t = _MIDDOT_RE.sub("·", t)
    if collapse_ws:
        t = _WS_RE.sub(" ", t).strip()
    return t


def normalize_token(value: str) -> str:
    """EDM 셀/토큰 정규화 — 내부 공백까지 제거하고 casefold.

    "강 남 구"·"강남구"·"강남 구" 를 동일 키로 만든다. 영문은 casefold.
    """
    if value is None:
        return ""
    t = normalize(value, collapse_ws=True, drop_middot=True)
    t = t.replace(" ", "")
    return t.casefold()


def is_wordchar(ch: str) -> bool:
    return bool(_WORDCHAR_RE.match(ch))


# ---------------------------------------------------------------------------
# 프롬프트 인젝션 탐지용 정규화 (Phase 1 — CMP-292)
# ---------------------------------------------------------------------------

# Fullwidth ASCII 범위 (U+FF01 ~ U+FF5E) → ASCII (U+0021 ~ U+007E)
_FULLWIDTH_OFFSET = 0xFEE0  # ord('！') - ord('!')

# 한글 자모 → 음절 재조합 (조합형 우회 탐지)
# NFC 만으로 부족한 경우: 사용자가 공백/비가시 문자를 자모 사이에 삽입
_JAMO_INITIAL = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JAMO_MEDIAL = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JAMO_FINAL = "ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"

# Compatibility Jamo (U+3131..U+3163) → Conjoining Jamo mapping for reassembly
_COMPAT_INITIAL_MAP = {
    'ㄱ': 0, 'ㄲ': 1, 'ㄴ': 2, 'ㄷ': 3, 'ㄸ': 4, 'ㄹ': 5,
    'ㅁ': 6, 'ㅂ': 7, 'ㅃ': 8, 'ㅅ': 9, 'ㅆ': 10, 'ㅇ': 11,
    'ㅈ': 12, 'ㅉ': 13, 'ㅊ': 14, 'ㅋ': 15, 'ㅌ': 16, 'ㅍ': 17, 'ㅎ': 18,
}
_COMPAT_MEDIAL_MAP = {
    'ㅏ': 0, 'ㅐ': 1, 'ㅑ': 2, 'ㅒ': 3, 'ㅓ': 4, 'ㅔ': 5,
    'ㅕ': 6, 'ㅖ': 7, 'ㅗ': 8, 'ㅘ': 9, 'ㅙ': 10, 'ㅚ': 11,
    'ㅛ': 12, 'ㅜ': 13, 'ㅝ': 14, 'ㅞ': 15, 'ㅟ': 16, 'ㅠ': 17,
    'ㅡ': 18, 'ㅢ': 19, 'ㅣ': 20,
}
_COMPAT_FINAL_MAP = {
    'ㄱ': 1, 'ㄲ': 2, 'ㄳ': 3, 'ㄴ': 4, 'ㄵ': 5, 'ㄶ': 6,
    'ㄷ': 7, 'ㄹ': 8, 'ㄺ': 9, 'ㄻ': 10, 'ㄼ': 11, 'ㄽ': 12,
    'ㄾ': 13, 'ㄿ': 14, 'ㅀ': 15, 'ㅁ': 16, 'ㅂ': 17, 'ㅄ': 18,
    'ㅅ': 19, 'ㅆ': 20, 'ㅇ': 21, 'ㅈ': 22, 'ㅊ': 23, 'ㅋ': 24,
    'ㅌ': 25, 'ㅍ': 26, 'ㅎ': 27,
}

# 자모 문자 범위
_JAMO_RE = re.compile(r"[ㄱ-ㅎㅏ-ㅣ]")


def _reassemble_jamo(text: str) -> str:
    """분리된 자모(ㅌㅏㄹㅗㄱ)를 한글 음절(탈옥)로 재조합.

    공백·비가시 문자가 자모 사이에 삽입된 우회를 탐지하기 위해
    먼저 자모만 추출하여 재조합한 뒤 원문의 자모 구간을 치환한다.
    """
    if not _JAMO_RE.search(text):
        return text

    result: list[str] = []
    i = 0
    chars = list(text)
    n = len(chars)

    while i < n:
        ch = chars[i]
        # 초성 후보
        if ch in _COMPAT_INITIAL_MAP:
            # 뒤쪽에서 중성을 찾는다 (공백/비가시 문자 건너뜀)
            j = i + 1
            while j < n and (chars[j] in _ZERO_WIDTH or chars[j] == ' '):
                j += 1
            if j < n and chars[j] in _COMPAT_MEDIAL_MAP:
                initial = _COMPAT_INITIAL_MAP[ch]
                medial = _COMPAT_MEDIAL_MAP[chars[j]]
                # 종성 후보
                k = j + 1
                while k < n and (chars[k] in _ZERO_WIDTH or chars[k] == ' '):
                    k += 1
                final_val = 0
                end = j + 1
                if k < n and chars[k] in _COMPAT_FINAL_MAP:
                    # 종성 뒤에 중성이 오면 이 종성은 다음 음절의 초성 → 종성 없음
                    m = k + 1
                    while m < n and (chars[m] in _ZERO_WIDTH or chars[m] == ' '):
                        m += 1
                    if m < n and chars[m] in _COMPAT_MEDIAL_MAP:
                        # 종성이 아니라 다음 음절의 초성
                        end = j + 1
                    else:
                        final_val = _COMPAT_FINAL_MAP[chars[k]]
                        end = k + 1
                syllable = chr(0xAC00 + initial * 21 * 28 + medial * 28 + final_val)
                result.append(syllable)
                i = end
                continue
        result.append(ch)
        i += 1

    return "".join(result)


def normalize_for_injection(text: str) -> str:
    """프롬프트 인젝션 탐지 전 적용하는 공격적 정규화.

    1. NFKC 정규화 (fullwidth → halfwidth, 호환 문자 통일)
    2. 제로폭 문자 제거
    3. 자모 재조합 (ㅌㅏㄹㅗㄱ → 탈옥)
    4. 연속 공백 정리
    """
    if not text:
        return ""
    t = _ZERO_WIDTH_RE.sub("", text)
    t = _reassemble_jamo(t)
    t = unicodedata.normalize("NFKC", t)
    t = _WS_RE.sub(" ", t).strip()
    return t


def find_word(text: str, term: str, *, case_sensitive: bool = False,
              max_josa: int = 3):
    """정규화된 text 에서 term 의 한국어 단어경계 매치 위치를 yield.

    - 좌경계: 앞 문자가 단어문자가 아니어야 함(부분어 충돌 방지).
    - 우경계(한글 term): 등록어 뒤 0~max_josa 음절의 조사 후보 허용,
      그 다음이 단어문자가 아니면 매치(예: "오로라는/오로라의" → "오로라").
    - 우경계(영문 term): 바로 뒤가 영숫자가 아니어야 매치(부분어 회피).
    yield (start, end) — end 는 등록어 끝(조사 미포함).
    """
    if not term:
        return
    hay = text if case_sensitive else text.casefold()
    needle = term if case_sensitive else term.casefold()
    has_hangul = bool(_HANGUL_RE.search(term))
    n = len(needle)
    i = 0
    while True:
        idx = hay.find(needle, i)
        if idx < 0:
            return
        i = idx + 1
        # 좌경계
        if idx > 0 and is_wordchar(text[idx - 1]):
            continue
        end = idx + n
        if has_hangul:
            # 조사 후보(한글) 최대 max_josa 음절 소비 후 경계 확인
            j = end
            josa = 0
            while j < len(text) and josa < max_josa and _HANGUL_RE.match(text[j]):
                j += 1
                josa += 1
            # 조사 소비 뒤가 여전히 단어문자(영숫자/추가 한글)면 부분어 → 거름
            if j < len(text) and is_wordchar(text[j]):
                # 단, 모두 한글이고 max_josa 도달이면 조사로 간주하고 통과시키지 않음(보수적)
                continue
            yield (idx, end)
        else:
            if end < len(text) and (text[end].isalnum()):
                continue
            yield (idx, end)
