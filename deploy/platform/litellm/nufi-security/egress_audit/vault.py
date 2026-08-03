"""매핑 Vault (M3): surrogate ↔ 원본 PII 매핑을 암호화 보관.

설계: docs/design/gateway/m3-reversible-pseudonymization-spec.md §3 / CMP-76.

핵심 불변식:
- 원본 평문은 어디에도 평문 저장하지 않는다. 가명화 즉시 AES-256-GCM 암호화.
- 봉투암호화: 세션 DEK 로 원본 암호화, KEK 로 DEK 봉인(at-rest 평문 키 0).
- 역방향 중복판정은 lookup_key_hash(HMAC) 로 — 원본 노출 없이 같은 원본→기존 surrogate.
- 세션 파티션 + 짧은 TTL + 확정 삭제(secure wipe). 임의 덤프 API 미제공.
- 외부 호출 0(NFR1): 키소스/암복호 전부 로컬. 외부 KMS 미사용.

`cryptography`(AES-256-GCM) 미설치 환경에서도 import 가 깨지지 않도록 지연 처리하되,
Vault 사용 시점에 명확히 실패시킨다(평문 폴백 금지 — at-rest 암호화는 보안 불변식).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore
    _HAS_AESGCM = True
except Exception:  # pragma: no cover - 미설치 환경
    AESGCM = None  # type: ignore
    _HAS_AESGCM = False


# ── 키소스 (KEK) ────────────────────────────────────────────────────────────
# 운영: EGRESS_VAULT_KEK 로 32B 키 주입(hex64 또는 base64). 평문 키 디스크 미저장.
# PoC: 미주입 시 부팅마다 휘발성 랜덤 KEK 생성(프로세스 재시작 시 기존 매핑 복호 불가
#      = 안전한 실패). 운영 전 keyring/HashiCorp Vault 주입 강제(spec §5.1).
def load_kek(raw: Optional[str] = None) -> bytes:
    raw = raw if raw is not None else os.environ.get("EGRESS_VAULT_KEK")
    if not raw:
        return os.urandom(32)  # 휘발성 PoC KEK
    raw = raw.strip()
    try:
        if len(raw) == 64:
            return bytes.fromhex(raw)
        key = base64.b64decode(raw)
    except Exception as e:  # pragma: no cover
        raise ValueError(f"EGRESS_VAULT_KEK 디코드 실패: {e}") from e
    if len(key) != 32:
        raise ValueError("EGRESS_VAULT_KEK 는 32바이트(AES-256) 여야 함")
    return key


@dataclass
class VaultEntry:
    surrogate: str
    session_id: str
    entity_type: str
    ciphertext: bytes          # AES-256-GCM(original), nonce 선두 12B 포함
    dek_id: str
    created_at: float
    expires_at: float
    lookup_key_hash: bytes     # HMAC(session_salt, entity_type||original)


@dataclass
class _Session:
    salt: bytes
    dek_id: str
    wrapped_dek: bytes         # KEK(AES-GCM)(dek), nonce 선두 12B
    entries: Dict[str, VaultEntry] = field(default_factory=dict)   # surrogate -> entry
    by_lookup: Dict[bytes, str] = field(default_factory=dict)      # lookup_hash -> surrogate
    counters: Dict[str, int] = field(default_factory=dict)         # tag -> 순번
    last_active: float = 0.0


class MappingVault:
    """in-memory 매핑 Vault(기본 백엔드). 게이트웨이 훅 프로세스 내 단일 인스턴스.

    영속(Redis/SQLite)은 동일 인터페이스로 후속 확장(spec §3.2 Could). PoC 는 in-memory.
    """

    def __init__(self, kek: Optional[bytes] = None, default_ttl: float = 1800.0,
                 hard_cap: float = 86400.0, time_fn: Callable[[], float] = time.time,
                 audit_sink: Optional[Callable[[dict], None]] = None):
        if not _HAS_AESGCM:
            raise RuntimeError(
                "MappingVault 는 AES-256-GCM(cryptography) 필요 — "
                "`pip install cryptography`. 평문 저장 폴백은 보안상 금지.")
        self._kek = kek if kek is not None else load_kek()
        self.default_ttl = float(default_ttl)
        self.hard_cap = float(hard_cap)
        self._now = time_fn
        self._sessions: Dict[str, _Session] = {}
        self._audit_log: list = []        # append-only(원본 평문 미기록)
        self._audit_sink = audit_sink

    # ── 세션 수명주기 ──────────────────────────────────────────────────────
    def _session(self, session_id: str) -> _Session:
        s = self._sessions.get(session_id)
        if s is None:
            dek = os.urandom(32)
            dek_id = uuid.uuid4().hex[:12]
            s = _Session(salt=os.urandom(16), dek_id=dek_id,
                         wrapped_dek=self._wrap(dek), last_active=self._now())
            self._sessions[session_id] = s
        return s

    def session_salt(self, session_id: str) -> bytes:
        return self._session(session_id).salt

    def purge_session(self, session_id: str) -> int:
        s = self._sessions.pop(session_id, None)
        if not s:
            return 0
        n = len(s.entries)
        s.entries.clear()
        s.by_lookup.clear()
        self._audit({"event": "purge_session", "session_id": session_id, "count": n})
        return n

    def purge_expired(self) -> int:
        now = self._now()
        removed = 0
        for sid in list(self._sessions.keys()):
            s = self._sessions[sid]
            for sur in list(s.entries.keys()):
                e = s.entries[sur]
                if e.expires_at <= now:
                    del s.entries[sur]
                    s.by_lookup.pop(e.lookup_key_hash, None)
                    removed += 1
            if not s.entries and (now - s.last_active) > self.hard_cap:
                del self._sessions[sid]
        if removed:
            self._audit({"event": "purge_expired", "count": removed})
        return removed

    # ── 봉투암호화 ────────────────────────────────────────────────────────
    def _wrap(self, dek: bytes) -> bytes:
        nonce = os.urandom(12)
        return nonce + AESGCM(self._kek).encrypt(nonce, dek, None)

    def _unwrap(self, wrapped: bytes) -> bytes:
        return AESGCM(self._kek).decrypt(wrapped[:12], wrapped[12:], None)

    def _enc(self, dek: bytes, plaintext: str) -> bytes:
        nonce = os.urandom(12)
        return nonce + AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), None)

    def _dec(self, dek: bytes, ct: bytes) -> str:
        return AESGCM(dek).decrypt(ct[:12], ct[12:], None).decode("utf-8")

    # ── 적재 / 조회 ──────────────────────────────────────────────────────
    def lookup_hash(self, session_id: str, entity_type: str, original: str) -> bytes:
        salt = self._session(session_id).salt
        msg = (entity_type + "|" + original).encode("utf-8")
        return hmac.new(salt, msg, hashlib.sha256).digest()

    def find_surrogate(self, session_id: str, entity_type: str, original: str) -> Optional[str]:
        """같은 원본이 세션 내 이미 가명화됐으면 기존 surrogate(결정성). 없으면 None."""
        s = self._session(session_id)
        sur = s.by_lookup.get(self.lookup_hash(session_id, entity_type, original))
        if sur and sur in s.entries and s.entries[sur].expires_at > self._now():
            return sur
        return None

    def next_index(self, session_id: str, tag: str) -> int:
        s = self._session(session_id)
        s.counters[tag] = s.counters.get(tag, 0) + 1
        return s.counters[tag]

    def store(self, session_id: str, surrogate: str, entity_type: str, original: str,
              ttl: Optional[float] = None) -> VaultEntry:
        s = self._session(session_id)
        s.last_active = now = self._now()
        ttl = self.default_ttl if ttl is None else float(ttl)
        ttl = min(ttl, self.hard_cap)
        dek = self._unwrap(s.wrapped_dek)
        lh = self.lookup_hash(session_id, entity_type, original)
        entry = VaultEntry(
            surrogate=surrogate, session_id=session_id, entity_type=entity_type,
            ciphertext=self._enc(dek, original), dek_id=s.dek_id,
            created_at=now, expires_at=now + ttl, lookup_key_hash=lh)
        s.entries[surrogate] = entry
        s.by_lookup[lh] = surrogate
        self._audit({"event": "mint", "session_id": session_id, "surrogate": surrogate,
                     "entity_type": entity_type, "dek_id": s.dek_id,
                     "lookup_key_hash": lh.hex()[:16]})
        return entry

    def resolve(self, session_id: str, surrogate: str) -> Optional[str]:
        """surrogate → 원본 평문(원복). 만료/미존재 시 None. 응답 경로 훅 전용."""
        s = self._sessions.get(session_id)
        if not s:
            return None
        e = s.entries.get(surrogate)
        if not e or e.expires_at <= self._now():
            return None
        dek = self._unwrap(s.wrapped_dek)
        return self._dec(dek, e.ciphertext)

    # ── 감사(append-only, 원본 평문/복호값 미기록) ──────────────────────────
    def _audit(self, event: dict) -> None:
        event = {"ts": self._now(), **event}
        self._audit_log.append(event)
        if self._audit_sink:
            try:
                self._audit_sink(event)
            except Exception:  # pragma: no cover - 감사 sink 실패가 본 흐름을 깨지 않음
                pass

    @property
    def audit_events(self) -> list:
        return list(self._audit_log)

    def active_count(self, session_id: Optional[str] = None) -> int:
        if session_id is not None:
            s = self._sessions.get(session_id)
            return len(s.entries) if s else 0
        return sum(len(s.entries) for s in self._sessions.values())
