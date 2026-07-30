"""한국 식별번호 체크섬 검증기. 정규식 선필터의 오탐(false positive)을 줄인다.

순수 stdlib. 외부 의존 없음(NFR1).
"""
from __future__ import annotations

_DIGITS = str.maketrans("", "", "-  \t")


def _only_digits(value: str) -> str:
    return value.translate(_DIGITS)


def validate_rrn(value: str) -> bool:
    """주민등록번호/외국인등록번호 13자리 체크섬.

    가중치 [2,3,4,5,6,7,8,9,2,3,4,5], 검증숫자 = (11 - sum%11) % 10.
    """
    d = _only_digits(value)
    if len(d) != 13 or not d.isdigit():
        return False
    weights = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]
    total = sum(int(d[i]) * weights[i] for i in range(12))
    check = (11 - (total % 11)) % 10
    return check == int(d[12])


def validate_brn(value: str) -> bool:
    """사업자등록번호 10자리 체크섬.

    가중치 [1,3,7,1,3,7,1,3,5], 9번째 자리는 *5 후 십의자리 보정.
    """
    d = _only_digits(value)
    if len(d) != 10 or not d.isdigit():
        return False
    weights = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    total = sum(int(d[i]) * weights[i] for i in range(9))
    total += (int(d[8]) * 5) // 10
    check = (10 - (total % 10)) % 10
    return check == int(d[9])


def validate_luhn(value: str) -> bool:
    """신용카드 Luhn(mod-10) 검증. 13~19자리."""
    d = _only_digits(value)
    if not d.isdigit() or not (13 <= len(d) <= 19):
        return False
    total = 0
    parity = len(d) % 2
    for i, ch in enumerate(d):
        n = int(ch)
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


VALIDATORS = {
    "rrn": validate_rrn,
    "brn": validate_brn,
    "luhn": validate_luhn,
    "none": lambda _v: True,
}


def verify(checksum: str, value: str) -> bool:
    return VALIDATORS.get(checksum, VALIDATORS["none"])(value)
