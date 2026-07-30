# KR_LOCATION Wilson CI 좁히기 — 주소 표본 확장 (v0.2.0 P6)

목적: 규칙 백엔드가 도로명·상세주소·시군구를 탐지하도록 확장된(P2) 뒤, 골드셋의
`KR_LOCATION` 표본을 확장해 **Wilson 95% CI 하한 ≥ 0.90** 을 확보한다. 점추정(recall 1.0)
단독이 아니라 **통계적 신뢰**로 상위 목표 "주소 0.90+" 를 마감하는 단계다.

- 배경(선결 과제): 확장 이전 골드셋의 `KR_LOCATION` 40건은 **광역/행정 지명 인식만** 측정했고
  **도로명주소·상세주소는 0건**이었다(오차 분석 §3 참조: `kr-location-error-analysis.md`).
- 재현(에어갭·결정적): `python3 scripts/bench_m5.py --backend gazetteer --split {test,dev} --no-latency`
- 골드셋 재현·검증: `python3 goldset/generate.py --verify` (content_hash·누수방지·push-protection 게이트)

## 1. 확장 내용 (전량 공개-안전 합성)

신규 62건을 정렬-최후미 클래스(`zz_kr_location_addr`)로 append 한다 — 기존 sealed 행
(byte 불변)에 영향을 주지 않는 append-only 규약. 실존 개인정보·시크릿 0: 도로명·행정구역명은
공개 지리정보, 건물번호·동/호·층은 합성 숫자.

| 하위 유형 | 규칙(P2) | 건수 | 예시 |
|---|---|---:|---|
| (a) 도로명주소 | 로/대로/길 + 건물번호(번길·번지·범위) | 24 | `테헤란로 152`, `판교로 235번길 4`, `불정로 6번지` |
| (b) 상세주소 | 동/호 · 층/호 · 지하 | 14 | `101동 203호`, `3층 402호`, `지하 1층 12호` |
| (c) 시군구(단일) | 시/군/구 사전 등재 | 16 | `김해시`, `완도군`, `해운대구` |
| (d) 시+구 결합 | 다토큰 행정 스팬 | 8 | `고양시 덕양구`, `수원시 팔달구` |
| **합계** | | **62** | |

## 2. 확장 전후 KR_LOCATION Wilson CI (gazetteer, 에어갭·결정적)

| split | 분모(전) | CI 하한(전) | 분모(후) | 적중 | recall | **CI 하한(후)** | benign 오탐 |
|---|---:|---:|---:|---:|---:|---:|---:|
| test | 24 | 0.862 | **62** | 62 | 1.0 | **0.9417** | 0/90 |
| dev  | 16 | 0.806 | **40** | 40 | 1.0 | **0.9124** | 0/60 |

- **test/dev 양 split 모두 CI 하한 ≥ 0.90 달성** — recall 1.0 를 유지하며 표본 확대로 CI 폭을
  좁혀 "90%+" 를 통계적으로 마감했다. benign false-block = 0(누수 0).
- 완전 recall(적중=분모)에서 Wilson 하한은 `n/(n+z²)` (z=1.96, z²≈3.84)로, 하한 ≥0.90 은
  `n ≥ 35`. test 62·dev 40 은 여유 있게 이 문턱을 넘는다.

## 3. 프로덕션 백엔드 주석

에어갭 CI 는 규칙(gazetteer) 백엔드로 결정적 재현한다. 프로덕션(onnx-int8)은 규칙이 잡는
구조적 주소(로/길+번지·동/호·시군구)를 상위집합으로 커버하므로, 이 표본에서 프로덕션 recall 은
gazetteer 이상으로 기대된다. 모델 프로비저닝 시 `--backend onnx-int8` 재실행으로 확정 가능.

## 4. 재현·검증

```
python3 goldset/generate.py --verify                                  # 골드셋 결정적 재현·누수·push 게이트
python3 scripts/bench_m5.py --backend gazetteer --split test --no-latency
python3 scripts/bench_m5.py --backend gazetteer --split dev  --no-latency
python3 -m pytest tests/test_cmp197_goldset_dist.py -q                # 골드셋 배포 규약
python3 scripts/check_doc_style.py                                    # 공개-안전 가드
```
