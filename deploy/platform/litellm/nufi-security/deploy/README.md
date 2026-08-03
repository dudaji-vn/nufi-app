# NuFi Egress-Audit — 배포 패키징 (v0.4.18)

게이트웨이 + 탐지코어 + 감사봇을 **단일 명령**으로 기동하는 배포 아티팩트.
SDK·진단(D1)이 있어도 재현 가능한 배포 단위가 없으면 온프렘 PoC 가 불가하므로,
에어갭 우선(NFR1)으로 패키징한다.

## 구성 매핑

| 논리 컴포넌트 | 실행 형태 | 비고 |
|---|---|---|
| 게이트웨이 | `gateway` 서비스 (uvicorn :4000) | OpenAI 호환, 인라인 EgressGuard |
| 탐지코어 (`egress_audit`) | 두 서비스에 임베드 | 별도 네트워크 서비스 없음 (NFR1) |
| 감사 봇 | `audit-bot` 서비스 (daemon) | 공유 `/app/logs` 큐 tail, internal-only 네트워크 |

게이트웨이와 감사봇은 **공유 볼륨(`audit-logs:/app/logs`)** 으로만 통신한다 —
게이트웨이 message-store 가 append, 감사봇 파일 큐가 tail. 외부 브로커/DB 0.

## 빠른 시작 (Docker Compose)

```bash
# 빌드 + 기동 (단일 명령)
docker compose -f deploy/docker-compose.yml up -d --build

# 헬스체크 GREEN
docker compose -f deploy/docker-compose.yml ps          # 두 서비스 healthy
curl -fsS http://localhost:4000/health                  # {"status":"ok",...}

# 정지
docker compose -f deploy/docker-compose.yml down
```

`.env` 로 포트/태그/백엔드 조정:
```bash
cp deploy/.env.example deploy/.env
```

## 코어 외부 네트워크 0 (NFR1)

`audit-bot`(탐지코어)은 compose `core` 네트워크(`internal: true`)에 격리되어
외부 egress 가 없다. NER 기본값은 `gazetteer`(온프렘, 외부 호출 0).
검증 절차는 [airgap/INSTALL.md](airgap/INSTALL.md) §4 참조.

## 무거운 백엔드(선택 번들)

transformers/ONNX 한국어 NER 은 **옵트인 오버레이**로만 — 에어갭 코어 경량 유지.
```bash
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.heavy.yml up -d --build
```

## 에어갭(오프라인) 설치

레지스트리·PyPI 없이 `docker save`/`load` 기반 단일 tar.gz 번들.
- 빌드: `bash deploy/airgap/build-bundle.sh [--heavy]`
- 설치 절차: [airgap/INSTALL.md](airgap/INSTALL.md)

## Kubernetes (Helm 스텁)

단일 파드(게이트웨이 + 감사봇 2 컨테이너, emptyDir 공유 큐) 기동 검증용 스텁.
```bash
helm install nufi deploy/helm/nufi-egress-audit
kubectl get pods -l app.kubernetes.io/instance=nufi      # Ready 2/2
```
프로덕션 HA·PVC·시크릿은 후속 이슈 범위.
