"""파이프라인 프리셋 엔진 (CMP-121 · v0.0.2 M1·D1).

raw `config/*.yaml` 수작업 대신 의견 있는 프리셋으로 안전 채택을 가속한다:
  - strict-kr-pii           : 한국어 PII/비밀 최대 차단(fail-closed).
  - audit-only              : 차단 없이 전수 탐지·로깅(fail-open).
  - pseudonymize-roundtrip  : 약한 PII 가역 가명화·원복, 강한 PII/비밀 차단(fail-open).

프리셋 = `config/presets/<name>.yaml` 의 "오버레이"(베이스 config 에 deep-merge).
이 모듈은 머지·검증·구체화(materialize)만 담당하며, **런타임 enforcement 동작은
바꾸지 않는다** — 기존 PolicyEngine/Applier 가 읽는 동일 스키마/식별자 config 를 낼 뿐.

fail-closed 원칙(CMP-121 수용기준):
  - 알 수 없는 프리셋 이름        → PresetError(파일 미생성).
  - 허용목록 밖 override 키       → PresetError.
  - 검증 실패(잘못된 action 등)   → PresetError.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _ROOT / "config"
_PRESET_DIR = _CONFIG_DIR / "presets"

# 베이스 config 키 → 파일명. materialize 는 (오버레이 ∘ 베이스)를 이 파일들로 낸다.
BASE_FILES: Dict[str, str] = {
    "policy": "policy.yaml",
    "routing": "routing.yaml",
    "audit_profiles": "audit_profiles.yaml",
}

# 정책 엔진이 이해하는 동작 enum(policy.py 와 정렬).
VALID_ACTIONS = {"block", "redact", "pseudonymize", "warn", "allow"}
VALID_FAIL_MODES = {"open", "closed"}
VALID_EGRESS_CLASSES = {"public", "private"}

# `--set k=v` 로 조정 가능한 안전 노브 허용목록. 그 외 키는 fail-closed 거부.
# value 검증기: 통과하면 강제 변환된 값을 반환, 실패 시 PresetError.
def _v_fail_mode(v: str) -> str:
    if v not in VALID_FAIL_MODES:
        raise PresetError(f"fail_mode 는 {sorted(VALID_FAIL_MODES)} 중 하나여야 함: {v!r}")
    return v


def _v_bool(v: str) -> bool:
    s = str(v).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off"):
        return False
    raise PresetError(f"불리언이어야 함(true/false): {v!r}")


def _v_action(v: str) -> str:
    if v not in VALID_ACTIONS:
        raise PresetError(f"action 은 {sorted(VALID_ACTIONS)} 중 하나여야 함: {v!r}")
    return v


# dotted-path → (file_key, [keys...], 검증기)
ALLOWED_OVERRIDES: Dict[str, tuple] = {
    "policy.default_action": ("policy", ["default_action"], _v_action),
    "policy.enforcement.fail_mode": ("policy", ["enforcement", "fail_mode"], _v_fail_mode),
    "audit_profiles.profiles.public.retain_raw":
        ("audit_profiles", ["profiles", "public", "retain_raw"], _v_bool),
    "audit_profiles.profiles.private.retain_raw":
        ("audit_profiles", ["profiles", "private", "retain_raw"], _v_bool),
}


class PresetError(ValueError):
    """프리셋 해석/검증/머지 실패(fail-closed). CLI 는 비0 종료·파일 미생성으로 처리."""


# ---------------------------------------------------------------- discovery
def preset_dir() -> Path:
    return _PRESET_DIR


def list_presets(preset_dir_path: Optional[Path] = None) -> List[str]:
    d = preset_dir_path or _PRESET_DIR
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.yaml"))


def load_preset(name: str, preset_dir_path: Optional[Path] = None) -> Dict[str, Any]:
    """프리셋 정의 dict 로드. 미지/형식오류 → PresetError(fail-closed)."""
    d = preset_dir_path or _PRESET_DIR
    path = d / f"{name}.yaml"
    if not path.is_file():
        avail = ", ".join(list_presets(d)) or "(없음)"
        raise PresetError(f"알 수 없는 프리셋 {name!r}. 사용 가능: {avail}")
    try:
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise PresetError(f"프리셋 {name!r} YAML 파싱 실패: {e}") from e
    if not isinstance(spec, dict):
        raise PresetError(f"프리셋 {name!r} 최상위는 매핑이어야 함")
    if spec.get("preset") != name:
        raise PresetError(
            f"프리셋 {name!r} 파일의 preset 필드({spec.get('preset')!r})가 파일명과 불일치")
    spec.setdefault("overlay", {})
    spec.setdefault("directives", {})
    return spec


# ---------------------------------------------------------------- merge
def deep_merge(base: Any, overlay: Any) -> Any:
    """dict 는 재귀 병합, 그 외(스칼라/리스트)는 overlay 가 교체. 베이스 비파괴."""
    if isinstance(base, dict) and isinstance(overlay, dict):
        out = copy.deepcopy(base)
        for k, v in overlay.items():
            out[k] = deep_merge(out.get(k), v) if k in out else copy.deepcopy(v)
        return out
    return copy.deepcopy(overlay)


def _load_base(base_dir: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for key, fname in BASE_FILES.items():
        path = base_dir / fname
        if not path.is_file():
            raise PresetError(f"베이스 config 누락: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise PresetError(f"베이스 config {path} 최상위는 매핑이어야 함")
        out[key] = data
    return out


def _parse_set(pairs: Optional[Iterable[str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in pairs or []:
        if "=" not in raw:
            raise PresetError(f"--set 은 key=value 형식이어야 함: {raw!r}")
        k, v = raw.split("=", 1)
        k = k.strip()
        if k not in ALLOWED_OVERRIDES:
            allowed = ", ".join(sorted(ALLOWED_OVERRIDES))
            raise PresetError(f"허용되지 않은 override 키 {k!r}. 허용: {allowed}")
        out[k] = v.strip()
    return out


def _set_path(d: Dict[str, Any], keys: List[str], value: Any) -> None:
    cur = d
    for k in keys[:-1]:
        nxt = cur.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[k] = nxt
        cur = nxt
    cur[keys[-1]] = value


def materialize(name: str, base_dir: Optional[Path] = None,
                overrides: Optional[Iterable[str]] = None,
                preset_dir_path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """프리셋을 베이스 config 에 적용해 완전한 config dict 집합을 반환.

    순서: 베이스 로드 → 오버레이 deep-merge → directive 적용 → --set override → 검증.
    실패는 전부 PresetError(fail-closed) — 호출자는 어떤 파일도 쓰지 않는다.
    """
    base_dir = base_dir or _CONFIG_DIR
    spec = load_preset(name, preset_dir_path)
    base = _load_base(base_dir)
    overlay = spec.get("overlay", {}) or {}
    if not isinstance(overlay, dict):
        raise PresetError(f"프리셋 {name!r} overlay 는 매핑이어야 함")

    merged: Dict[str, Dict[str, Any]] = {}
    for key in BASE_FILES:
        merged[key] = deep_merge(base[key], overlay.get(key, {}) or {})

    _apply_directives(spec.get("directives", {}) or {}, merged)

    for dotted, value in _parse_set(overrides).items():
        file_key, keys, validate = ALLOWED_OVERRIDES[dotted]
        _set_path(merged[file_key], keys, validate(value))

    _validate(merged)
    return merged


def _apply_directives(directives: Dict[str, Any], merged: Dict[str, Dict[str, Any]]) -> None:
    """프리셋 directive 적용(오버레이 후처리). 현재 지원: force_entity_action."""
    force = directives.get("force_entity_action")
    if force is not None:
        if force not in VALID_ACTIONS:
            raise PresetError(f"force_entity_action 은 {sorted(VALID_ACTIONS)} 중 하나여야 함: {force!r}")
        entities = merged["policy"].get("entities", {})
        for ent in entities.values():
            if isinstance(ent, dict):
                ent["action"] = force


# ---------------------------------------------------------------- validation
def _validate(merged: Dict[str, Dict[str, Any]]) -> None:
    pol = merged["policy"]
    da = pol.get("default_action")
    if da not in VALID_ACTIONS:
        raise PresetError(f"policy.default_action 무효: {da!r}")
    ba = pol.get("blocking_actions", [])
    if not isinstance(ba, list) or any(a not in VALID_ACTIONS for a in ba):
        raise PresetError(f"policy.blocking_actions 무효: {ba!r}")
    for etype, ent in (pol.get("entities") or {}).items():
        if not isinstance(ent, dict) or ent.get("action") not in VALID_ACTIONS:
            raise PresetError(f"policy.entities.{etype} action 무효: {ent!r}")
    for cls, spec in (pol.get("conf_class_actions") or {}).items():
        if not isinstance(spec, dict) or spec.get("action") not in VALID_ACTIONS:
            raise PresetError(f"policy.conf_class_actions.{cls} action 무효: {spec!r}")
    fm = (pol.get("enforcement") or {}).get("fail_mode")
    if fm is not None and fm not in VALID_FAIL_MODES:
        raise PresetError(f"policy.enforcement.fail_mode 무효: {fm!r}")

    routing = merged["routing"]
    for bname, b in (routing.get("backends") or {}).items():
        ec = (b or {}).get("egress_class")
        if ec not in VALID_EGRESS_CLASSES:
            raise PresetError(f"routing.backends.{bname}.egress_class 무효: {ec!r}")

    profiles = (merged["audit_profiles"].get("profiles") or {})
    for pname in ("private", "public"):
        prof = profiles.get(pname)
        if not isinstance(prof, dict) or not isinstance(prof.get("retain_raw"), bool):
            raise PresetError(f"audit_profiles.profiles.{pname}.retain_raw 는 불리언이어야 함")


# ---------------------------------------------------------------- write
def write_config(merged: Dict[str, Dict[str, Any]], out_dir: Path,
                 preset_name: str, force: bool = False) -> List[Path]:
    """검증된 config 집합을 out_dir 에 기록. 기존 파일은 force 없으면 거부(fail-closed)."""
    out_dir = Path(out_dir)
    targets = {BASE_FILES[k]: merged[k] for k in BASE_FILES}
    if not force:
        existing = [out_dir / f for f in targets if (out_dir / f).exists()]
        if existing:
            names = ", ".join(p.name for p in existing)
            raise PresetError(f"대상 파일이 이미 존재({names}). 덮어쓰려면 --force.")
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    header = (f"# 생성: nufi init {preset_name} (프리셋)\n"
              f"# 이 파일은 프리셋에서 구체화됨. 재현: nufi init {preset_name} --force\n"
              f"# 세부 조정은 raw 편집(파워유저 탈출구) 또는 프리셋 오버레이 수정.\n")
    for fname, data in targets.items():
        path = out_dir / fname
        body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
        path.write_text(header + body, encoding="utf-8")
        written.append(path)
    return written
