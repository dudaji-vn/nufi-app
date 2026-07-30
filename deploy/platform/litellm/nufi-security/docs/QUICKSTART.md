# Quickstart -- 0에서 첫 스캔까지 2분

NuFi 를 처음 쓰는 개발자가 **설치 → 초기화 → 스캔 → 탐색**까지 빠르게 돌려 보는 가이드입니다.

---

## 1. 설치

```bash
cd security
python3 -m pip install -r requirements.txt   # 코어: PyYAML·fastapi·uvicorn·httpx
python3 -m pip install -e .                   # nufi-egress CLI 진입점 등록(선택)
```

> `pip install -e .` 를 건너뛰면 `nufi-egress` 대신 `python3 -m enforcement.cli` 로 동일하게 실행합니다.

---

## 2. 프로젝트 초기화

```bash
nufi-egress init
```

`config/`, `.nufiignore`, pre-commit 훅을 한 번에 세팅합니다.
Git 훅까지 설치하려면 `--install-hook` 플래그를 추가하세요.

---

## 3. 첫 스캔

```bash
nufi-egress scan . --stats
```

현재 디렉터리에서 PII 를 찾고, 요약 통계(파일 수·탐지 건수·엔티티 분포)를 출력합니다.

```bash
# CI 연동: PII 가 있으면 비제로 종료
nufi-egress scan . --fail-on-pii
```

---

## 4. 텍스트 한 줄 점검

```bash
# PII 탐지 + 정책 + 라우팅 판정을 한 번에
nufi-egress inspect --text "김민수님 주민번호 900101-1234568"

# PII 마스킹
nufi-egress mask --text "김민수님 전화번호 010-1234-5678"

# PII 리댁션
nufi-egress redact --text "김민수님 이메일 hong@example.com"
```

---

## 5. 인터랙티브 탐색

```bash
nufi-egress playground
```

REPL 환경에서 텍스트를 입력하며 탐지·마스킹·라우팅 결과를 즉시 확인합니다.

---

## 6. 배선 자가진단

```bash
nufi-egress doctor
```

설정·탐지 엔진·감사 로거 등 6개 항목의 정상 동작을 확인합니다.

---

## 7. 통합 테스트

```bash
nufi-egress test
```

내장 테스트 스위트를 실행해 환경이 정상인지 검증합니다.

---

## 8. 실시간 감시

```bash
nufi-egress watch src/ --once
```

디렉터리 파일 변경 시 PII 를 자동 탐지합니다. `--once` 는 한 번 스캔 후 종료합니다.

---

## 9. HTTP API 모드

```bash
nufi-egress serve --port 8000 &
curl -s localhost:8000/detect -H "Content-Type: application/json" \
  -d '{"text":"김민수님 전화 010-1234-5678"}'
```

NuFi 기능을 REST API 로 노출하여 다른 마이크로서비스에서 HTTP 호출로 PII 탐지·라우팅·마스킹을 사용합니다. 엔드포인트: `/detect`, `/route`, `/inspect`, `/mask`, `/redact`, `/injection`, `/pipeline`, `/explain`, `/scan`, `/posture`, `/summary`, `/stats`, `/badge/{type}`, `/health`. 전체 상세는 [`CLI.md`](CLI.md) 의 `serve` 섹션을 참고하세요.

---

## 다음 단계

| 하고 싶은 것 | 문서 |
|---|---|
| CLI 전체 서브커맨드 레퍼런스 | [`CLI.md`](CLI.md) |
| Python SDK 라이브러리 API | [`SDK.md`](SDK.md) |
| 손으로 따라하며 익히기 (20~30분 실습) | [`HANDS_ON.md`](HANDS_ON.md) |
| 내 LLM 서비스에 통합하기 | [`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md) |
| PII 기반 하이브리드 라우팅 | [`PII_ROUTING.md`](PII_ROUTING.md) |
| 한국 규제 증빙 리포트 | [`REPORTING.md`](REPORTING.md) |
| SDK 예시 스크립트 11종 | [`../examples/README.md`](../examples/README.md) |
