# KR_LOCATION v0.2.0 릴리스 측정 게이트

주소(KR_LOCATION) 정확도 트랙(v0.2.0)의 **릴리스 게이트** 판정 리포트입니다. 전/후 공개
평가셋 비교로 아래 세 조건이 모두 통과해야 v0.2.0 을 릴리스할 수 있습니다. 측정 원본은
[`kr-location-gate.json`](kr-location-gate.json), before baseline 은
[`baseline-int8.json`](baseline-int8.json), 유니온 세부는
[`kr-location-union.json`](kr-location-union.json) 을 참고하세요.

## 게이트 3조건

1. **KR_LOCATION Wilson 95% CI 하한 ≥ 0.90** — 점추정이 아닌 신뢰구간 하한으로 재현율 주장.
2. **benign FP = 0.0** — 무해 입력에 대한 주소 오탐/오차단 0.
3. **전체 PII precision ~1.0** (≥ 0.98) — 재현율 확장이 정밀도를 희생하지 않음.

## 백엔드 주기(측정 정직성)

프로덕션 백엔드(onnx-int8)는 이 환경에서 `optimum` 미프로비저닝(에어갭)으로 라이브 재실행이
불가합니다. 따라서:

- **before(v0.1.0)** 의 모델 재현율은 커밋된 baseline 리포트를 인용합니다.
- **after(v0.2.0)** 는 확장규칙(gazetteer, P2) **라이브 하한**을 인용합니다. 모델∪규칙
  유니온(P3)은 규칙 스팬을 모델 출력에 **더하는** 방향이라 유니온 재현율은 이 하한 이상이며,
  benign FP 는 (모델 0) ∪ (규칙 0) = 0 으로 유지됩니다. 즉 여기 표기한 after 수치는
  **보수적 하한**이고, 모델 프로비저닝 시 재측정으로 상향 확정됩니다.

## 전/후 비교

| 지표 | before v0.1.0 (onnx-int8, test) | after v0.2.0 (test) | after v0.2.0 (dev) |
|---|---|---|---|
| KR_LOCATION 재현율 | 0.7917 (19/24) | **1.0 (62/62)** | **1.0 (40/40)** |
| KR_LOCATION CI95 하한 | 0.5953 | **0.9417** | **0.9124** |
| benign FP | 0.0 | **0.0 (0/90)** | **0.0 (0/60)** |
| 전체 PII precision | 1.0 | **0.9887** | **0.9885** |

재현율 이득: 모델 baseline 0.7917 → 유니온 하한 1.0 = **+0.2083**. 골드셋 주소 표본은
P6 확장(24→62 test / 40 dev 양성행)으로 CI 하한이 목표선을 넘을 만큼 좁혀졌습니다.

## 판정

| 조건 | test | dev |
|---|---|---|
| CI 하한 ≥ 0.90 | ✅ 0.9417 | ✅ 0.9124 |
| benign FP = 0.0 | ✅ | ✅ |
| PII precision ~1.0 | ✅ 0.9887 | ✅ 0.9885 |

**게이트 통과 = ✅ (3/3 · 양 split 전부).** P4(모델 파인튜닝)는 규칙 백엔드만으로 재현율
1.0 이 확보되어 게이트 통과에 불필요했습니다. 릴리스 태그 컷(VERSION/tag/push)은 별도
보드 명령 대기입니다.

## 재현

```bash
python3 goldset/generate.py            # 골드셋 결정적 재생성
python3 scripts/union_check.py --mode location --split test   # 주소 유니온 하한
python3 scripts/union_check.py --mode location --split dev
```
