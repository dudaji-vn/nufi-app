# NuFi + LiteLLM Proxy — Hands-On 튜토리얼

> **이 문서는 무엇인가요?**
> LiteLLM Proxy 위에 NuFi 콜백을 붙여서 **PII 기반 하이브리드 라우팅 + 감사 로깅**을
> 처음부터 끝까지 직접 띄워 보는 실습 가이드입니다.
>
> - **NuFi standalone 게이트웨이 튜토리얼:** [`HANDS_ON.md`](HANDS_ON.md)
> - **통합 경로 레퍼런스:** [`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md) §C (LiteLLM 훅)
> - **설정 파일 상세:** `config/litellm_config.yaml`
> - **콜백 구현:** `gateway/litellm_hook.py`
>
> ⏱ 소요: 약 15~20분 · 사전 조건: Python 3.9+, pip

---

## 0. 왜 LiteLLM 경로인가?

| 기준 | standalone 게이트웨이 | LiteLLM Proxy + NuFi 콜백 |
|------|----------------------|--------------------------|
| 적합 상황 | PoC, 단일 프로바이더 | 이미 LiteLLM 운영 중, 멀티프로바이더 |
| 라우팅·키관리 | NuFi 자체 Router | LiteLLM 이 담당 (폴백·로드밸런싱 포함) |
| PII 탐지·정책 | 동일 (egress_audit 코어) | 동일 (egress_audit 코어) |
| 감사 로깅 | 동일 | 동일 |
| 배포 복잡도 | 낮음 | 중간 (litellm 의존 추가) |

**권장 프로덕션 경로**는 LiteLLM Proxy + 콜백입니다. 기존 OpenAI 호환 코드를 변경하지 않고
보호 계층을 추가할 수 있습니다.

---

## 1. 환경 준비

```bash
cd security

# NuFi 설치
python3 -m pip install -r requirements.txt
python3 -m pip install -e .

# LiteLLM 설치
python3 -m pip install 'litellm[proxy]'

# 에어갭/결정론적 백엔드 고정 (모델 다운로드 불필요)
export EGRESS_NER_BACKEND=gazetteer
```

설치 확인:

```bash
nufi-egress --help          # NuFi CLI
litellm --version           # LiteLLM CLI (1.x 이상)
```

---

## 2. 설정 파일 이해하기

NuFi 의 LiteLLM 설정은 `config/litellm_config.yaml` 한 파일입니다:

```yaml
# config/litellm_config.yaml (핵심 발췌)
model_list:
  # 로컬 모델 — PII 포함 요청은 여기로
  - model_name: nufi-local
    litellm_params:
      model: openai/local-llm
      api_base: http://localhost:8000/v1
      api_key: "sk-local-noauth"
    model_info:
      egress_class: private

  # 클라우드 모델 — PII 없을 때만 허용
  - model_name: nufi-cloud
    litellm_params:
      model: anthropic/claude-3-5-sonnet-20241022
      api_key: os.environ/ANTHROPIC_API_KEY
    model_info:
      egress_class: public

router_settings:
  fallbacks:
    - nufi-cloud: ["nufi-cloud-fast"]
    - nufi-default: ["nufi-cloud"]

litellm_settings:
  # ← 이 한 줄이 NuFi PII 감사 훅을 활성화합니다
  callbacks: gateway.litellm_hook.egress_audit_hook
```

**핵심 포인트:**
- `model_info.egress_class: private` — PII 포함 요청이 라우팅되는 안전한 모델
- `model_info.egress_class: public` — PII 없는 요청만 허용
- `callbacks` — NuFi 의 `EgressAuditHook` 이 모든 요청을 가로채서 PII 감지 실행

---

## 3. 스텁 로컬 LLM 띄우기

실습에서는 실제 LLM 대신 **에코 서버**를 로컬 모델로 사용합니다.
터미널 1에서:

```bash
# 간단한 OpenAI 호환 에코 서버 (포트 8000)
python3 -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, time

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        messages = body.get('messages', [])
        last_msg = messages[-1]['content'] if messages else '(empty)'

        resp = {
            'id': 'echo-001',
            'object': 'chat.completion',
            'created': int(time.time()),
            'model': 'local-echo',
            'choices': [{
                'index': 0,
                'message': {'role': 'assistant', 'content': f'[LOCAL ECHO] {last_msg}'},
                'finish_reason': 'stop'
            }],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}
        }
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        out = json.dumps(resp).encode()
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        # /v1/models 등 health check 용
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        out = json.dumps({'object': 'list', 'data': [{'id': 'local-echo'}]}).encode()
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, fmt, *args):
        print(f'  [stub-llm] {fmt % args}')

print('Stub local LLM listening on :8000')
HTTPServer(('127.0.0.1', 8000), Handler).serve_forever()
"
```

> 실제 환경에서는 vLLM, Ollama, 또는 온프렘 모델 서버가 이 자리를 대신합니다.

---

## 4. LiteLLM Proxy + NuFi 콜백 기동

터미널 2에서:

```bash
cd security

# NuFi 가 PYTHONPATH 에 있어야 콜백이 import 됩니다
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
export EGRESS_NER_BACKEND=gazetteer

# LiteLLM Proxy 기동 (포트 4000)
litellm --config config/litellm_config.yaml \
        --port 4000 \
        --detailed_debug
```

정상 기동 시 다음이 보입니다:

```
INFO:     Uvicorn running on http://0.0.0.0:4000
LiteLLM Proxy is running on port 4000
```

Health check:

```bash
curl -s http://localhost:4000/health | python3 -m json.tool
# → {"healthy_endpoints": [...], ...}
```

---

## 5. 요청 보내기 — 3가지 시나리오

### 시나리오 A: PII 없는 일반 질문 → 클라우드 허용

```bash
curl -s http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nufi-cloud",
    "messages": [{"role": "user", "content": "파이썬에서 리스트를 정렬하는 방법은?"}]
  }' | python3 -m json.tool
```

**기대 결과:**
- HTTP 200, 클라우드 모델이 응답
- NuFi 훅 로그: `PII routing: ... → nufi-cloud (reason=no_pii_detected)`
- 감사 로그에 `outcome: forwarded` 기록

### 시나리오 B: PII 포함 → 로컬로 강제 라우팅

```bash
curl -s http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nufi-cloud",
    "messages": [{"role": "user", "content": "고객 박서연의 전화번호 010-1234-5678로 연락해주세요."}]
  }' | python3 -m json.tool
```

**기대 결과:**
- HTTP 200, **로컬 에코 서버**가 응답 (응답에 `[LOCAL ECHO]` 포함)
- 원래 `nufi-cloud` 로 보냈지만 NuFi 훅이 PII 감지 → `nufi-local` 로 재라우팅
- 감사 로그에 `outcome: routed_local`, `findings: [KR_PERSON, KR_PHONE]` 기록

### 시나리오 C: 강한 PII (주민번호) → 차단 (HTTP 403)

```bash
curl -s -w "\nHTTP_CODE: %{http_code}\n" \
  http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nufi-cloud",
    "messages": [{"role": "user", "content": "김민수 주민번호 900101-1234568 으로 신청서 작성해줘"}]
  }'
```

**기대 결과:**
- HTTP 403, `error: egress_blocked`
- 주민등록번호(strong PII)는 로컬 라우팅으로도 불충분 → 정책에 따라 hard-block
- 감사 로그에 `outcome: blocked`, `entities: [KR_RRN]` 기록

---

## 6. 감사 로그 확인

NuFi 는 모든 요청의 라우팅 결정과 PII 탐지 결과를 감사 로그에 기록합니다:

```bash
# 감사 로그 위치 (기본: logs/ 디렉터리)
ls -la logs/egress_audit*.jsonl 2>/dev/null

# 최근 로그 확인
tail -5 logs/egress_audit*.jsonl | python3 -m json.tool
```

감사 로그 레코드 예시:

```json
{
  "timestamp": "2026-07-05T10:30:00Z",
  "model": "nufi-local",
  "provider": "local",
  "is_public": false,
  "outcome": "routed_local",
  "decision_summary": {
    "routed_to_local": true,
    "reason": "pii_detected",
    "original_model": "nufi-cloud",
    "target_model": "nufi-local",
    "findings_count": 2
  },
  "findings": [
    {"entity_type": "KR_PERSON", "score": 0.95},
    {"entity_type": "KR_PHONE", "score": 0.99}
  ]
}
```

---

## 7. 비용 추적 확인

NuFi 콜백은 로컬/클라우드 라우팅에 따른 비용을 자동 추적합니다:

```python
# Python 에서 비용 요약 조회
from gateway.pii_router import PiiRouter
router = PiiRouter(local_model="nufi-local", cloud_model="nufi-cloud")
# ... 요청 처리 후 ...
print(router.cost_summary())
# {
#   "total_requests": 10,
#   "local_requests": 6,
#   "cloud_requests": 4,
#   "cloud_cost_usd": 0.0032,
#   "local_cost_usd": 0.0,
#   "savings_pct": 60.0
# }
```

PII 가 포함된 요청을 로컬로 라우팅함으로써:
- **클라우드 API 비용 절감** (PII 요청 비율만큼)
- **데이터 유출 위험 제거** (민감 데이터가 외부로 나가지 않음)

---

## 8. Docker Compose 로 한 번에 띄우기

수동으로 서버를 각각 띄우는 대신, Docker Compose 로 한 번에 기동할 수 있습니다:

```bash
# NuFi 게이트웨이 + 감사봇 (standalone 경로)
docker compose -f deploy/docker-compose.yml up -d --build
curl -fsS http://localhost:4000/health

# LiteLLM Proxy 경로는 litellm 을 별도 서비스로 추가하거나,
# 기존 LiteLLM 배포에 콜백만 등록합니다:
#   litellm_settings:
#     callbacks: gateway.litellm_hook.egress_audit_hook
```

---

## 9. 커스터마이징

### 라우팅 정책 변경

`config/litellm_config.yaml` 의 `pii_routing` 섹션:

```yaml
pii_routing:
  enabled: true
  local_model: nufi-local
  cloud_model: nufi-cloud
  force_local_entities: []      # 빈 목록 = 모든 PII → 로컬
  # force_local_entities: [KR_RRN, KR_PERSON]  # 특정 엔티티만 로컬 강제
  fail_closed: true             # 감지 오류 시 로컬로 폴백 (안전)
```

### 탐지 정책 변경

`config/policy.yaml` 에서 엔티티별 액션을 조정:

```bash
# 현재 정책 확인
nufi-egress render

# 정책 변경 후 적용 (무재기동)
nufi-egress apply config/policy.yaml
```

### 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `EGRESS_NER_BACKEND` | `auto` | NER 백엔드 (`gazetteer` / `onnx` / `auto`) |
| `NUFI_LOCAL_MODEL` | `nufi-local` | PII 감지 시 라우팅할 로컬 모델명 |
| `NUFI_CLOUD_MODEL` | `nufi-cloud` | PII 미감지 시 허용할 클라우드 모델명 |
| `NUFI_FAIL_CLOSED` | `1` | 감지 오류 시 로컬 폴백 (`1`=안전, `0`=통과) |

---

## 10. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `ModuleNotFoundError: gateway` | PYTHONPATH 미설정 | `export PYTHONPATH="$(pwd):$PYTHONPATH"` |
| `litellm: command not found` | litellm 미설치 | `pip install 'litellm[proxy]'` |
| 콜백 미동작 (PII 통과) | yaml `callbacks` 오타 | `callbacks: gateway.litellm_hook.egress_audit_hook` 확인 |
| 로컬 모델 연결 실패 | 스텁 서버 미기동 | §3 의 에코 서버 먼저 실행 |
| `403 egress_blocked` 예상치 않게 | strong PII 포함 | 정책 확인: `nufi-egress render` |
| 감사 로그 미생성 | 로그 디렉터리 권한 | `mkdir -p logs && chmod 755 logs` |

---

## 11. 다음 단계

| 관심사 | 다음 문서 |
|--------|-----------|
| standalone 게이트웨이 심화 | [`HANDS_ON.md`](HANDS_ON.md) — 토이 프로젝트 전체 워크스루 |
| CLI 운영 상세 | [`CLI.md`](CLI.md) — 서브커맨드·플래그 레퍼런스 |
| 배포 구성 | [`../deploy/README.md`](../deploy/README.md) — Compose·Helm·에어갭 |
| 정책·프리셋 | [`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md) §2 — 프리셋 선택 가이드 |
| SDK 라이브러리 | [`SDK.md`](SDK.md) — detect·Guard·scan_file API |
| 감사 로그 스키마 | [`MANUAL.md`](MANUAL.md) §3 — JSONL 레코드 필드 상세 |
| 규제 매핑 | [`REPORTING.md`](REPORTING.md) — 한국 규제 5종 대응표 |
| 아키텍처 | [`ARCHITECTURE.md`](ARCHITECTURE.md) — 컴포넌트 다이어그램 |

---

> **요약:** LiteLLM Proxy + NuFi 콜백은 기존 OpenAI 호환 코드를 변경하지 않고
> PII 기반 라우팅·차단·감사를 한 줄(`callbacks`)로 추가하는 **권장 프로덕션 경로**입니다.
> 이 튜토리얼의 3개 시나리오(일반→클라우드, PII→로컬, 강한PII→차단)가
> 실제 운영에서 발생하는 대부분의 케이스를 커버합니다.
