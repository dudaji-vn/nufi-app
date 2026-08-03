# NuFi Egress-Audit — 단일 이미지(탐지코어 + 게이트웨이 + 감사봇).
# CMP-122 (v0.0.2 M1·D2): docker compose / Helm 단일명령 배포 아티팩트.
#
# 한 이미지로 두 역할을 기동한다(같은 코드, 다른 command):
#   - gateway   : OpenAI 호환 게이트웨이(인라인 EgressGuard). uvicorn :4000
#   - audit-bot : 비동기 감사 봇(DetectionPipeline). 공유 /app/logs 큐 tail
# 탐지코어(egress_audit 패키지)는 두 역할에 임베드된다 — 별도 네트워크 서비스 없음(NFR1).
#
# 무거운 백엔드(transformers/onnxruntime)는 기본 미포함(에어갭 코어 우선).
#   docker build --build-arg INSTALL_HEAVY=1 ... 로만 옵트인 번들.
# syntax=docker/dockerfile:1
FROM python:3.12-slim

ARG INSTALL_HEAVY=0
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    EGRESS_NER_BACKEND=gazetteer

WORKDIR /app

# 코어 의존성만(경량). requirements.txt 의 [필수] 블록만 활성.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_HEAVY" = "1" ]; then \
         pip install --no-cache-dir "transformers>=4.40" "onnxruntime>=1.17"; \
       fi

# 앱 소스(탐지코어 + 게이트웨이 + 감사봇 + 캡처(flow tap/content dump) + 운영자 설정).
COPY gateway ./gateway
COPY egress_audit ./egress_audit
COPY enforcement ./enforcement
COPY capture ./capture
COPY config ./config
COPY VERSION ./VERSION

# 게이트웨이 message-store ↔ 감사봇 파일 큐의 공유 마운트 지점.
RUN mkdir -p /app/logs
VOLUME ["/app/logs"]

# 비루트 실행(최소권한).
RUN useradd -u 10001 -m nufi && chown -R nufi /app
USER nufi

EXPOSE 4000

# 게이트웨이 /health 200 → GREEN. 외부 의존 없는 stdlib-only 프로브.
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
  CMD ["python3", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:4000/health', timeout=2).status==200 else 1)"]

# 기본 역할 = 게이트웨이. 감사봇은 compose/Helm 에서 command 오버라이드.
CMD ["python3", "-m", "uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", "4000"]
