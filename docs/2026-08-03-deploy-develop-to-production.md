# Đưa `develop` lên production — runbook

Trạng thái tại thời điểm viết: `develop` đi trước `main` **125 commit / 567 file**.
Đây không phải bản vá nhỏ — nó **thay một service** ở gateway và **gỡ toàn bộ
lớp bảo vệ trong app chat**. Thứ tự deploy quyết định có khoảng trống bảo mật
hay không.

---

## 0. Trạng thái production đo được (2026-08-03)

Railway CLI ở `~/.railway/bin/railway` (không nằm trong PATH mặc định của shell
không-login — dùng đường dẫn đầy đủ hoặc `export PATH="$HOME/.railway/bin:$PATH"`).
Đăng nhập: `sun@dudaji.com`. Project `nufi` — `06c8dad0-f74c-412e-b9cf-f563676520d5`,
env `production` — `57cf6b17-ab70-466c-a7d8-fcbbe8b01d49`.

| Service | Nguồn | Trạng thái |
|---|---|---|
| `nufi-chat` | image `ghcr.io/dudaji-vn/nufichat:v0.1.10` qua biến `BASE` | chat.nufi.me |
| `nufichat-admin-panel` | image `…/nufichat-admin-panel:v0.0.4` (06/07) | admin.app.nufi.me |
| `nufi-docs` | ⚠️ repo **`dudaji-vn/nufi-docs`** (đã archive) | **đóng băng từ 20/07** |
| `nufi-console` | — | 0 file đổi, bỏ qua |

`BACKEND_BASE_URL = https://api.codechi.me/v1` → **chat trên Railway đi qua
Cloudflare tunnel vào gateway trên VM.** Hai phần dính chặt; mục 3 là bắt buộc.

Biến rác còn sót trên `nufi-chat`: `GUARDRAIL_ENABLED`, `GUARDRAIL_PII_INPUT_MODE`.
Chat mới không đọc biến `GUARDRAIL_*` nào — để lại chỉ tạo ảo giác còn bảo vệ.

`develop` phải vào `main` trước: release flow tag trên `main`; merge chỉ build
`:main`/`:sha-`, **không** tạo tag phiên bản. Mỗi app cần tag riêng.

---

## 1. Thứ tự bắt buộc: VM trước, Railway sau

`develop` **gỡ sạch** guardrail lớp ứng dụng khỏi chat
(`63ff9d6f refactor(chat)!: remove the application-layer LLM guardrails` —
xoá 20 file `api/server/middleware/guardrails/`). Bảo vệ chuyển hết xuống gateway.

| Thứ tự | Hệ quả |
|---|---|
| **VM trước → Railway sau** ✅ | Luôn có ít nhất một lớp đang bảo vệ |
| Railway trước → VM sau ❌ | Chat mới không còn guardrail, gateway cũ vẫn là `llm-guard-api` → **tụt bảo vệ trong suốt khoảng giữa** |

Trong khoảng gateway-mới + chat-cũ, một request bị chặn sẽ hiện ra như lỗi
chung chung thay vì thông báo rõ ràng (bản sửa nằm ở `01a429f69`, thuộc chat mới).
Xấu về hiển thị, không mất an toàn — chấp nhận được vì ngắn.

---

## 2. `nufi-docs` đang nối vào repo đã archive — sửa trước, nếu không docs không bao giờ lên

Cả **9/9 deployment** của `nufi-docs` đều đến từ **`dudaji-vn/nufi-docs`**, không
phải monorepo. Bản SUCCESS cuối là **20/07/2026** ("replace LibreChat's feather
icon with the real NUFI logo"). Bản kế tiếp — tên đúng nghĩa đen là
*"docs: repo moved to dudaji-vn/nufi-app"* — kẹt ở **`NEEDS_APPROVAL`** và
chưa bao giờ chạy.

Đo trực tiếp:

```
curl -o /dev/null -w '%{http_code}' https://docs.app.nufi.me/docs/end-user/security
→ 404
```

**Hệ quả: merge `develop` → `main` bao nhiêu lần cũng không đưa trang security lên.**
Service phải được trỏ lại nguồn:

- Railway → service `nufi-docs` → **Settings → Source**
- Đổi repo sang **`dudaji-vn/nufi-app`**, branch `main`
- **Root Directory: `apps/docs`** (bắt buộc — nếu không Railpack build nhầm gốc monorepo)
- Watch Paths: `apps/docs/**` để commit ở app khác không rebuild docs
- Xoá/huỷ deployment `NEEDS_APPROVAL` đang kẹt

Đây cũng là lời giải cho việc logo LibreChat quay lại: bản sửa 20/07 nằm ở repo
**cũ**, bản copy vào monorepo là bản trước khi sửa. Production đang chạy bản đã
sửa; monorepo thì không — cho tới commit `d032a454b` hôm nay.

---

## 3. Hai defect phải sửa TRƯỚC khi chat mới gặp gateway mới

Đã xác nhận áp dụng: `BACKEND_BASE_URL = https://api.codechi.me/v1`.

### 3.1 `titleModel` trên Railway không được miễn trừ khỏi G1

| File | `titleModel` | Miễn trừ G1? |
|---|---|---|
| `deploy/platform/librechat.yaml:69` | `gemini-2.5-flash-title` | ✅ có trong `exempt_models` |
| `deploy/railway/librechat.yaml:54` | `current_model` | ❌ **không** |

G1 đang `mode: pre_call` (enforcing). `policy.yaml` ghi thẳng:

> Point librechat.yaml's titleModel at this alias; **anything else keeps full G1**.

LibreChat bắn thêm một request/tin nhắn để sinh tiêu đề, gói cả hội thoại vào
instruction — đo được **2898 và 3007 ký tự, score 0.987 và 0.988** so với ngưỡng
`user: 0.90`, trên hội thoại hoàn toàn vô hại.

**Lưu ý về mức độ chắc chắn:** span `user` yêu cầu `require_corroboration` — phải
hai detector độc lập cùng đồng ý. Nếu detector regex không bắt, request tiêu đề
sẽ **không** bị chặn. Nên đây là **rủi ro chưa loại trừ**, không phải hỏng chắc chắn.
Cách duy nhất để biết là đo trên staging, không phải suy luận.

Sửa: đổi `deploy/railway/librechat.yaml` sang `titleModel: "gemini-2.5-flash-title"`.

### 3.2 Alias đó **không có** trong version control

```bash
grep -n "model_name:" deploy/platform/litellm/config.yaml    # → rỗng
grep -n "store_model_in_db" deploy/platform/litellm/config.yaml  # → true
```

`config.yaml` **không định nghĩa model nào cả** — tất cả nằm trong Postgres.
Nghĩa là `gemini-2.5-flash-title` chỉ tồn tại trên stack đã từng tạo nó qua UI.

Kiểm tra trên gateway production trước khi trỏ `titleModel` vào nó:

```bash
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  https://<gateway>/v1/models | grep gemini-2.5-flash-title
```

Không có → tạo alias trong LiteLLM admin UI (`/ui`), rồi `docker compose restart librechat`
(LibreChat cache danh sách model lúc khởi động).

---

## 4. Phần VM — gateway (làm trước)

### 4.1 Thay đổi thực sự là gì

| | `main` | `develop` |
|---|---|---|
| Sidecar injection | `llm-guard-api` | **`nufi-scanner`** (mới) |
| Image litellm | build từ `./litellm` | build từ `./litellm`, **COPY thêm `nufi-security/`** (424 file) |
| Env | `LLM_GUARD_AUTH_TOKEN` | **bỏ**; thêm `SCANNER_MODEL_ID`, `SCANNER_MODEL_REVISION`, `HF_TOKEN` |

`nufi-scanner` **tải classifier ~700 MB ở lần chạy đầu** (`start_period: 300s`).
`litellm-proxy` `depends_on: nufi-scanner: service_healthy` — proxy sẽ **không lên**
cho tới khi scanner khoẻ. Lần đầu chờ tới 5 phút là bình thường, không phải treo.

### 4.2 VM đang chạy repo CŨ `npuops-platform` — đây là migration, không phải `git pull`

Xác nhận 2026-08-03. Không thể `git pull`: monorepo để platform ở
`deploy/platform/`, repo cũ để ở gốc.

**Điều cứu dữ liệu:** `docker-compose.yml` khai báo `name: npuops` ở **dòng 1**,
có từ commit LiteLLM đầu tiên (`e65c3c84a`). Compose lấy project name từ **file**,
không phải tên thư mục — nên volume vẫn là `npuops_postgres-data`… dù checkout
nằm ở đâu. Nếu không có dòng đó, chạy compose từ `deploy/platform/` sẽ tạo project
tên `platform` với volume mới toanh và **stack lên với database rỗng**.

#### B1 — Xác nhận tiền tố volume (một lệnh, quyết định mọi thứ)

```bash
docker volume ls | grep -E 'postgres-data|mongodb-data'
```
✅ Phải thấy `npuops_postgres-data`, `npuops_mongodb-data`.
❌ Thấy `npuops-platform_postgres-data` → **DỪNG**, checkout cũ có `name:` khác;
   di chuyển sẽ mất dữ liệu.

#### B2 — Kiểm kê sửa đổi local ở checkout cũ

Repo cũ có thể đã bị `add-model.sh` sửa `litellm/config.yaml` / `librechat.yaml`
ngay trên VM. Những sửa đổi đó **không nằm trong git** và sẽ mất khi chuyển.

```bash
cd <checkout-cũ>
git status --short
git diff --stat
```
Ghi lại mọi file `M`. Đặc biệt `litellm/config.yaml`, `librechat.yaml`.

#### B3 — Backup

```bash
docker compose exec -T postgres pg_dumpall -U postgres > ~/pg-$(date +%F).sql
docker compose exec -T mongodb mongodump --archive > ~/mongo-$(date +%F).archive
cp .env ~/env-$(date +%F).bak
ls -lh ~/pg-*.sql ~/mongo-*.archive
```
✅ Cả hai file > 0 byte.

#### B4 — Clone monorepo (KHÔNG xoá checkout cũ)

```bash
cd ~ && git clone https://github.com/dudaji-vn/nufi-app.git
cd nufi-app && git log --oneline -1     # phải là 44290a6ea
```

#### B5 — Mang state sang

```bash
OLD=<checkout-cũ>
NEW=~/nufi-app/deploy/platform
cp $OLD/.env $NEW/.env
[ -f $OLD/monitoring/secrets/slack-webhook ] && cp $OLD/monitoring/secrets/slack-webhook $NEW/monitoring/secrets/
# rồi áp lại thủ công các sửa đổi ghi ở B2
```

Thêm vào `$NEW/.env`:
```bash
cat >> $NEW/.env <<'EOF'

SCANNER_MODEL_ID=protectai/deberta-v3-base-prompt-injection-v2
SCANNER_MODEL_REVISION=90c9989b1a342275dd0d1a95aad283c04e075671
HF_TOKEN=
EOF
sed -i 's/^LLM_GUARD_AUTH_TOKEN=/#&/' $NEW/.env
grep -E 'SCANNER_MODEL|LLM_GUARD' $NEW/.env
```
✅ Thấy 2 dòng `SCANNER_MODEL_*`; `LLM_GUARD_AUTH_TOKEN` có `#` đằng trước.

#### B6 — Build và chuyển sang stack mới

```bash
cd $NEW
docker compose build litellm-proxy nufi-scanner     # tải classifier ~700 MB
docker compose up -d --remove-orphans
docker compose ps
```

Vì project name giống nhau, compose **tiếp quản đúng stack đang chạy** — chỉ tạo
lại container nào đổi config, volume giữ nguyên. `--remove-orphans` gỡ
`llm-guard-api`.

✅ `npuops-nufi-scanner` → `healthy` (**chờ tới 5 phút**, `start_period: 300s`),
`npuops-litellm` `Up`, `llm-guard-api` biến mất.

### 4.3 Xác minh

```bash
./scripts/staging-readiness.sh      # 35 check
curl -s localhost:4000/metrics/ | grep nufi_guardrail_enabled   # chú ý dấu / cuối
npm run check:wired
```

Dấu `/` cuối bắt buộc — LiteLLM mount metrics ở `/metrics`, gọi thiếu `/` trả `307`
rỗng nên grep khớp 0 dòng **trên một stack hoàn toàn khoẻ mạnh**.

Trạng thái đúng sau deploy: G1 `pre_call`, G2b/G3/G4 `post_call`, G2a `logging_only`.

---

## 5. Phần Railway (làm sau khi VM xanh)

Ba service, **mỗi app cần tag riêng** — merge `main` không tự sinh version.

| App | Có đổi? | Hiện tại | Việc cần làm |
|---|---|---|---|
| chat | 37 file | `nufichat:v0.1.10` | tag `nufi-v0.1.11` → đổi `BASE` |
| admin-panel | 2 file | `…-admin-panel:v0.0.4` | tag `nufi-admin-v0.0.5` → đổi image |
| docs | 20 file | **đóng băng 20/07** | trỏ lại nguồn (mục 2) |
| console | **0 file** | — | không đụng |

### 5.1 chat

```bash
export PATH="$HOME/.railway/bin:$PATH"
P=06c8dad0-f74c-412e-b9cf-f563676520d5

/nufi-release                       # tag main, verify GHCR image
railway variable set BASE=ghcr.io/dudaji-vn/nufichat:v0.1.11 \
  --project $P --environment production --service nufi-chat
```

`BASE` chứa **image ref đầy đủ**, không phải mỗi tag — hiện là
`ghcr.io/dudaji-vn/nufichat:v0.1.10`. Đặt nhầm mỗi `v0.1.11` sẽ hỏng build.

Chat chạy `deploy/railway/Dockerfile` — wrapper mỏng `FROM …nufichat:$BASE`.
**Code app nằm trong base image**, nên đổi `BASE` mới là cách cập nhật.

**Dọn hai biến rác** (chat mới không đọc `GUARDRAIL_*` nào):

```bash
railway variable delete GUARDRAIL_ENABLED --project $P --environment production --service nufi-chat
railway variable delete GUARDRAIL_PII_INPUT_MODE --project $P --environment production --service nufi-chat
```

### 5.2 admin-panel

2 file đổi. Tag `nufi-admin-v0.0.5`, rồi trỏ service sang image mới
(`Settings → Source → Image`). `API_SERVER_URL` và `VITE_API_BASE_URL` đã đúng —
không cần đổi.

### 5.3 docs

Xem **mục 2** — không phải chuyện tag, mà là service đang nối vào repo đã archive.

⚠️ Trang security mô tả cơ chế **chưa có trên production**; ảnh chụp từ stack
local. Trỏ lại nguồn docs **sau khi** gateway ở mục 4 đã xanh, nếu không tài liệu
sẽ mô tả thứ người dùng chưa được bảo vệ.

---

## 6. Rollback

| Phần | Cách lùi |
|---|---|
| Railway | Đặt `BASE` về tag cũ + redeploy. Nhanh, sạch. |
| VM | `git checkout <sha-cũ>` → `docker compose up -d --build`. Chậm hơn (build lại). |
| DB | Từ dump ở 4.2. **Chưa có migration nào trong lần này** — schema không đổi. |

Không có bước nào phá dữ liệu. Rủi ro thật nằm ở **khoảng giữa hai lần deploy**,
nên làm liền mạch, đừng để qua đêm.
