"""무재기동 룰 핫리로드 + 드라이런 + fail-closed 거부 (CMP-124 · v0.0.2 M2·D2).

운영자가 policy / 정규식(patterns) / 기밀 사전(confidential) / EDM 인덱스를
게이트웨이 **재기동 없이** 갱신한다. NFR3(룰 변경에 재기동 불필요)를 충족한다.

흐름
----
- ``validate_ruleset`` : 후보 룰셋을 빌드+검증(YAML 파싱·정규식 컴파일·정책 액션
  화이트리스트·스모크 분석). 문제가 있으면 :class:`RuleValidationError`.
- ``ReloadableGuard.dry_run`` : 현재 vs 후보 룰셋의 **결정 diff** 산출(적용하지 않음).
- ``ReloadableGuard.reload`` : 검증을 통과한 경우에만 **원자적 스왑**.
  검증 실패 시 **fail-closed** — 직전(검증된) 룰셋을 그대로 유지하고 거부 사유 반환.

설계 불변식
-----------
- 본 모듈은 신규 egress 차단 규칙이나 게이트웨이 결정 로직을 바꾸지 않는다.
  오직 "이미 검증된 설정만 적용된다"는 운영 안전장치(범위: 운영/설정)이다.
- 무거운 NER 모델은 재로드하지 않는다 — 룰 스왑 시 기존 NER 인스턴스를 재사용한다
  (룰 핫리로드 대상은 정규식/사전/EDM/정책뿐).

승인: 보드 2abc6285 (Option A).
"""
from __future__ import annotations

import hashlib
import signal
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .pipeline import DetectionPipeline
from .policy import PolicyEngine
from .guard import EgressGuard

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# policy.yaml 에서 허용되는 동작. 이 집합 밖의 액션은 fail-closed 거부 사유.
# (PolicyEngine._replacement 가 해석하는 값과 정합 — allow 는 무편집 통과.)
KNOWN_ACTIONS = {"block", "redact", "pseudonymize", "warn", "allow"}

# 드라이런/스모크 검증 기본 표본 — PII/비밀/기밀/클린 경로를 고루 자극한다.
# 원문 PII 는 합성값(실데이터 아님). 결정 diff 의 의미를 보장하려는 용도.
DEFAULT_SAMPLE_CORPUS: List[str] = [
    "주민등록번호 900101-1234567 로 본인확인 부탁드립니다.",
    "담당자 연락처 010-1234-5678, 이메일 hong@example.com 입니다.",
    "배포키 AKIAIOSFODNN7EXAMPLE / wJalrXUtnFEMI K7MDENG bPxRfiCYEXAMPLEKEY 공유합니다.",
    "본 문서는 대외비 이며 무단 반출을 금합니다.",
    "안녕하세요, 오늘 점심 회의는 12시에 진행합니다.",
]


class RuleValidationError(Exception):
    """후보 룰셋 검증 실패 — 적용 거부(fail-closed) 사유."""


@dataclass
class RuleSetPaths:
    """핫리로드 대상 4개 룰 소스 경로 묶음."""
    patterns_path: str
    policy_path: str
    confidential_path: str
    edm_index_path: str

    @classmethod
    def default(cls) -> "RuleSetPaths":
        return cls(
            patterns_path=str(_CONFIG_DIR / "patterns.yaml"),
            policy_path=str(_CONFIG_DIR / "policy.yaml"),
            confidential_path=str(_CONFIG_DIR / "confidential.yaml"),
            edm_index_path=str(_CONFIG_DIR / "edm" / "index.json"),
        )

    def fingerprint(self) -> str:
        """4개 소스 내용의 sha256 지문(존재하는 파일만). 룰셋 변경 감지용."""
        h = hashlib.sha256()
        for p in (self.patterns_path, self.policy_path,
                  self.confidential_path, self.edm_index_path):
            fp = Path(p)
            h.update(p.encode("utf-8"))
            h.update(b"\x00")
            if fp.exists():
                h.update(fp.read_bytes())
            h.update(b"\x00")
        return h.hexdigest()[:16]


@dataclass
class RuleSetReport:
    """검증 통과한 후보 룰셋의 요약(감사/로그용)."""
    fingerprint: str
    conf_ruleset_version: Optional[str]
    edm_ruleset_version: Optional[str]
    policy_version: Optional[int]
    entity_count: int


@dataclass
class ReloadDiff:
    """현재 vs 후보 룰셋의 결정 diff(드라이런 산출물 — 미적용)."""
    valid: bool
    error: Optional[str] = None
    fingerprint_before: Optional[str] = None
    fingerprint_after: Optional[str] = None
    changed: List[dict] = field(default_factory=list)
    totals: Dict[str, int] = field(default_factory=dict)


@dataclass
class ReloadResult:
    """reload() 결과. applied=False 면 직전 룰셋 유지(fail-closed)."""
    applied: bool
    generation: int
    fingerprint: Optional[str] = None
    error: Optional[str] = None
    report: Optional[RuleSetReport] = None


def _build_pipeline(paths: RuleSetPaths, reuse_ner) -> DetectionPipeline:
    """후보 경로로 탐지 파이프라인을 빌드한다(NER 은 재로드하지 않고 재사용).

    잘못된 정규식/누락 키/깨진 YAML 은 여기서 예외로 드러난다(=검증).
    """
    pipe = DetectionPipeline(
        patterns_path=paths.patterns_path,
        enable_ner=False,
        confidential_path=paths.confidential_path,
        edm_index_path=paths.edm_index_path,
    )
    # 룰 핫리로드 대상이 아닌 NER 모델은 기존 인스턴스를 그대로 물려준다(무재로드).
    pipe.ner = reuse_ner
    return pipe


def validate_ruleset(paths: RuleSetPaths, reuse_ner=None,
                     sample_corpus: Optional[List[str]] = None) -> RuleSetReport:
    """후보 룰셋을 빌드+검증한다. 실패 시 :class:`RuleValidationError`.

    검사 항목:
      1. patterns/confidential/edm 빌드(정규식 컴파일·YAML 파싱) 성공.
      2. policy.yaml 빌드 성공 + 모든 동작이 :data:`KNOWN_ACTIONS` 내.
      3. 표본 코퍼스 스모크 분석(analyze→policy.apply)이 예외 없이 끝남.
    """
    sample_corpus = sample_corpus or DEFAULT_SAMPLE_CORPUS

    # 1) 탐지 파이프라인 빌드 (정규식/사전/EDM)
    try:
        pipe = _build_pipeline(paths, reuse_ner)
    except Exception as e:  # re.error / KeyError / yaml 오류 / 파일오류 등
        raise RuleValidationError(
            f"탐지 룰(정규식/사전/EDM) 빌드 실패: {type(e).__name__}: {e}") from e

    # 2) 정책 빌드 + 동작 화이트리스트
    try:
        policy = PolicyEngine(policy_path=paths.policy_path)
    except Exception as e:
        raise RuleValidationError(
            f"정책(policy.yaml) 빌드 실패: {type(e).__name__}: {e}") from e
    _validate_policy_actions(policy)

    # 3) 스모크 분석 — 룰셋이 실제 결정 경로에서 동작하는지
    try:
        for text in sample_corpus:
            findings = pipe.analyze(text)
            policy.apply(text, findings)
    except Exception as e:
        raise RuleValidationError(
            f"스모크 분석 실패: {type(e).__name__}: {e}") from e

    return RuleSetReport(
        fingerprint=paths.fingerprint(),
        conf_ruleset_version=pipe.conf_ruleset_version,
        edm_ruleset_version=(pipe.edm.index.ruleset_version
                             if pipe.edm is not None else None),
        policy_version=policy.cfg.get("version") if isinstance(policy.cfg, dict) else None,
        entity_count=len(policy.entities),
    )


def _validate_policy_actions(policy: PolicyEngine) -> None:
    bad: List[str] = []
    for etype, ent in (policy.entities or {}).items():
        act = (ent or {}).get("action")
        if act not in KNOWN_ACTIONS:
            bad.append(f"{etype}={act!r}")
    for cls, ent in (policy.conf_class_actions or {}).items():
        act = (ent or {}).get("action")
        if act not in KNOWN_ACTIONS:
            bad.append(f"conf_class_actions.{cls}={act!r}")
    if policy.default_action not in KNOWN_ACTIONS:
        bad.append(f"default_action={policy.default_action!r}")
    if bad:
        raise RuleValidationError(
            "알 수 없는 정책 동작(허용: %s): %s"
            % (sorted(KNOWN_ACTIONS), ", ".join(bad)))


def _decision_snapshot(guard: EgressGuard, text: str) -> dict:
    r = guard.inspect(text)
    s = r.summary
    return {
        "blocked": bool(s.get("blocked")),
        "action_counts": dict(s.get("action_counts", {})),
        "finding_count": int(s.get("finding_count", 0)),
    }


class ReloadableGuard:
    """핫리로드 가능한 :class:`EgressGuard` 래퍼.

    - ``inspect`` 는 현재(검증된) 가드로 위임한다.
    - ``dry_run`` 은 후보 룰셋의 결정 diff 를 적용 없이 산출한다.
    - ``reload`` 는 검증 통과 시에만 원자적으로 가드를 교체한다.
    """

    def __init__(self, guard: Optional[EgressGuard] = None,
                 paths: Optional[RuleSetPaths] = None,
                 sample_corpus: Optional[List[str]] = None,
                 on_reload: Optional[Callable[[ReloadResult], None]] = None):
        self.paths = paths or RuleSetPaths.default()
        self.sample_corpus = sample_corpus or DEFAULT_SAMPLE_CORPUS
        self._on_reload = on_reload
        self._lock = threading.Lock()
        self.guard = guard or EgressGuard()
        self.generation = 0
        self.active_fingerprint = self.paths.fingerprint()
        self.last_error: Optional[str] = None

    # 라이브 결정 경로 — 항상 현재 검증된 가드 사용.
    def inspect(self, text: str):
        return self.guard.inspect(text)

    def _candidate_guard(self, paths: RuleSetPaths) -> EgressGuard:
        """검증 통과를 전제로 후보 가드를 빌드(NER 재사용)."""
        pipe = _build_pipeline(paths, self.guard.pipeline.ner)
        policy = PolicyEngine(policy_path=paths.policy_path)
        return EgressGuard(pipeline=pipe, policy=policy)

    def dry_run(self, paths: Optional[RuleSetPaths] = None) -> ReloadDiff:
        """후보 룰셋을 검증하고, 표본에 대한 현재 대비 결정 diff 를 반환(미적용)."""
        paths = paths or self.paths
        before_fp = self.active_fingerprint
        try:
            validate_ruleset(paths, reuse_ner=self.guard.pipeline.ner,
                             sample_corpus=self.sample_corpus)
            candidate = self._candidate_guard(paths)
        except RuleValidationError as e:
            return ReloadDiff(valid=False, error=str(e),
                              fingerprint_before=before_fp,
                              fingerprint_after=paths.fingerprint())

        changed: List[dict] = []
        newly_blocked = newly_unblocked = 0
        with self._lock:
            current = self.guard
        for i, text in enumerate(self.sample_corpus):
            b = _decision_snapshot(current, text)
            a = _decision_snapshot(candidate, text)
            if b != a:
                changed.append({
                    "index": i,
                    "text_preview": (text[:40] + "…") if len(text) > 40 else text,
                    "before": b, "after": a,
                })
                if a["blocked"] and not b["blocked"]:
                    newly_blocked += 1
                elif b["blocked"] and not a["blocked"]:
                    newly_unblocked += 1
        return ReloadDiff(
            valid=True,
            fingerprint_before=before_fp,
            fingerprint_after=paths.fingerprint(),
            changed=changed,
            totals={
                "samples": len(self.sample_corpus),
                "changed": len(changed),
                "newly_blocked": newly_blocked,
                "newly_unblocked": newly_unblocked,
            },
        )

    def reload(self, paths: Optional[RuleSetPaths] = None) -> ReloadResult:
        """후보 룰셋을 검증하고 통과 시 원자적 스왑. 실패 시 fail-closed(직전 유지)."""
        paths = paths or self.paths
        try:
            report = validate_ruleset(paths, reuse_ner=self.guard.pipeline.ner,
                                      sample_corpus=self.sample_corpus)
            candidate = self._candidate_guard(paths)
        except RuleValidationError as e:
            self.last_error = str(e)
            result = ReloadResult(applied=False, generation=self.generation,
                                  fingerprint=self.active_fingerprint, error=str(e))
            if self._on_reload:
                self._on_reload(result)
            return result

        with self._lock:
            self.guard = candidate                  # 원자적 참조 교체
            self.generation += 1
            self.active_fingerprint = report.fingerprint
            self.last_error = None
            result = ReloadResult(applied=True, generation=self.generation,
                                  fingerprint=report.fingerprint, report=report)
        if self._on_reload:
            self._on_reload(result)
        return result

    def install_sighup_handler(self) -> None:
        """SIGHUP 수신 시 reload() 를 트리거하도록 등록한다(메인 스레드 전용).

        운영: ``kill -HUP <gateway_pid>`` 로 무재기동 룰 적용. 검증 실패 시
        직전 룰셋이 유지되며 last_error 로 사유를 남긴다(fail-closed).
        """
        def _handler(signum, frame):  # pragma: no cover - 시그널 경로
            self.reload()
        signal.signal(signal.SIGHUP, _handler)
