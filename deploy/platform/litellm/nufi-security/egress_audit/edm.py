"""EDM — 문서 지문 / 데이터셋 셀 매치 (SPEC_M4 §3).

두 신호원:
  - edm_struct : 등록 데이터셋(고객명단·급여·단가)의 셀 값을 솔티드 해시로 인덱싱,
                 한 메시지에 같은 레코드의 K-of-N 필드가 함께 등장하면 강신호.
  - edm_doc    : 등록 문서를 shingling→winnowing→MinHash 시그니처로 인덱싱,
                 프롬프트와의 Jaccard 유사도가 임계 초과면 매치(부분 인용 탐지).

NFR1: 등록·조회 전부 로컬, 원문 비저장 — 인덱스에는 해시/시그니처/필드명만.
NFR4: 순수 stdlib (HMAC-SHA256, blake2b). datasketch 등 외부 의존 없음.

인덱스 빌드(오프라인 배치)는 register_* 함수, 인라인 조회는 EdmMatcher(읽기 전용).
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import normalize as nz

# per-deployment salt (NFR1: 인덱스 유출돼도 원문 복원 불가, 역상 저항+salt).
# 운영시 Vault/시크릿 주입. 등록·조회가 같은 salt 를 써야 한다.
_SALT = os.environ.get("EGRESS_EDM_SALT", "nufi-edm-poc-salt").encode()

_MASK64 = (1 << 64) - 1
_MERSENNE = (1 << 61) - 1  # MinHash 순열 모듈러스(소수)


def _cell_hash(value: str, salt: bytes = _SALT) -> str:
    """정규화 셀 값 → 솔티드 HMAC-SHA256 (앞 16바이트 hex)."""
    norm = nz.normalize_token(value)
    if not norm:
        return ""
    return hmac.new(salt, norm.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _shingle_hash(s: str) -> int:
    """char n-gram → 64bit 정수 해시(blake2b, 안정적·결정적)."""
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")


# ----------------------------------------------------------------------------
# Structured EDM
# ----------------------------------------------------------------------------
def register_structured(rows: List[dict], fields_cfg: List[dict], *,
                        dataset: str, salt: bytes = _SALT) -> dict:
    """CSV 행 목록 → 셀 해시 인덱스. 원문 미저장.

    fields_cfg: [{column, field, class, min_cardinality?}]
    반환 인덱스: hash→[{rec,field}], records: rec→[field...], field meta.
    """
    fmap = {f["column"]: f for f in fields_cfg}
    cls = None
    hash_index: Dict[str, List[dict]] = {}
    records: List[Dict[str, str]] = []        # rec_id -> {field: hash}
    field_cardinality: Dict[str, set] = {}
    for ri, row in enumerate(rows):
        rec_id = f"{dataset}#r{ri}"
        rec: Dict[str, str] = {}
        for col, fc in fmap.items():
            if col not in row:
                continue
            h = _cell_hash(str(row[col]), salt)
            if not h:
                continue
            fld = fc["field"]
            rec[fld] = h
            field_cardinality.setdefault(fld, set()).add(h)
            hash_index.setdefault(h, []).append({"rec": rec_id, "field": fld})
            if fc.get("class"):
                cls = fc["class"]
        if rec:
            records.append({"rec": rec_id, "fields": rec})
    field_meta = {f["field"]: {"class": f.get("class"),
                               "min_cardinality": int(f.get("min_cardinality", 1)),
                               "cardinality": len(field_cardinality.get(f["field"], ()))}
                  for f in fields_cfg}
    return {
        "kind": "edm_struct",
        "dataset": dataset,
        "class": cls or "CONFIDENTIAL",
        "n_fields": len({f["field"] for f in fields_cfg}),
        "hash_index": hash_index,
        "records": records,
        "field_meta": field_meta,
    }


# ----------------------------------------------------------------------------
# Unstructured EDM — shingling + winnowing + MinHash
# ----------------------------------------------------------------------------
def _winnowed_shingles(text: str, k: int = 8, window: int = 4) -> List[int]:
    """정규화 텍스트 → char k-gram 해시 → winnowing 으로 대표 지문 선택."""
    t = nz.normalize_token(text)  # 공백·대소문자 무시한 연속 문자열
    if len(t) < k:
        return [_shingle_hash(t)] if t else []
    hashes = [_shingle_hash(t[i:i + k]) for i in range(len(t) - k + 1)]
    if len(hashes) < window:
        return sorted(set(hashes))
    selected: set = set()
    min_idx = -1
    for i in range(len(hashes) - window + 1):
        win = hashes[i:i + window]
        # 윈도우 내 최소값(동률이면 가장 오른쪽) 선택 — 표준 winnowing
        m = min(range(window), key=lambda j: (win[j], j))
        gmin = i + m
        if gmin != min_idx:
            selected.add(hashes[gmin])
            min_idx = gmin
    return sorted(selected)


def _minhash(fingerprints: List[int], num_perm: int, perms: List[Tuple[int, int]]) -> List[int]:
    if not fingerprints:
        return [0] * num_perm
    sig = []
    for a, b in perms:
        mn = _MERSENNE
        for fp in fingerprints:
            v = (a * (fp & _MASK64) + b) % _MERSENNE
            if v < mn:
                mn = v
        sig.append(mn)
    return sig


def _default_perms(num_perm: int) -> List[Tuple[int, int]]:
    """결정적 순열 계수(a,b) — 빌드·조회가 같은 계수를 써야 비교 가능."""
    perms = []
    a, b = 0x9E3779B97F4A7C15, 0xC2B2AE3D27D4EB4F
    seed = 0x12345
    for i in range(num_perm):
        seed = (seed * a + b) % _MERSENNE
        ai = (seed | 1) % _MERSENNE
        seed = (seed * a + b) % _MERSENNE
        bi = seed % _MERSENNE
        perms.append((ai or 1, bi))
    return perms


def register_document(text: str, *, doc_id: str, cls: str = "CONFIDENTIAL",
                      k: int = 8, window: int = 4, num_perm: int = 64) -> dict:
    perms = _default_perms(num_perm)
    fps = _winnowed_shingles(text, k=k, window=window)
    sig = _minhash(fps, num_perm, perms)
    return {
        "doc_id": doc_id, "class": cls,
        "k": k, "window": window, "num_perm": num_perm,
        "n_fp": len(fps), "signature": sig,
    }


# ----------------------------------------------------------------------------
# 읽기 전용 매처 (인라인 경로)
# ----------------------------------------------------------------------------
@dataclass
class EdmThresholds:
    k_of_n: int = 2                 # structured 강신호 동시매치 임계
    doc_high: float = 0.55          # 고유사도 → block
    doc_med: float = 0.30           # 중유사도 → warn


@dataclass
class EdmIndex:
    struct: List[dict] = field(default_factory=list)
    docs: List[dict] = field(default_factory=list)
    stop_hashes: set = field(default_factory=set)
    thresholds: EdmThresholds = field(default_factory=EdmThresholds)
    ruleset_version: str = "edm-dev"


class EdmMatcher:
    """인덱스(해시/시그니처만)를 읽어 메시지를 조회. 외부호출 0."""

    def __init__(self, index: EdmIndex, salt: bytes = _SALT):
        self.index = index
        self.salt = salt

    @classmethod
    def from_file(cls, path: str) -> "EdmMatcher":
        p = Path(path)
        if not p.exists():
            return cls(EdmIndex())
        data = json.loads(p.read_text(encoding="utf-8"))
        th = data.get("thresholds", {})
        idx = EdmIndex(
            struct=data.get("struct", []),
            docs=data.get("docs", []),
            stop_hashes=set(data.get("stop_hashes", [])),
            thresholds=EdmThresholds(
                k_of_n=int(th.get("k_of_n", 2)),
                doc_high=float(th.get("doc_high", 0.55)),
                doc_med=float(th.get("doc_med", 0.30)),
            ),
            ruleset_version=data.get("ruleset_version", "edm-dev"),
        )
        return cls(idx)

    @property
    def empty(self) -> bool:
        return not self.index.struct and not self.index.docs

    # ---- structured 조회 ----
    def _candidate_hashes(self, norm_text: str) -> set:
        """메시지에서 셀 후보 토큰(1~3 어절 n-gram)을 해시."""
        words = [w for w in norm_text.split(" ") if w]
        cand: set = set()
        for w in words:
            cand.add(_cell_hash(w, self.salt))
        for size in (2, 3):                       # 다어절 값(이름+공백, 지명) 흡수
            for i in range(len(words) - size + 1):
                cand.add(_cell_hash("".join(words[i:i + size]), self.salt))
        cand.discard("")
        return cand - self.index.stop_hashes

    def match_structured(self, norm_text: str) -> List[dict]:
        cand = self._candidate_hashes(norm_text)
        results = []
        for ds in self.index.struct:
            hash_index = ds.get("hash_index", {})
            # rec -> matched field set
            per_rec: Dict[str, set] = {}
            for h in cand:
                for hit in hash_index.get(h, []):
                    per_rec.setdefault(hit["rec"], set()).add(hit["field"])
            if not per_rec:
                continue
            k_of_n = self.index.thresholds.k_of_n
            best_rec, best_fields = max(per_rec.items(), key=lambda kv: len(kv[1]))
            n_fields = ds.get("n_fields", len(best_fields))
            field_meta = ds.get("field_meta", {})
            strong = len(best_fields) >= k_of_n
            if not strong:
                # 단일/약신호: 저카디널리티 필드 단독은 강등/무시
                fld = next(iter(best_fields))
                if field_meta.get(fld, {}).get("cardinality", 99) < field_meta.get(fld, {}).get("min_cardinality", 1):
                    continue
            entity = "CONF_EDM_STRUCT_STRONG" if strong else "CONF_EDM_STRUCT_WEAK"
            conf = round(min(0.99, 0.5 + 0.15 * len(best_fields)), 3)
            results.append({
                "entity_type": entity, "source": "edm_struct",
                "class": ds.get("class", "CONFIDENTIAL"), "confidence": conf,
                "match_meta": {
                    "matched_fields": sorted(best_fields),
                    "k_of_n": f"{len(best_fields)}/{n_fields}",
                    "fingerprint_id": best_rec,
                    "ruleset_version": self.index.ruleset_version,
                },
            })
        return results

    # ---- unstructured 조회 ----
    def match_documents(self, norm_text: str) -> List[dict]:
        results = []
        for doc in self.index.docs:
            num_perm = doc.get("num_perm", 64)
            perms = _default_perms(num_perm)
            q_fp = _winnowed_shingles(norm_text, k=doc.get("k", 8),
                                      window=doc.get("window", 4))
            if not q_fp:
                continue
            q_sig = _minhash(q_fp, num_perm, perms)
            d_sig = doc.get("signature", [])
            if len(d_sig) != num_perm:
                continue
            sim = sum(1 for a, b in zip(q_sig, d_sig) if a == b) / num_perm
            th = self.index.thresholds
            if sim >= th.doc_high:
                entity, conf = "CONF_EDM_DOC_HIGH", round(sim, 3)
            elif sim >= th.doc_med:
                entity, conf = "CONF_EDM_DOC_MED", round(sim, 3)
            else:
                continue
            results.append({
                "entity_type": entity, "source": "edm_doc",
                "class": doc.get("class", "CONFIDENTIAL"), "confidence": conf,
                "match_meta": {
                    "fingerprint_id": doc.get("doc_id"),
                    "similarity": round(sim, 3),
                    "ruleset_version": self.index.ruleset_version,
                },
            })
        return results

    def match(self, norm_text: str) -> List[dict]:
        if self.empty:
            return []
        return self.match_structured(norm_text) + self.match_documents(norm_text)
