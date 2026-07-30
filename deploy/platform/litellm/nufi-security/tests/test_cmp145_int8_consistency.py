"""CMP-145 — INT8 재양자화 정합성 검증 (requantization consistency).

설계 근거: docs/M5_MEASUREMENT_REPORT.md · docs/reports/CMP-123-d3-accuracy-perf.md.
이슈: CMP-145 (v0.0.5 B2). 보드 승인 6e02b6aa (approved 2026-06-28).

목적
----
INT8 동적 양자화가 KR_PERSON 탐지를 FP32 원본 대비 **퇴화시키지 않음**을 고정
코퍼스로 검증한다. CMP-123 에서 per-tensor INT8 가 양자화 노이즈로 인명 3건을
잃어 Wilson CI 하한이 0.860→0.832 로 떨어진 회귀가 재발하지 않도록 가드한다.

검증 불변식
-----------
1. **정합성:** 동일 모델의 FP32 ONNX 와 INT8 ONNX 를 같은 인명 코퍼스에 태워,
   INT8 이 FP32 가 잡은 KR_PERSON 스팬을 허용 오차(TOL) 내에서 재현한다.
2. **must-hold:** 명백한 인명(경칭/직함 동반)은 INT8 도 반드시 잡는다(무손실).

실행: PYTHONPATH=~/.cache/m5_libs pytest tests/test_cmp145_int8_consistency.py
모델 스택/ONNX 산출물이 없으면(에어갭 CI) skip — 침묵 금지(CMP-78 §2.1).
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 측정 대상 ONNX 산출 디렉터리(fp32/ 와 int8/ 를 형제로 가짐).
ONNX_BASE = Path(os.environ.get("M5_ONNX_DIR", os.path.expanduser("~/.cache/m5_onnx_int8")))

# must-hold: 양자화와 무관하게 반드시 인명으로 잡혀야 하는 고-신뢰 표본(경칭/직함/문맥).
MUST_HOLD = [
    "담당자 김민수 님께 전달 부탁드립니다.",
    "발신: 이영희 과장 / 수신: 박철수 부장",
    "고객 최지우 님의 계약 건으로 연락드립니다.",
    "환자 정대현 씨 진료 기록을 확인했습니다.",
    "예금주 한소희 명의로 입금되었습니다.",
]

# 정합성 코퍼스: 다양한 문맥의 인명(must-hold 포함). FP32 기준선과 INT8 을 비교.
CONSISTENCY_CORPUS = MUST_HOLD + [
    "회의에 강동원 윤아 두 분이 참석합니다.",
    "신청자 오세훈, 보호자 임수정.",
    "작성자 한지민 기자가 보도했습니다.",
    "수취인 권상우 앞으로 발송하였습니다.",
    "이사 송강호 께서 승인하셨습니다.",
]

TOL = 0.0  # INT8 이 FP32 인명 스팬을 놓쳐도 되는 허용 비율(0 = 무손실 요구).


def _onnx_dirs_ready():
    """fp32/ · int8/ 양쪽에 config.json + .onnx 가 있고 런타임 스택이 설치됐는가."""
    try:
        import optimum.onnxruntime  # noqa: F401
        import transformers  # noqa: F401
    except Exception:
        return False
    for sub in ("fp32", "int8"):
        d = ONNX_BASE / sub
        if not (d / "config.json").is_file():
            return False
        if not glob.glob(str(d / "*.onnx")):
            return False
    return True


pytestmark = pytest.mark.skipif(
    not _onnx_dirs_ready(),
    reason=f"INT8/FP32 ONNX 산출물 또는 모델 스택 미설치({ONNX_BASE}) — `scripts/export_onnx_int8.py` 후 측정")


def _build_pipe(sub: str):
    """주어진 ONNX 하위 디렉터리(fp32|int8)에서 token-classification 파이프라인 빌드."""
    from optimum.onnxruntime import ORTModelForTokenClassification
    from transformers import AutoConfig, AutoTokenizer, pipeline

    d = ONNX_BASE / sub
    onnx_files = [os.path.basename(p) for p in glob.glob(str(d / "*.onnx"))]
    file_name = next((f for f in ("model_quantized.onnx", "model.onnx") if f in onnx_files),
                     onnx_files[0])
    model = ORTModelForTokenClassification.from_pretrained(
        d, config=AutoConfig.from_pretrained(d), file_name=file_name)
    tok = AutoTokenizer.from_pretrained(d)
    return pipeline("token-classification", model=model, tokenizer=tok,
                    aggregation_strategy="simple")


_LABEL_MAP = {"PS": "KR_PERSON", "PER": "KR_PERSON", "LC": "KR_LOCATION", "LOC": "KR_LOCATION"}


def _person_spans(pipe, text):
    """파이프라인 출력에서 KR_PERSON 스팬 집합(start,end) 추출 (ner.py 매핑과 동일)."""
    out = set()
    for ent in pipe(text):
        grp = str(ent.get("entity_group", "")).upper()
        mapped = next((v for k, v in _LABEL_MAP.items() if grp.startswith(k)), None)
        if mapped == "KR_PERSON":
            out.add((int(ent["start"]), int(ent["end"])))
    return out


def _has_person(pipe, text):
    return len(_person_spans(pipe, text)) > 0


@pytest.fixture(scope="module")
def pipes():
    return _build_pipe("fp32"), _build_pipe("int8")


def test_int8_must_hold_no_person_loss(pipes):
    """must-hold 고-신뢰 인명은 INT8 도 무손실로 탐지(양자화 회귀 가드)."""
    _fp32, int8 = pipes
    missed = [t for t in MUST_HOLD if not _has_person(int8, t)]
    assert not missed, f"INT8 이 must-hold 인명을 놓침(양자화 퇴화): {missed}"


def test_int8_consistent_with_fp32_person(pipes):
    """INT8 이 FP32 가 잡은 KR_PERSON '존재'를 TOL 내에서 재현(정합성)."""
    fp32, int8 = pipes
    fp32_pos = [t for t in CONSISTENCY_CORPUS if _has_person(fp32, t)]
    assert fp32_pos, "FP32 기준선이 인명을 전혀 못 잡음 — 코퍼스/모델 점검 필요"
    int8_recovered = [t for t in fp32_pos if _has_person(int8, t)]
    loss = (len(fp32_pos) - len(int8_recovered)) / len(fp32_pos)
    assert loss <= TOL, (
        f"INT8 정합성 위반: FP32 인명 {len(fp32_pos)}건 중 INT8 재현 "
        f"{len(int8_recovered)}건(손실 {loss:.1%} > 허용 {TOL:.1%}). "
        f"누락: {[t for t in fp32_pos if not _has_person(int8, t)]}")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
