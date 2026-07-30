"""정책 운영 자동화 — 다중 프로파일·묶기·버전/되돌리기·변경 감사 (CMP-144 · v0.0.5 B1).

CMP-124(단일 프로파일·단건 무재기동 핫리로드)를 **운영 규모**로 끌어올린다:

1. **여러 프로파일 동시 운영 + 경로별 묶기(binding)** — :class:`ProfileRegistry`.
   프로파일 = 이름이 붙은 룰셋(:class:`~egress_audit.reload.RuleSetPaths`). 경로/테넌트
   키를 프로파일에 묶어 한 게이트웨이에서 부서·서비스별로 다른 정책을 운영한다.
2. **정책 버전 관리·되돌리기(rollback)** — :class:`PolicyVersionStore`.
   프로파일별로 정책 파일 내용을 불변(immutable) 스냅샷으로 적재하고, 이전 버전 내용을
   라이브 정책 경로로 복원한 뒤 **무재기동** 핫리로드(CMP-124 원자 스왑)로 되돌린다.
3. **변경 감사 기록** — :class:`PolicyChangeAudit`.
   누가·언제·무엇을(register/bind/snapshot/rollback) 바꿨는지 추가전용 해시 체인으로 기록.

설계 불변식 (CMP-124 계승)
--------------------------
- 신규 차단 규칙이나 게이트웨이 결정 로직을 바꾸지 않는다. 범위: 운영/설정.
- 되돌리기는 **검증된 룰셋만 적용**(fail-closed) — 후보가 깨졌으면 직전 룰셋 유지.
- 무거운 NER 모델은 재로드하지 않는다(프로파일 가드 간 인스턴스 재사용은 호출자 선택).

범위 밖 (Won't → v0.1.0): 멀티테넌시·권한관리(RBAC)·테넌트 격리.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from egress_audit.reload import (
    ReloadableGuard, ReloadResult, RuleSetPaths, RuleValidationError,
    validate_ruleset,
)

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _ROOT / "config"
_DEFAULT_ROUTING = _CONFIG_DIR / "routing.yaml"
# 런타임 묶기 변경 오버레이(라우팅 base 위에 덮어씀). routing.yaml 주석 보존 위해
# 손으로 쓴 선언과 도구가 쓰는 런타임 상태를 분리한다.
_DEFAULT_BINDINGS_OVERLAY = _CONFIG_DIR / "policy_bindings.yaml"
_DEFAULT_VERSIONS_DIR = _ROOT / "logs" / "policy_versions"
_DEFAULT_CHANGE_LOG = _ROOT / "logs" / "policy_changes.jsonl"

GENESIS_HASH = "0" * 64


# --------------------------------------------------------------------------- #
# 프로파일 레지스트리 + 묶기
# --------------------------------------------------------------------------- #
@dataclass
class PolicyProfile:
    """이름이 붙은 룰셋. 최소 override 는 policy_path(엔티티 동작)이며, 나머지
    소스(patterns/confidential/edm)는 미지정 시 base config 를 공유한다."""
    name: str
    paths: RuleSetPaths
    description: str = ""


class ProfileRegistry:
    """``routing.yaml`` 의 ``policy_profiles``/``policy_bindings`` + 런타임 오버레이.

    - ``policy_profiles``: {name: {policy: PATH, patterns: PATH, ...}} 프로파일 선언.
      미선언 키는 base config(:meth:`RuleSetPaths.default`)에서 채운다.
    - ``policy_bindings``: {route_or_tenant: profile_name} 선언 기본 묶기.
    - 런타임 ``policy bind`` 변경은 오버레이 파일에 적재되어 base 위에 덮어쓴다.
    """

    def __init__(self, routing_path: Optional[str] = None,
                 bindings_overlay_path: Optional[str] = None):
        self.routing_path = Path(routing_path or _DEFAULT_ROUTING)
        self.bindings_overlay_path = Path(
            bindings_overlay_path or os.environ.get("POLICY_BINDINGS_OVERLAY")
            or _DEFAULT_BINDINGS_OVERLAY)
        self._load()

    def _load(self) -> None:
        cfg = {}
        if self.routing_path.exists():
            cfg = yaml.safe_load(self.routing_path.read_text(encoding="utf-8")) or {}
        self._profiles_cfg: Dict[str, dict] = cfg.get("policy_profiles", {}) or {}
        self._declared_bindings: Dict[str, str] = dict(cfg.get("policy_bindings", {}) or {})
        self._default_profile: str = cfg.get("policy_default_profile", "default")
        self._overlay_bindings: Dict[str, str] = self._load_overlay()

    def _load_overlay(self) -> Dict[str, str]:
        if not self.bindings_overlay_path.exists():
            return {}
        data = yaml.safe_load(self.bindings_overlay_path.read_text(encoding="utf-8")) or {}
        return dict(data.get("bindings", {}) or {})

    def _base_paths(self) -> RuleSetPaths:
        return RuleSetPaths.default()

    def _resolve_path(self, value: Optional[str], default: str) -> str:
        if not value:
            return default
        p = Path(value)
        return str(p if p.is_absolute() else (_ROOT / p))

    def profile_names(self) -> List[str]:
        names = list(self._profiles_cfg.keys())
        if self._default_profile not in names:
            names.insert(0, self._default_profile)
        return names

    def get(self, name: str) -> PolicyProfile:
        base = self._base_paths()
        spec = self._profiles_cfg.get(name)
        if spec is None:
            if name == self._default_profile:
                # 기본 프로파일 = base config 그대로.
                return PolicyProfile(name=name, paths=base, description="base config")
            raise KeyError(f"미선언 프로파일: {name!r} (routing.yaml policy_profiles 확인)")
        paths = RuleSetPaths(
            patterns_path=self._resolve_path(spec.get("patterns"), base.patterns_path),
            policy_path=self._resolve_path(spec.get("policy"), base.policy_path),
            confidential_path=self._resolve_path(spec.get("confidential"), base.confidential_path),
            edm_index_path=self._resolve_path(spec.get("edm"), base.edm_index_path),
        )
        return PolicyProfile(name=name, paths=paths, description=spec.get("description", ""))

    def bindings(self) -> Dict[str, str]:
        """유효 묶기 = 선언(routing.yaml) ∪ 런타임 오버레이(오버레이 우선)."""
        merged = dict(self._declared_bindings)
        merged.update(self._overlay_bindings)
        return merged

    def default_profile(self) -> str:
        return self._default_profile

    def profile_for_route(self, route: str) -> str:
        """경로/테넌트 키 → 프로파일 이름. 미묶임 시 기본 프로파일."""
        return self.bindings().get(route, self._default_profile)

    def set_binding(self, route: str, profile: str) -> None:
        """런타임 묶기 변경을 오버레이에 영속한다(routing.yaml 주석 비파괴)."""
        if profile != self._default_profile and profile not in self._profiles_cfg:
            raise KeyError(f"미선언 프로파일에 묶기 불가: {profile!r}")
        self._overlay_bindings[route] = profile
        self.bindings_overlay_path.parent.mkdir(parents=True, exist_ok=True)
        header = ("# 런타임 정책 묶기 오버레이 (nufi-egress policy bind 가 기록).\n"
                  "# routing.yaml 의 policy_bindings(선언 기본) 위에 덮어쓴다.\n")
        dumped = yaml.safe_dump({"bindings": self._overlay_bindings},
                                allow_unicode=True, sort_keys=True)
        self.bindings_overlay_path.write_text(header + dumped, encoding="utf-8")


# --------------------------------------------------------------------------- #
# 정책 버전 저장소 (스냅샷 + 되돌리기)
# --------------------------------------------------------------------------- #
@dataclass
class PolicyVersion:
    version: int
    fingerprint: str
    created_at: str
    actor: str
    note: str
    active: bool = False


def _sha16(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


class PolicyVersionStore:
    """프로파일별 정책 파일 내용의 불변 버전 스냅샷 + 활성 버전 포인터.

    레이아웃: ``{base}/{profile}/v{N}.policy.yaml`` (불변 스냅샷),
    ``{base}/{profile}/meta.json`` (버전 메타 + active 포인터).

    - :meth:`snapshot` — 현재 라이브 정책 내용을 새 버전으로 적재하고 active 로 설정.
    - :meth:`restore` — 지정 버전 내용을 라이브 정책 경로에 복원하고 active 갱신
      (파일 복원만; 가드 핫리로드는 :class:`PolicyOpsManager` 가 수행).
    """

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or os.environ.get("POLICY_VERSIONS_DIR")
                             or _DEFAULT_VERSIONS_DIR)

    def _pdir(self, profile: str) -> Path:
        return self.base_dir / profile

    def _meta_path(self, profile: str) -> Path:
        return self._pdir(profile) / "meta.json"

    def _read_meta(self, profile: str) -> dict:
        mp = self._meta_path(profile)
        if not mp.exists():
            return {"versions": [], "active": None}
        return json.loads(mp.read_text(encoding="utf-8"))

    def _write_meta(self, profile: str, meta: dict) -> None:
        mp = self._meta_path(profile)
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def _snap_path(self, profile: str, version: int) -> Path:
        return self._pdir(profile) / f"v{version}.policy.yaml"

    def versions(self, profile: str) -> List[PolicyVersion]:
        meta = self._read_meta(profile)
        active = meta.get("active")
        out = []
        for v in meta.get("versions", []):
            out.append(PolicyVersion(
                version=v["version"], fingerprint=v["fingerprint"],
                created_at=v["created_at"], actor=v.get("actor", "unknown"),
                note=v.get("note", ""), active=(v["version"] == active)))
        return out

    def active_version(self, profile: str) -> Optional[int]:
        return self._read_meta(profile).get("active")

    def snapshot(self, profile: str, policy_path: str, *, actor: str,
                 note: str = "") -> PolicyVersion:
        """현재 라이브 정책 내용을 새 불변 버전으로 적재하고 active 로 설정한다."""
        content = Path(policy_path).read_bytes()
        meta = self._read_meta(profile)
        existing = [v["version"] for v in meta.get("versions", [])]
        n = (max(existing) + 1) if existing else 1
        self._snap_path(profile, n).parent.mkdir(parents=True, exist_ok=True)
        self._snap_path(profile, n).write_bytes(content)
        rec = {
            "version": n,
            "fingerprint": _sha16(content),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "actor": actor,
            "note": note,
        }
        meta.setdefault("versions", []).append(rec)
        meta["active"] = n
        self._write_meta(profile, meta)
        return PolicyVersion(active=True, **rec)

    def restore(self, profile: str, version: int, policy_path: str) -> PolicyVersion:
        """지정 버전 스냅샷 내용을 라이브 정책 경로에 복원하고 active 를 갱신한다.

        반환은 복원된 버전 메타. 가드 핫리로드는 호출자가 수행한다(무재기동).
        """
        snap = self._snap_path(profile, version)
        if not snap.exists():
            raise FileNotFoundError(
                f"프로파일 {profile!r} 버전 v{version} 스냅샷이 없습니다: {snap}")
        Path(policy_path).write_bytes(snap.read_bytes())
        meta = self._read_meta(profile)
        meta["active"] = version
        self._write_meta(profile, meta)
        for v in self.versions(profile):
            if v.version == version:
                return v
        raise KeyError(version)  # pragma: no cover


# --------------------------------------------------------------------------- #
# 변경 감사 로그 (누가·언제·무엇을)
# --------------------------------------------------------------------------- #
class PolicyChangeAudit:
    """정책 운영 변경의 추가전용 해시 체인 로그(변조탐지).

    각 레코드: {seq, ts, actor, action, profile, route, from_version, to_version,
    fingerprint, note, chain:{prev_hash, hash}}. 체인은 임의 행 수정·삭제·재배열을
    :meth:`verify_chain` 으로 탐지한다(egress_audit.audit 와 동일 방식).
    """

    def __init__(self, path: Optional[str] = None):
        self.path = Path(path or os.environ.get("POLICY_CHANGE_LOG",
                                                str(_DEFAULT_CHANGE_LOG)))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _tip(self) -> tuple[int, str]:
        if not self.path.exists():
            return -1, GENESIS_HASH
        last = None
        for ln in self.path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                last = ln
        if not last:
            return -1, GENESIS_HASH
        ch = json.loads(last).get("chain", {})
        return ch.get("seq", -1), ch.get("hash", GENESIS_HASH)

    @staticmethod
    def _hash(prev: str, payload: dict, seq: int) -> str:
        body = {k: v for k, v in payload.items() if k != "chain"}
        body["_seq"] = seq
        blob = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256((prev + blob).encode("utf-8")).hexdigest()

    def record(self, *, action: str, profile: str, actor: str,
               route: Optional[str] = None, from_version: Optional[int] = None,
               to_version: Optional[int] = None, fingerprint: Optional[str] = None,
               note: str = "", extra: Optional[dict] = None) -> dict:
        seq, prev = self._tip()
        seq += 1
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "actor": actor,
            "action": action,           # register | bind | snapshot | rollback | reload-reject
            "profile": profile,
            "route": route,
            "from_version": from_version,
            "to_version": to_version,
            "fingerprint": fingerprint,
            "note": note,
        }
        if extra:
            rec["extra"] = extra
        rec["chain"] = {"seq": seq, "prev_hash": prev,
                        "hash": self._hash(prev, rec, seq)}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def read_all(self) -> List[dict]:
        if not self.path.exists():
            return []
        return [json.loads(ln) for ln in self.path.read_text(encoding="utf-8").splitlines()
                if ln.strip()]

    def verify_chain(self) -> dict:
        records = self.read_all()
        prev = GENESIS_HASH
        for i, rec in enumerate(records):
            ch = rec.get("chain", {})
            if ch.get("seq") != i:
                return {"ok": False, "error": "seq 불연속", "broken_seq": i, "count": len(records)}
            if ch.get("prev_hash") != prev:
                return {"ok": False, "error": "prev_hash 불일치", "broken_seq": i, "count": len(records)}
            if self._hash(prev, rec, i) != ch.get("hash"):
                return {"ok": False, "error": "hash 불일치(변조)", "broken_seq": i, "count": len(records)}
            prev = ch["hash"]
        return {"ok": True, "count": len(records)}


# --------------------------------------------------------------------------- #
# 매니저 — 다중 프로파일 가드 + 운영 동작
# --------------------------------------------------------------------------- #
@dataclass
class RollbackOutcome:
    applied: bool
    profile: str
    from_version: Optional[int]
    to_version: int
    generation_before: int
    generation_after: int
    fingerprint: Optional[str] = None
    error: Optional[str] = None


class PolicyOpsManager:
    """다중 프로파일을 동시에 운영하고(가드 캐시), 묶기/버전/되돌리기/감사를 묶는다.

    프로파일 가드는 lazy 로 1회 생성·캐시된다 — 되돌리기는 이 **같은 인스턴스**를
    원자 스왑(:meth:`ReloadableGuard.reload`)하므로 프로세스 재기동이 없다(무재기동).
    """

    def __init__(self, registry: Optional[ProfileRegistry] = None,
                 version_store: Optional[PolicyVersionStore] = None,
                 change_audit: Optional[PolicyChangeAudit] = None,
                 reuse_ner=None, ner_backend: str = "gazetteer"):
        self.registry = registry or ProfileRegistry()
        self.versions = version_store or PolicyVersionStore()
        self.audit = change_audit or PolicyChangeAudit()
        self._reuse_ner = reuse_ner
        # 기본 gazetteer — 결정론적·경량(doctor/audit 기본과 정합, 에어갭 안전).
        self._ner_backend = ner_backend
        self._guards: Dict[str, ReloadableGuard] = {}

    # --- 다중 프로파일 운영 ------------------------------------------------ #
    def _build_guard(self, prof: PolicyProfile) -> ReloadableGuard:
        """프로파일 룰셋(paths)에서 가드를 구성한다. ReloadableGuard 의 기본 생성자는
        base config 가드를 만들므로, 프로파일 정책이 실제로 반영되도록 명시 구성한다."""
        from egress_audit.pipeline import DetectionPipeline
        from egress_audit.policy import PolicyEngine
        from egress_audit.guard import EgressGuard

        reuse = self._reuse_ner
        pipe = DetectionPipeline(
            patterns_path=prof.paths.patterns_path,
            confidential_path=prof.paths.confidential_path,
            edm_index_path=prof.paths.edm_index_path,
            ner_backend=self._ner_backend,
            enable_ner=(reuse is None),
        )
        if reuse is not None:
            pipe.ner = reuse
        guard = EgressGuard(pipeline=pipe,
                            policy=PolicyEngine(policy_path=prof.paths.policy_path))
        return ReloadableGuard(guard=guard, paths=prof.paths)

    def guard(self, profile: str) -> ReloadableGuard:
        """프로파일의 라이브 가드(캐시). 최초 1회 생성, 이후 동일 인스턴스 재사용."""
        if profile not in self._guards:
            self._guards[profile] = self._build_guard(self.registry.get(profile))
        return self._guards[profile]

    def guard_for_route(self, route: str) -> ReloadableGuard:
        return self.guard(self.registry.profile_for_route(route))

    def inspect(self, route: str, text: str):
        """경로/테넌트 묶기를 따라 해당 프로파일 가드로 검사한다."""
        return self.guard_for_route(route).inspect(text)

    # --- 묶기 -------------------------------------------------------------- #
    def bind(self, route: str, profile: str, *, actor: str) -> dict:
        prev = self.registry.bindings().get(route)
        self.registry.set_binding(route, profile)
        return self.audit.record(action="bind", profile=profile, actor=actor,
                                 route=route, note=f"{route} → {profile} (이전: {prev})")

    # --- 버전 -------------------------------------------------------------- #
    def snapshot(self, profile: str, *, actor: str, note: str = "") -> PolicyVersion:
        prof = self.registry.get(profile)
        pv = self.versions.snapshot(profile, prof.paths.policy_path, actor=actor, note=note)
        self.audit.record(action="snapshot", profile=profile, actor=actor,
                          to_version=pv.version, fingerprint=pv.fingerprint, note=note)
        return pv

    # --- 되돌리기(무재기동) ------------------------------------------------- #
    def rollback(self, profile: str, *, actor: str,
                 to_version: Optional[int] = None) -> RollbackOutcome:
        """이전(또는 지정) 버전으로 무재기동 되돌리기.

        절차: 활성 버전 확인 → 대상 버전 스냅샷 내용 복원 → 후보 검증 →
        통과 시 가드 원자 스왑(generation++), 실패 시 fail-closed(직전 룰셋 유지·
        파일 원복). 변경 감사 기록.
        """
        prof = self.registry.get(profile)
        active = self.versions.active_version(profile)
        existing = [v.version for v in self.versions.versions(profile)]
        if not existing:
            raise ValueError(f"프로파일 {profile!r} 에 적재된 버전이 없습니다 — 먼저 snapshot.")
        if to_version is None:
            # 기본: 활성 직전 버전.
            below = [v for v in existing if active is None or v < active]
            if not below:
                raise ValueError(f"되돌릴 이전 버전이 없습니다(활성 v{active}).")
            to_version = max(below)
        if to_version not in existing:
            raise ValueError(f"존재하지 않는 버전 v{to_version} (가용: {existing}).")

        rg = self.guard(profile)
        gen_before = rg.generation
        # 라이브 파일 백업(검증 실패 시 원복) 후 대상 버전 복원.
        live = Path(prof.paths.policy_path)
        backup = live.read_bytes()
        self.versions.restore(profile, to_version, prof.paths.policy_path)

        # 후보 검증 — 깨졌으면 fail-closed: 파일 원복 + active 원복, 가드 유지.
        try:
            validate_ruleset(prof.paths, reuse_ner=rg.guard.pipeline.ner)
        except RuleValidationError as e:
            live.write_bytes(backup)
            if active is not None:
                meta = self.versions._read_meta(profile)
                meta["active"] = active
                self.versions._write_meta(profile, meta)
            self.audit.record(action="reload-reject", profile=profile, actor=actor,
                              from_version=active, to_version=to_version,
                              note=f"되돌리기 거부(fail-closed): {e}")
            return RollbackOutcome(applied=False, profile=profile, from_version=active,
                                   to_version=to_version, generation_before=gen_before,
                                   generation_after=gen_before, error=str(e))

        res: ReloadResult = rg.reload(prof.paths)  # 무재기동 원자 스왑
        self.audit.record(action="rollback", profile=profile, actor=actor,
                          from_version=active, to_version=to_version,
                          fingerprint=res.fingerprint,
                          note=f"무재기동 되돌리기 v{active}→v{to_version} "
                               f"(generation {gen_before}→{rg.generation})")
        return RollbackOutcome(applied=res.applied, profile=profile, from_version=active,
                               to_version=to_version, generation_before=gen_before,
                               generation_after=rg.generation, fingerprint=res.fingerprint)

    # --- 상태 -------------------------------------------------------------- #
    def status(self) -> dict:
        bindings = self.registry.bindings()
        profiles = []
        for name in self.registry.profile_names():
            try:
                prof = self.registry.get(name)
            except KeyError:
                continue
            profiles.append({
                "name": name,
                "policy_path": prof.paths.policy_path,
                "active_version": self.versions.active_version(name),
                "version_count": len(self.versions.versions(name)),
                "loaded": name in self._guards,
                "generation": self._guards[name].generation if name in self._guards else None,
                "description": prof.description,
            })
        return {
            "default_profile": self.registry.default_profile(),
            "profiles": profiles,
            "bindings": bindings,
        }
