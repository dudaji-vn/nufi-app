"""CMP-236 (v0.3.0 과제2) — 인명 채널 규칙∪NER 유니온 검증.

KR_LOCATION 유니온(CMP-222 P3)과 동일 플레이북을 KR_PERSON 에 적용한다.
규칙(경칭/직함/문맥 게이팅)이 모델이 놓친 등재 성씨 인명을 회복해
recall(model ∪ rules) ≥ max(model, rules) 를 보장한다.

본 테스트는 실제 모델 없이(에어갭) 유니온 *메커니즘* 을 결정적으로 검증한다:
  · stub 모델 백엔드(미수록 성씨만 잡고 등재 성씨 일부를 놓침)로
    유니온 recall 개선을 실측하고,
  · KR_LOCATION/기타 PII 채널이 유니온으로 회귀하지 않으며,
  · benign false-positive 0 을 유지하고,
  · gazetteer 백엔드에서는 유니온이 no-op 임을

를 검증한다.

실행: python3 -m pytest tests/test_cmp236_person_union.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import EgressGuard  # noqa: E402
from egress_audit.pipeline import DetectionPipeline  # noqa: E402
from egress_audit.detectors.korean_pii import RawSpan  # noqa: E402
from egress_audit.detectors.ner import KoreanNerDetector, detect_kr_persons  # noqa: E402


# ---------------------------------------------------------------------------
# 모델 백엔드 stub — 미수록(unlisted) 성씨 인명만 탐지, 등재 성씨 일부를 놓침.
# 실제 onnx-int8 없이 유니온 메커니즘을 결정적으로 재현한다(에어갭).
# ---------------------------------------------------------------------------
class _StubPersonModelBackend:
    name = "stub-person-model"
    source = "ner:stub-person-model"
    _pool = None

    # 모델이 잡는 인명 목록(미수록 성씨 포함, 등재 성씨 일부 누락)
    _DETECTABLE = {
        "삼민수": (0, 3),   # 미수록 성씨 — 모델이 잡음
        "율지훈": (0, 3),   # 미수록 성씨 — 모델이 잡음
        "김서연": (0, 3),   # 등재 성씨 — 모델이 잡음
    }
    # 모델이 놓치는 인명(등재 성씨이나 특정 문맥에서 놓침)
    _MISS = {"박예준", "이도윤", "정하준"}

    def detect(self, text):
        for name in self._DETECTABLE:
            idx = text.find(name)
            if idx >= 0:
                yield RawSpan("KR_PERSON", name, idx, idx + len(name), 0.92,
                              source=self.source)
        # 다른 인명은 놓침(모델 한계 시뮬레이션)


def _guard(person_union: bool) -> EgressGuard:
    """stub 모델 백엔드를 단 파이프라인으로 EgressGuard 구성."""
    pipe = DetectionPipeline(ner_backend="gazetteer")
    det = KoreanNerDetector.__new__(KoreanNerDetector)
    det.backend = _StubPersonModelBackend()
    det.person_union = bool(person_union) and det.backend_name != "gazetteer"
    det.location_union = False
    pipe.ner = det
    return EgressGuard(pipeline=pipe)


def _persons(guard: EgressGuard, text: str) -> set[str]:
    return {f.text for f in guard.inspect(text).findings if f.entity_type == "KR_PERSON"}


def _person_hit(guard: EgressGuard, text: str) -> bool:
    return any(f.entity_type == "KR_PERSON" for f in guard.inspect(text).findings)


# 모델이 놓치는 등재 성씨 인명(규칙이 회복해야 함)
_MODEL_MISS_POSITIVES = [
    "고객 박예준님의 계정 본인확인을 진행해 주세요.",       # 등재 성씨 + 경칭
    "이도윤 부장 보고서 검토 부탁드립니다.",                # 등재 성씨 + 직함
    "예금주 정하준 명의로 이체 처리되었습니다.",             # 등재 성씨 + 문맥(공백 경계)
]
# 모델이 이미 잡는 인명(유니온이 깨지 않아야 함)
_MODEL_DETECT_POSITIVES = [
    "고객 삼민수님의 계정 본인확인을 진행해 주세요.",       # 미수록 성씨 — 모델이 잡음
    "고객 김서연님의 계정 본인확인을 진행해 주세요.",       # 등재 성씨 — 모델이 잡음
]


def test_union_recovers_model_false_negatives():
    """모델이 놓친 등재 성씨 인명을 규칙 유니온이 회복한다."""
    model = _guard(person_union=False)
    union = _guard(person_union=True)
    for p in _MODEL_MISS_POSITIVES:
        assert not _person_hit(model, p), f"stub 모델이 이미 잡음(테스트 전제 붕괴): {p}"
        assert _person_hit(union, p), f"유니온이 회복 실패: {p}"


def test_union_recall_ge_max_each_backend():
    """recall(모델 ∪ 규칙) ≥ max(모델, 규칙) — 인명 양성 전체."""
    positives = _MODEL_MISS_POSITIVES + _MODEL_DETECT_POSITIVES
    model = _guard(person_union=False)
    union = _guard(person_union=True)
    gaz = EgressGuard(ner_backend="gazetteer")  # 규칙 단독

    def recall(guard):
        return sum(_person_hit(guard, p) for p in positives) / len(positives)

    r_model, r_rule, r_union = recall(model), recall(gaz), recall(union)
    assert r_union >= max(r_model, r_rule), (r_model, r_rule, r_union)
    assert r_union > r_model, (r_model, r_union)  # 모델 대비 실질 이득


def test_union_does_not_regress_model_detections():
    """모델이 잡던 인명은 유니온에서도 유지(스팬 중복 제거 후)."""
    union = _guard(person_union=True)
    assert "삼민수" in _persons(union, "고객 삼민수님의 계정 본인확인을 진행해 주세요.")
    assert "김서연" in _persons(union, "고객 김서연님의 계정 본인확인을 진행해 주세요.")


def test_overlapping_span_deduped_by_pipeline_merge():
    """모델·규칙이 같은 인명을 잡으면 파이프라인 병합이 하나로 축약한다."""
    union = _guard(person_union=True)
    # '김서연' = 모델(stub) + 규칙(경칭 게이팅) 둘 다 매치 → 병합 후 1개.
    findings = [f for f in union.inspect("고객 김서연님의 계정 본인확인을 진행해 주세요.").findings
                if f.entity_type == "KR_PERSON"]
    spans = [(f.start, f.end) for f in findings]
    assert len(spans) == len(set(spans)), spans
    for i, a in enumerate(spans):
        for b in spans[i + 1:]:
            assert not (a[0] < b[1] and b[0] < a[1]), (a, b)


def test_location_and_other_pii_channels_unchanged():
    """유니온은 KR_PERSON 만 추가 — 주소/주민번호 등 다른 채널 불변."""
    text = "고객 박예준님의 주민번호는 900101-1234567 이고 주소는 서울특별시입니다."
    model = _guard(person_union=False)
    union = _guard(person_union=True)

    def non_person(guard):
        return sorted((f.entity_type, f.start, f.end)
                      for f in guard.inspect(text).findings
                      if f.entity_type != "KR_PERSON")

    assert non_person(model) == non_person(union), "비-인명 채널이 유니온으로 바뀌었다"
    # 그러나 인명은 유니온이 새로 잡는다(등재 성씨 + 경칭).
    assert _person_hit(union, text) and not _person_hit(model, text)


def test_benign_false_positive_zero_with_union():
    """benign 코퍼스에서 유니온 활성 시에도 오탐 차단 0 유지."""
    benign_path = ROOT / "samples" / "benign_samples.jsonl"
    rows = [json.loads(l) for l in benign_path.open(encoding="utf-8") if l.strip()]
    union = _guard(person_union=True)
    blocked = [r for r in rows if union.inspect(r["prompt"]).blocked]
    assert not blocked, f"benign 오탐 차단 {len(blocked)}건: {[r['prompt'] for r in blocked][:5]}"


def test_gazetteer_backend_union_is_noop():
    """gazetteer 백엔드는 규칙 내장 → 유니온 no-op(중복 배출·source 혼입 없음)."""
    det = KoreanNerDetector(backend="gazetteer", person_union=True)
    assert det.person_union is False
    spans = [s for s in det.detect("고객 김철수님의 계정 본인확인을 진행해 주세요.")
             if s.entity_type == "KR_PERSON"]
    assert {s.source for s in spans} == {"ner:gazetteer"}, "유니온 source 혼입"
    assert len(spans) == len({(s.start, s.end) for s in spans}), "중복 배출"


def test_pipeline_person_union_flag_threads_through():
    """DetectionPipeline(person_union=True) 가 NER 로 전달된다(모델 백엔드일 때 활성)."""
    pipe = DetectionPipeline(ner_backend="gazetteer", person_union=True)
    assert pipe.ner.person_union is False  # gazetteer → no-op


def test_detect_kr_persons_standalone():
    """detect_kr_persons() 모듈 함수가 경칭/직함/문맥 게이팅으로 올바르게 배출한다."""
    # 경칭 게이팅
    spans = list(detect_kr_persons("고객 김철수님의 계정입니다.", source="rule:kr-person"))
    assert any(s.text == "김철수" for s in spans), f"경칭 게이팅 실패: {spans}"

    # 직함 게이팅
    spans = list(detect_kr_persons("이영희 부장 보고서 검토.", source="rule:kr-person"))
    assert any(s.text == "이영희" for s in spans), f"직함 게이팅 실패: {spans}"

    # 문맥 게이팅 (이름 뒤 공백 경계 — 조사 부착 시 candidate RE 불발)
    spans = list(detect_kr_persons("담당자 박민수 앞으로 전달.", source="rule:kr-person"))
    assert any(s.text == "박민수" for s in spans), f"문맥 게이팅 실패: {spans}"

    # 게이팅 없는 인명 — 배출 안 함(오탐 억제)
    spans = list(detect_kr_persons("김철수가 갔다.", source="rule:kr-person"))
    assert not any(s.text == "김철수" for s in spans), f"게이팅 없이 배출됨: {spans}"


def test_person_union_gate_raised_to_090():
    """enforcement 게이트가 person_recall_ci_low >= 0.90 으로 상향되었다."""
    from enforcement.benchmark import PERSON_CI_FLOOR
    assert PERSON_CI_FLOOR >= 0.90, f"게이트 미상향: {PERSON_CI_FLOOR}"


def test_goldset_person_expansion():
    """골드셋 확장: KR_PERSON test n >= 180, CI 하한 충분 표본."""
    rows = [json.loads(l) for l in (ROOT / "samples" / "gold" / "test.jsonl").open(encoding="utf-8")
            if l.strip()]
    person_rows = [r for r in rows if "KR_PERSON" in r.get("expect", [])]
    assert len(person_rows) >= 180, f"KR_PERSON test 표본 부족: {len(person_rows)}"
    unlisted = sum(1 for r in person_rows if r.get("gazetteer_unlisted"))
    listed = len(person_rows) - unlisted
    assert listed >= 100, f"등재 성씨 표본 부족: {listed}"
    assert unlisted >= 50, f"미수록 성씨 표본 부족(누수방지): {unlisted}"
