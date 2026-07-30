"""CMP-309: 언어 기반 NER 라우팅 — 한국어/영어 자동 분기 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit.normalize import detect_language
from egress_audit.detectors.korean_pii import RawSpan


# ---------------------------------------------------------------------------
# 1) detect_language — Unicode 기반 언어 판별
# ---------------------------------------------------------------------------

def test_detect_language_korean():
    assert detect_language("안녕하세요 오늘 날씨가 좋습니다") == "ko"


def test_detect_language_english():
    assert detect_language("Hello, how are you today?") == "en"


def test_detect_language_mixed():
    # ~15% Hangul → mixed
    assert detect_language("Hello 안녕 world test 세계 foo bar") == "mixed"


def test_detect_language_empty():
    assert detect_language("") == "en"


def test_detect_language_numbers_only():
    assert detect_language("123-456-7890") == "en"


def test_detect_language_threshold_korean():
    """Hangul > 30% → ko"""
    # 10 chars: 4 hangul = 40%
    assert detect_language("가나다라abcdef") == "ko"


def test_detect_language_threshold_english():
    """Hangul < 5% → en"""
    # 100 chars with 1 hangul → ~1%
    text = "a" * 99 + "가"
    assert detect_language(text) == "en"


# ---------------------------------------------------------------------------
# 2) Pipeline language routing — 모킹으로 라우팅 동작 검증
# ---------------------------------------------------------------------------

def test_pipeline_routes_korean_to_kor_ner():
    """한국어 텍스트 → KoreanNerDetector.detect() 호출, multilingual 미호출."""
    from egress_audit.pipeline import DetectionPipeline

    with patch.object(DetectionPipeline, '__init__', lambda self, **kw: None):
        pipe = DetectionPipeline.__new__(DetectionPipeline)
        pipe.pii = MagicMock()
        pipe.pii.detect.return_value = []
        pipe.secrets = MagicMock()
        pipe.secrets.detect.return_value = []
        pipe.confidential = None
        pipe.edm = None

        pipe.ner = MagicMock()
        pipe.ner.detect.return_value = [
            RawSpan("KR_PERSON", "김철수", 0, 3, 0.9, source="ner:koelectra")]
        pipe.multilingual_ner = MagicMock()
        pipe.multilingual_ner.detect.return_value = []

        findings = pipe.analyze("김철수님이 서울에서 근무합니다")
        pipe.ner.detect.assert_called_once()
        pipe.multilingual_ner.detect.assert_not_called()
        assert any(f.entity_type == "KR_PERSON" for f in findings)


def test_pipeline_routes_english_to_multilingual_ner():
    """영어 텍스트 → MultilingualNerDetector.detect() 호출, Korean NER 미호출."""
    from egress_audit.pipeline import DetectionPipeline

    with patch.object(DetectionPipeline, '__init__', lambda self, **kw: None):
        pipe = DetectionPipeline.__new__(DetectionPipeline)
        pipe.pii = MagicMock()
        pipe.pii.detect.return_value = []
        pipe.secrets = MagicMock()
        pipe.secrets.detect.return_value = []
        pipe.confidential = None
        pipe.edm = None

        pipe.ner = MagicMock()
        pipe.ner.detect.return_value = []
        pipe.multilingual_ner = MagicMock()
        pipe.multilingual_ner.detect.return_value = [
            RawSpan("PERSON", "John Smith", 0, 10, 0.95, source="ner:multilingual")]

        findings = pipe.analyze("John Smith lives in New York City")
        pipe.multilingual_ner.detect.assert_called_once()
        pipe.ner.detect.assert_not_called()
        assert any(f.entity_type == "PERSON" for f in findings)


def test_pipeline_routes_mixed_to_both():
    """혼합 텍스트 → 양쪽 NER 모두 호출."""
    from egress_audit.pipeline import DetectionPipeline

    with patch.object(DetectionPipeline, '__init__', lambda self, **kw: None):
        pipe = DetectionPipeline.__new__(DetectionPipeline)
        pipe.pii = MagicMock()
        pipe.pii.detect.return_value = []
        pipe.secrets = MagicMock()
        pipe.secrets.detect.return_value = []
        pipe.confidential = None
        pipe.edm = None

        pipe.ner = MagicMock()
        pipe.ner.detect.return_value = []
        pipe.multilingual_ner = MagicMock()
        pipe.multilingual_ner.detect.return_value = []

        # ~20% Hangul → mixed
        pipe.analyze("Hello 안녕 world test 세계 foo bar")
        pipe.ner.detect.assert_called_once()
        pipe.multilingual_ner.detect.assert_called_once()


def test_pipeline_no_multilingual_fallback_to_korean():
    """multilingual_ner=None 이면 영어도 KoreanNER 폴백."""
    from egress_audit.pipeline import DetectionPipeline

    with patch.object(DetectionPipeline, '__init__', lambda self, **kw: None):
        pipe = DetectionPipeline.__new__(DetectionPipeline)
        pipe.pii = MagicMock()
        pipe.pii.detect.return_value = []
        pipe.secrets = MagicMock()
        pipe.secrets.detect.return_value = []
        pipe.confidential = None
        pipe.edm = None

        pipe.ner = MagicMock()
        pipe.ner.detect.return_value = []
        pipe.multilingual_ner = None

        pipe.analyze("John Smith lives in New York")
        # multilingual_ner 없으면 lang detection 안 하고 ko 경로로 감
        pipe.ner.detect.assert_called_once()


def test_korean_pii_no_regression_gazetteer():
    """기존 한국어 PII 탐지 회귀 없음 — gazetteer 백엔드."""
    from egress_audit.pipeline import DetectionPipeline

    pipe = DetectionPipeline(ner_backend="gazetteer")
    findings = pipe.analyze("주민번호 900101-1234568 전화 010-1234-5678")
    types = {f.entity_type for f in findings}
    assert "KR_RRN" in types
    assert "KR_PHONE" in types


# ---------------------------------------------------------------------------
# 3) MultilingualNerDetector 인터페이스
# ---------------------------------------------------------------------------

def test_multilingual_detector_disabled_backend():
    """모델 미가용 시 disabled 백엔드 → 빈 결과."""
    from egress_audit.detectors.ner import MultilingualNerDetector

    det = MultilingualNerDetector(backend="disabled_test")
    # backend=disabled_test → _build_backend returns None
    assert det.backend_name == "disabled"
    assert list(det.detect("Hello world")) == []


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
