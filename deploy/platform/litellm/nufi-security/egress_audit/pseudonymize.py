"""가명화/마스킹 유틸 (M2: 마스킹·결정적 가명화까지. 가역 원복은 M3).

결정적 가명화: HMAC-SHA256(key, value) → 짧은 토큰. 같은 값 → 같은 토큰(참조 무결성).
M3에서 매핑 Vault + Presidio Encrypt/Decrypt로 가역 원복을 구현한다.
"""
from __future__ import annotations

import hashlib
import hmac
import os

# PoC 기본 키. 운영시 환경변수/Vault로 주입(NFR3).
_DEFAULT_KEY = os.environ.get("EGRESS_PSEUDO_KEY", "nufi-egress-poc-key").encode()


def pseudo_token(entity_type: str, value: str, key: bytes = _DEFAULT_KEY) -> str:
    digest = hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:10]
    return f"<{entity_type}_{digest}>"


def redact(entity_type: str) -> str:
    return f"<{entity_type}_REDACTED>"


def mask(value: str, keep_tail: int = 0) -> str:
    """문자/숫자만 *로 가리고 구분자는 유지. keep_tail 만큼 끝자리 노출."""
    chars = list(value)
    maskable = [i for i, c in enumerate(chars) if c.isalnum()]
    keep = set(maskable[len(maskable) - keep_tail:]) if keep_tail else set()
    for i in maskable:
        if i not in keep:
            chars[i] = "*"
    return "".join(chars)
