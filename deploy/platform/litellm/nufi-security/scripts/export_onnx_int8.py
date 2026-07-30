"""KoELECTRA NER → ONNX FP32 내보내기 + 동적 INT8 양자화.

설계: docs/design/gateway/m5-bench-hardening-spec.md §2.2 (CMP-78). 이슈: CMP-100.
거버넌스: 보안 도메인 상시 승인(GOVERNANCE.md 규칙3, CMP-96).

`Leo97/KoELECTRA-small-v3-modu-ner` 를 optimum(ORT)로 ONNX 내보내기 후
동적 양자화(QInt8, 가중치 INT8)로 변환한다. 산출물 디렉터리는 기본적으로
저장소 밖(`~/.cache/m5_onnx_int8`)에 둬 대용량 바이너리 커밋을 피한다.

  python3 scripts/export_onnx_int8.py            # 기본(small) 내보내기+양자화
  M5_ONNX_DIR=/path python3 scripts/export_onnx_int8.py

CMP-123 NER base 격상(KR_PERSON CI 하한 0.85↑)은 모델 ID 만 교체하면 된다 —
코드 변경 불필요, 환경변수로 base 모델 지정:
  M5_NER_MODEL_ID=Leo97/KoELECTRA-base-v3-modu-ner python3 scripts/export_onnx_int8.py
산출 INT8 디렉터리를 `M5_ONNX_DIR` 로 가리키면 `egress_audit.detectors.ner`
의 onnx-int8 백엔드가 동일 경로에서 로드한다. 재양자화 후 측정:
  M5_ONNX_DIR=/path python3 scripts/bench_m5.py --backend onnx-int8 --split test

런타임 의존: transformers, onnx, onnxruntime, optimum[onnxruntime]. 에어갭(NFR1)
프로덕션에서는 사전 산출된 INT8 ONNX 를 반입해 동일 경로에 배치한다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 기본 small. CMP-123 격상은 M5_NER_MODEL_ID 로 base 지정(코드 변경 없음).
MODEL_ID = os.environ.get("M5_NER_MODEL_ID", "Leo97/KoELECTRA-small-v3-modu-ner")
DEFAULT_DIR = Path(os.environ.get("M5_ONNX_DIR", Path.home() / ".cache" / "m5_onnx_int8"))

# CMP-145: 채널별(per-channel) 동적 양자화 기본 ON. per-tensor 양자화가 KR_PERSON
# 인명 3건을 노이즈로 잃어 Wilson CI 하한을 0.860→0.832(<0.85)로 떨군 회귀를
# per-channel 이 복원(115/126, CI 하한 0.850 ≥ 0.85). 정합성: tests/test_cmp145_int8_consistency.py.
# 호환 검증용으로 per-tensor 회귀가 필요하면 M5_QUANT_PER_CHANNEL=0.
PER_CHANNEL = os.environ.get("M5_QUANT_PER_CHANNEL", "1") not in ("0", "false", "False")


def main():
    out = DEFAULT_DIR
    fp32_dir = out / "fp32"
    int8_dir = out / "int8"
    fp32_dir.mkdir(parents=True, exist_ok=True)
    int8_dir.mkdir(parents=True, exist_ok=True)

    from optimum.onnxruntime import ORTModelForTokenClassification, ORTQuantizer
    from optimum.onnxruntime.configuration import AutoQuantizationConfig
    from transformers import AutoTokenizer

    print(f"[1/3] FP32 ONNX 내보내기: {MODEL_ID} → {fp32_dir}", flush=True)
    model = ORTModelForTokenClassification.from_pretrained(MODEL_ID, export=True)
    model.save_pretrained(fp32_dir)
    AutoTokenizer.from_pretrained(MODEL_ID).save_pretrained(fp32_dir)

    print(f"[2/3] 동적 INT8 양자화(avx512_vnni, QInt8, per_channel={PER_CHANNEL}) → {int8_dir}",
          flush=True)
    quantizer = ORTQuantizer.from_pretrained(fp32_dir)
    # CPU 동적 양자화: 가중치 INT8. AVX512-VNNI 미지원 CPU 도 동적 경로는 동작.
    # per_channel=True(CMP-145 기본): 가중치 출력채널별 스케일 → 양자화 정밀도 손실 최소화.
    qconfig = AutoQuantizationConfig.avx512_vnni(is_static=False, per_channel=PER_CHANNEL)
    quantizer.quantize(save_dir=int8_dir, quantization_config=qconfig)
    AutoTokenizer.from_pretrained(MODEL_ID).save_pretrained(int8_dir)

    # 산출물 크기 보고(FP32 대비 INT8 축소 확인)
    def dir_mb(p):
        return round(sum(f.stat().st_size for f in p.glob("*.onnx")) / 1e6, 1)

    print(f"[3/3] 완료. FP32 onnx={dir_mb(fp32_dir)}MB  INT8 onnx={dir_mb(int8_dir)}MB", flush=True)
    print(f"INT8_DIR={int8_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
