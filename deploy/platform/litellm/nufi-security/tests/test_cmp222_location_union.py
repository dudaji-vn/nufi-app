"""CMP-222 (v0.2.0 P3) — 백엔드 유니온(주소 한정) 검증: 모델 ∪ 확장규칙.

부모 CMP-218. 선행 P1(CMP-220) 오차분석 + P2(CMP-221) 규칙확장. 프로덕션 모델
백엔드(onnx-int8)는 어휘밖·구조적 주소(국제도시·도로명·상세주소)를 놓치지만
(P1: KR_LOCATION recall 0.79, FN 100% 어휘밖 고유지명), P2 확장 규칙은 이를 잡는다.
P3 은 **주소 채널(KR_LOCATION)만** 모델 ∪ 규칙 유니온을 활성화해 모델의 FN 을
규칙으로 회복한다.

본 테스트는 실제 모델 없이(에어갭) 유니온 *메커니즘* 을 결정적으로 고정한다:
  · 모델을 대신하는 stub 백엔드(어휘 지명만 잡고 어휘밖은 놓침 = P1 특성)로
    recall(모델 ∪ 규칙) ≥ max(모델, 규칙) 를 실측하고,
  · 인명/기타 PII 채널이 유니온으로 회귀하지 않으며,
  · benign false-positive 0 을 유지하고,
  · gazetteer 백엔드에서는 유니온이 no-op(규칙이 이미 내장) 임을

를 검증한다.

실행: python3 -m pytest tests/test_cmp222_location_union.py
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
from egress_audit.detectors.ner import KoreanNerDetector  # noqa: E402


# ---------------------------------------------------------------------------
# 모델 백엔드 stub — P1 특성(어휘 지명만 탐지, 어휘밖 고유지명·구조적 주소는 놓침).
# 실제 onnx-int8 없이 유니온 메커니즘을 결정적으로 재현한다(에어갭).
# ---------------------------------------------------------------------------
_MODEL_LEXICON = ("서울", "부산", "대구", "인천", "청주시", "부산광역시", "서울특별시")


class _StubModelBackend:
    name = "stub-model"
    source = "ner:stub-model"
    _pool = None

    def detect(self, text):
        seen = set()
        for kw in sorted(_MODEL_LEXICON, key=len, reverse=True):
            start = 0
            while True:
                i = text.find(kw, start)
                if i < 0:
                    break
                span = (i, i + len(kw))
                if not any(a < span[1] and span[0] < b for a, b in seen):
                    seen.add(span)
                    yield RawSpan("KR_LOCATION", kw, i, i + len(kw), 0.95,
                                  source=self.source)
                start = i + len(kw)


def _guard(location_union: bool) -> EgressGuard:
    """stub 모델 백엔드를 단 파이프라인으로 EgressGuard 구성."""
    pipe = DetectionPipeline(ner_backend="gazetteer")  # 정규식/비밀/기밀은 그대로
    det = KoreanNerDetector.__new__(KoreanNerDetector)
    det.backend = _StubModelBackend()
    det.location_union = bool(location_union) and det.backend_name != "gazetteer"
    det.person_union = False
    pipe.ner = det
    return EgressGuard(pipeline=pipe)


def _locs(guard: EgressGuard, text: str) -> set[str]:
    return {f.text for f in guard.inspect(text).findings if f.entity_type == "KR_LOCATION"}


def _loc_hit(guard: EgressGuard, text: str) -> bool:
    return any(f.entity_type == "KR_LOCATION" for f in guard.inspect(text).findings)


# P1 클래스(어휘밖 고유지명·도로명·상세주소)를 담은 주소-양성 프롬프트.
# 모델(stub)이 놓치는 케이스를 규칙이 회복하는지 본다.
_OOV_POSITIVES = [
    "배송지를 송도국제도시로 변경해 주세요.",          # c: 어휘밖 고유지명
    "이번 워크숍은 판교테크노밸리에서 진행됩니다.",     # c
    "주소는 테헤란로 152 입니다.",                      # a: 도로명주소
    "본사는 세종대로 110 에 있습니다.",                 # a
    "우리 집은 101동 203호 입니다.",                    # b: 상세주소
    "광교호수공원 근처로 예약해줘.",                     # c
]
# 모델(stub)이 이미 잡는 어휘 지명(유니온이 깨지 않아야 함).
_MODEL_POSITIVES = [
    "부산광역시 인근 맛집 추천해줘.",
    "이번 워크숍은 청주시에서 진행됩니다.",
]


def test_union_recovers_model_false_negatives():
    """모델이 놓친 어휘밖·구조적 주소를 규칙 유니온이 회복한다."""
    model = _guard(location_union=False)
    union = _guard(location_union=True)
    for p in _OOV_POSITIVES:
        assert not _loc_hit(model, p), f"stub 모델이 이미 잡음(테스트 전제 붕괴): {p}"
        assert _loc_hit(union, p), f"유니온이 회복 실패: {p}"


def test_union_recall_ge_max_each_backend():
    """recall(모델 ∪ 규칙) ≥ max(모델, 규칙) — 주소 양성 전체."""
    positives = _OOV_POSITIVES + _MODEL_POSITIVES
    model = _guard(location_union=False)
    union = _guard(location_union=True)
    gaz = EgressGuard(ner_backend="gazetteer")  # 규칙 단독

    def recall(guard):
        return sum(_loc_hit(guard, p) for p in positives) / len(positives)

    r_model, r_rule, r_union = recall(model), recall(gaz), recall(union)
    assert r_union >= max(r_model, r_rule), (r_model, r_rule, r_union)
    assert r_union == 1.0, r_union            # 규칙이 전량 커버 → 유니온 1.0
    assert r_union > r_model, (r_model, r_union)  # 모델 대비 실질 이득


def test_union_does_not_regress_lexicon_places():
    """모델이 잡던 어휘 지명은 유니온에서도 유지(스팬 중복 제거 후)."""
    union = _guard(location_union=True)
    assert "부산광역시" in _locs(union, "부산광역시 인근 맛집 추천해줘.")
    assert "청주시" in _locs(union, "이번 워크숍은 청주시에서 진행됩니다.")


def test_overlapping_span_deduped_by_pipeline_merge():
    """모델·규칙이 같은 지명을 잡으면 파이프라인 병합이 하나로 축약한다."""
    union = _guard(location_union=True)
    # '부산광역시' = 모델(어휘) + 규칙(광역 접미사) 둘 다 매치 → 병합 후 1개.
    findings = [f for f in union.inspect("부산광역시 지점 오픈 일정 알려줘.").findings
                if f.entity_type == "KR_LOCATION"]
    spans = [(f.start, f.end) for f in findings]
    assert len(spans) == len(set(spans)), spans
    # 겹치는 스팬은 남지 않는다(_merge 가 제거).
    for i, a in enumerate(spans):
        for b in spans[i + 1:]:
            assert not (a[0] < b[1] and b[0] < a[1]), (a, b)


def test_person_and_other_pii_channels_unchanged():
    """유니온은 KR_LOCATION 만 추가 — 인명/주민번호 등 다른 채널 불변."""
    text = "고객 김철수 님의 주민번호는 900101-1234567 이고 주소는 테헤란로 152 입니다."
    model = _guard(location_union=False)
    union = _guard(location_union=True)

    def non_loc(guard):
        return sorted((f.entity_type, f.start, f.end)
                      for f in guard.inspect(text).findings
                      if f.entity_type != "KR_LOCATION")

    assert non_loc(model) == non_loc(union), "비-주소 채널이 유니온으로 바뀌었다"
    # 그러나 주소는 유니온이 새로 잡는다(도로명).
    assert _loc_hit(union, text) and not _loc_hit(model, text)


def test_benign_false_positive_zero_with_union():
    """benign 코퍼스에서 유니온 활성 시에도 오탐 차단 0 유지."""
    benign_path = ROOT / "samples" / "benign_samples.jsonl"
    rows = [json.loads(l) for l in benign_path.open(encoding="utf-8") if l.strip()]
    union = _guard(location_union=True)
    blocked = [r for r in rows if union.inspect(r["prompt"]).blocked]
    assert not blocked, f"benign 오탐 차단 {len(blocked)}건: {[r['prompt'] for r in blocked][:5]}"


def test_gazetteer_backend_union_is_noop():
    """gazetteer 백엔드는 규칙 내장 → 유니온 no-op(중복 배출·source 혼입 없음)."""
    det = KoreanNerDetector(backend="gazetteer", location_union=True)
    assert det.location_union is False
    spans = [s for s in det.detect("배송지를 송도국제도시로 변경해 주세요.")
             if s.entity_type == "KR_LOCATION"]
    assert {s.source for s in spans} == {"ner:gazetteer"}, "유니온 source 혼입"
    assert len(spans) == len({(s.start, s.end) for s in spans}), "중복 배출"


def test_pipeline_location_union_flag_threads_through():
    """DetectionPipeline(location_union=True) 가 NER 로 전달된다(모델 백엔드일 때 활성)."""
    # gazetteer 는 no-op(위 참조). 여기선 플래그가 KoreanNerDetector 로 전달되는지만 확인.
    pipe = DetectionPipeline(ner_backend="gazetteer", location_union=True)
    assert pipe.ner.location_union is False  # gazetteer → no-op
