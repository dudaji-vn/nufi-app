# NuFi Egress-Audit — 에어갭(오프라인) 설치 가이드

| 항목 | 값 |
|---|---|
| **NuFi 버전** | v0.4.18 |
| **Docker Engine** | ≥ 24.0 |
| **Docker Compose** | v2.x (`docker compose` 서브커맨드) |
| **Python (빌드 호스트)** | ≥ 3.10 |

대상: 인터넷이 차단된 온프렘/폐쇄망 호스트. 레지스트리·PyPI 접근 없이
`docker save`/`docker load` 기반으로 게이트웨이+탐지코어+감사봇을 기동한다.
외부 브로커·DB·레지스트리 0 (NFR1).

---

## 0. 사전 요건 (에어갭 호스트)

- Docker Engine ≥ 24.0, Docker Compose v2 (`docker compose version`).
- 게이트웨이 노출 포트(기본 4000) 사용 가능.
- 무거운 NER 백엔드는 **선택**. 코어는 gazetteer 로 외부 호출 0.

---

## 1. 연결된 빌드 호스트에서 번들 생성

레지스트리 푸시 없이 단일 tar.gz 만 만든다.

```bash
# 코어(경량) 번들
bash deploy/airgap/build-bundle.sh

# 무거운 백엔드 포함(transformers/ONNX) 번들 — 별도 -heavy 태그
bash deploy/airgap/build-bundle.sh --heavy
```

산출물: `dist/nufi-egress-audit-v0.4.18[-heavy]-airgap.tar.gz`
(이미지 `images.tar` + compose/Helm + 본 가이드 + `MANIFEST.txt` 무결성).

USB/내부 전송 등 **물리/단방향 경로**로 에어갭 호스트에 옮긴다.

---

## 2. 에어갭 호스트에서 로드 + 기동

```bash
mkdir -p nufi && tar -xzf nufi-egress-audit-v0.4.18-airgap.tar.gz -C nufi
cd nufi

# docker load + sha256 무결성 검증
bash load-bundle.sh

# (선택) 포트/태그 조정
cp deploy/.env.example deploy/.env

# 단일명령 기동
docker compose -f deploy/docker-compose.yml up -d
```

`up` 은 인터넷을 전혀 사용하지 않는다(이미지 로컬 로드 완료, 의존성 이미지 내장).

---

## 3. 헬스체크 GREEN 확인

```bash
# 컨테이너 상태 — 둘 다 healthy 여야 함
docker compose -f deploy/docker-compose.yml ps

# 게이트웨이 헬스
curl -fsS http://localhost:4000/health
# → {"status":"ok","ner_backend":"gazetteer"}
```

`gateway`/`audit-bot` 모두 `healthy` 면 수용기준 GREEN.

---

## 4. 코어 외부 네트워크 0 검증 (선택)

감사봇(탐지코어)은 `internal: true` 네트워크에 격리되어 egress 가 없다.

```bash
# 감사봇 컨테이너에서 외부로 나가지 못함을 확인(실패가 정상)
docker compose -f deploy/docker-compose.yml exec audit-bot \
  python3 -c "import socket; socket.create_connection(('1.1.1.1',53),2)" \
  && echo "예상과 다름: egress 가능" || echo "OK: 코어 외부 egress 0"
```

---

## 5. 운영 명령

```bash
# 로그
docker compose -f deploy/docker-compose.yml logs -f gateway audit-bot
# 정지
docker compose -f deploy/docker-compose.yml down
# 감사 결과(findings/alerts) — 공유 볼륨 audit-logs:/app/logs
docker compose -f deploy/docker-compose.yml exec audit-bot \
  sh -c 'tail -n 20 /app/logs/audit_findings.jsonl 2>/dev/null || echo "(아직 finding 없음)"'
```

---

## 6. 무거운 백엔드 번들(선택)

`--heavy` 번들을 로드한 경우, heavy 오버레이로 기동한다.

```bash
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.heavy.yml up -d
```

코어 경량 번들과 이미지 태그가 분리(`...-heavy`)되어 있어, 에어갭 코어를
가볍게 유지하면서 필요 환경에만 무거운 NER 을 배치할 수 있다.
