# NPUOps Platform

Self-hosted AI platform that routes LLM workloads across GPU and NPU backends.
Q2 2026 deliverable: complete GPU platform with NPU integration ready.

## Stack

| Component         | Role                                       |
| ----------------- | ------------------------------------------ |
| LiteLLM Proxy     | Gateway, routing, virtual keys             |
| Langfuse          | Observability, tracing, cost tracking      |
| LibreChat         | Chat interface for end users               |
| Console           | Self-service API key + usage UI (W3)       |
| Guardrails        | In-proxy LLM security controls + detector sidecars (Presidio, nufi-scanner) |
| Prometheus + Grafana | Monitoring dashboards (W5)              |
| PostgreSQL        | State store (LiteLLM keys, Langfuse data)  |
| MongoDB           | LibreChat app data                         |
| Redis             | Rate limiting + cache                      |

Everything runs in Docker Compose. See `docs/roadmap.md` for the weekly plan.

## Prerequisites

- Docker Engine 24+ and Docker Compose v2 (Docker Desktop on macOS / Windows)
- `git`
- A GitHub Personal Access Token with `read:packages` scope, then
  `docker login ghcr.io` once — the LibreChat image is pulled from
  `ghcr.io/dudaji-vn/librechat` (private until the org loosens GHCR access).
  See "LibreChat customization" below for the one-time login command.
- `yq` (Mike Farah's Go-based one — bootstrap and `add-model.sh` use it):
  - macOS — `brew install yq`
  - Linux — `sudo snap install yq` or download the binary from
    https://github.com/mikefarah/yq/releases
  - Windows (Git Bash / WSL2) — `winget install MikeFarah.yq` or the
    Linux binary above
  - **Not** Ubuntu's `apt install yq` — that's a different Python tool
- A reachable GPU inference server exposing an OpenAI-compatible API
  (e.g. vLLM, TGI, Ollama). Set `GPU_BACKEND_BASE_URL` in `.env`.
- ~10 GB free disk for Postgres / MongoDB / Langfuse / LibreChat volumes
- A POSIX shell to run the helper scripts:
  - macOS / Linux — built-in
  - Windows — Git Bash (ships with Git for Windows) or WSL2. Do **not** run
    `*.sh` scripts from cmd.exe or PowerShell.

## Quick start (recommended)

### 1. One-time install on your machine

Docker is required. Ollama is **optional** — only install it if you want to
run models locally on your laptop. If you'll point the stack at a remote
GPU/NPU box (vLLM, TGI, custom OpenAI-compatible server) or a cloud
provider (OpenAI, Anthropic, Together, …), skip Ollama entirely.

| OS      | Docker (required)                                      | Ollama (optional, local backend)                                        |
| ------- | ------------------------------------------------------ | ----------------------------------------------------------------------- |
| macOS   | Docker Desktop — https://www.docker.com (≥4 GB RAM)    | `brew install ollama && brew services start ollama`                    |
| Linux   | Docker Engine + Compose v2                             | `curl -fsSL https://ollama.com/install.sh \| sh` then `ollama serve &`  |
| Windows | Docker Desktop + WSL2 backend (≥4 GB RAM)              | `winget install Ollama.Ollama` (or installer from https://ollama.com)   |

Windows users also need **Git for Windows** (which provides Git Bash) or
**WSL2** to run the bootstrap and smoke-test scripts.

### 2. Clone and bootstrap

```bash
# macOS / Linux: open Terminal.
# Windows:       open Git Bash (right-click → "Git Bash Here") or a WSL2 shell.

git clone git@github.com:dudaji-vn/npuops-platform.git
# or: git clone https://github.com/dudaji-vn/npuops-platform.git
cd npuops-platform
./scripts/bootstrap.sh
#   → asks which backend to use:
#       • ollama     — local Ollama on this machine (auto-pulls + registers)
#       • remote     — vLLM / TGI / custom OpenAI-compatible server on the network
#       • cloud      — OpenAI / Anthropic / Together / Groq / etc. (needs an API key)
#       • mock-npu   — clone an existing model entry, tag as backend_type=npu
#       • skip       — bring the stack up only, register models later
#   → fills in random secrets in .env
#   → pulls the LibreChat image from ghcr.io (~150 MB)
#   → docker compose up -d
#   → runs the smoke test (skipped if no model was registered)
#   → prints URLs and the Langfuse admin password
```

Re-run `./scripts/bootstrap.sh` anytime — it's idempotent. Non-interactive flags:

```bash
./scripts/bootstrap.sh --backend ollama --model qwen2.5:3b   # CI / one-liner
./scripts/bootstrap.sh --backend remote                       # → add-model.sh prompts
./scripts/bootstrap.sh --backend skip                         # stack only, no model
```

### Manual quick start (if you want to do it yourself)

```bash
cp .env.example .env
# edit .env: replace every `replace-me` value (see comments in the file for
# how to generate each one — e.g. `openssl rand -hex 32`)

docker compose pull librechat    # ~150 MB from ghcr.io (one-time)
docker compose up -d
docker compose logs -f litellm-proxy   # wait for "Application startup complete"

# Register a model (pick one path):
./scripts/add-model.sh           # interactive — works for Ollama, vLLM, TGI,
                                 # OpenAI, Anthropic, Together, custom servers
# (or, if you'll use local Ollama: `ollama pull qwen2.5:3b` first, then run
#  add-model.sh and point it at http://host.docker.internal:11434/v1)

./scripts/smoke-test.sh
```

### Local dev backend (Ollama)

LiteLLM treats Ollama as just another OpenAI-compatible server. `.env.example`
ships with the host-Ollama defaults already set:

```env
GPU_BACKEND_BASE_URL=http://host.docker.internal:11434/v1
GPU_BACKEND_API_KEY=ollama
```

`./scripts/bootstrap.sh` pulls a model and registers it for you. To swap to
a real GPU server later: change the two lines above, then `add-model.sh`
again pointing at the same env vars.

## Adding a new model

Use `./scripts/add-model.sh` (interactive or via flags) to register any
OpenAI-compatible model — Ollama, vLLM, OpenAI, Together, Anthropic, your
teammate's custom server, etc. The script edits `litellm/config.yaml`
and `librechat.yaml`, restarts the proxy + chat UI, and runs a
test chat completion against the new model.

```bash
# Interactive — prompts you for each field
./scripts/add-model.sh

# Or non-interactive (CI / one-liner)
./scripts/add-model.sh \
  --name mixtral-8x7b \
  --model 'openai/mistralai/Mixtral-8x7B-Instruct-v0.1' \
  --base-url https://api.together.xyz/v1 \
  --api-key-env TOGETHER_API_KEY \
  --backend-type cloud \
  --hardware-id together-cloud
```

Requires `yq` (Mike Farah's — see [Prerequisites](#prerequisites) for cross-platform install). Run `./scripts/add-model.sh --help` for all flags.

### Adding a model from the LiteLLM admin UI

LiteLLM also lets you add models from its admin dashboard at
`http://localhost:4000/ui`. Those entries are persisted in Postgres
(`store_model_in_db: true` in `litellm/config.yaml`) and are served from
`/v1/models` immediately — no LiteLLM restart needed.

**But the new model won't appear in the LibreChat dropdown until you bounce
LibreChat.** LibreChat fetches `/v1/models` once at startup and caches the
list (`fetch: true` + `cache: true` in `librechat.yaml`):

```bash
docker compose restart librechat   # flushes the cached model list
```

Two caveats with this path:

- **Not in version control.** UI-added models live only in the DB, so they
  survive a LiteLLM restart but won't be reproducible on a fresh checkout
  and `./scripts/add-model.sh` won't know about them. Prefer the script for
  anything that needs to ship.
- **You still owe `backend_type` + `hardware_id`.** The admin UI lets you
  skip those, but W6 reports aggregate by `hardware_id` and W8 routing keys
  off `backend_type` — fill them in under "Model Info" or the entry is
  effectively invisible to reporting.

## End-to-end smoke test

`./scripts/e2e-smoke-test.sh` drives the full user flow
(LibreChat → LiteLLM → GPU backend → Langfuse trace) inside the compose
network. Useful as a regression check after touching any of those services.

```bash
./scripts/e2e-smoke-test.sh             # ~10s after the image is built
./scripts/e2e-smoke-test.sh --rebuild   # rebuild the e2e image first
```

The console-specific smoke test (login → JIT-provision → generate key →
use vs LiteLLM → 429 on rate-limit → revoke → 401 on revoked) now lives
in the standalone [nufi-console](https://github.com/dudaji-vn/nufi-console)
repo:

```bash
cd ../nufi-console && bun run smoke
```

Same `E2E_*` env vars; requires the stack to already be running.

Required env (auto-set by `./scripts/bootstrap.sh`, otherwise fill in `.env`
from the new `E2E_*` block in `.env.example`): `E2E_USER_EMAIL`,
`E2E_USER_PASSWORD`, `E2E_MODEL`, `E2E_EXPECTED_HARDWARE_ID`.

Production deployments that disable `ALLOW_REGISTRATION` must pre-create the
e2e user — the test only auto-registers when registration is open.

## Service endpoints (local defaults)

| Service        | URL                       |
| -------------- | ------------------------- |
| LiteLLM Proxy  | http://localhost:4000     |
| LibreChat      | http://localhost:3080     |
| Console        | http://localhost:3001     |
| Langfuse       | http://localhost:3000     |
| Grafana        | http://localhost:3030     |
| Prometheus     | http://localhost:9090     |
| Alertmanager   | http://localhost:9093     |

## Monitoring

Prometheus scrapes the LiteLLM `/metrics` endpoint plus Postgres and
Redis exporters every 15 seconds. Grafana auto-loads the LiteLLM
Overview dashboard from `monitoring/grafana/dashboards/`.

```bash
open http://localhost:3030/d/litellm-overview
# user/pass come from GRAFANA_ADMIN_USER / GRAFANA_ADMIN_PASSWORD in .env
```

**Alert rules** live in `monitoring/rules/litellm.rules.yml` —
LiteLLMDown (critical, 1m), LiteLLMHighErrorRate (>5% for 5m),
LiteLLMHighLatencyP95 (>10s for 5m). Iterate without restarting:

```bash
$EDITOR monitoring/rules/litellm.rules.yml
curl -X POST http://localhost:9090/-/reload
```

**Slack alerts** are scaffolded but disabled by default — alerts route
to a `noop` receiver until a webhook is in place. To enable:

```bash
cp monitoring/secrets/slack-webhook.example monitoring/secrets/slack-webhook
$EDITOR monitoring/secrets/slack-webhook   # paste the real URL, no quotes
$EDITOR monitoring/alertmanager.yml        # change route.receiver: noop → slack
docker compose restart alertmanager
```

The real `slack-webhook` file is gitignored.

## Guardrails

LLM security controls run inside the LiteLLM proxy. Design:
`docs/2026-07-27-llm-security-gateway-design.md`.

- **Policy** — `litellm/guardrails/policy.yaml`. Every threshold, failure
  behaviour and enforcement mode lives there, not in code.
- **Enforcement** — a control blocks only when its `policy.yaml` `mode` is
  something other than `logging_only` **and** it is registered in `config.yaml`.
  All controls ship in `logging_only`.
- **Status** — `curl localhost:4000/metrics/ | grep nufi_guardrail`. Note the
  trailing slash: LiteLLM mounts the metrics app at `/metrics`, and the
  un-slashed form answers `307` with an empty body, so a grep against it matches
  nothing on a perfectly healthy stack. `nufi_guardrail_enabled` is `0` for any
  control that is not enforcing.
- **Wiring** — `npm run check:wired` reconciles `policy.yaml` against
  `config.yaml`. A control declared in one and missing from the other cannot
  report its own absence, because the module never loads.
- **Benchmark** — `npm run bench:guardrails` (needs `BENCH_MODEL`;
  `LITELLM_MASTER_KEY` is read from `.env`).
- **Tests** — `.venv/bin/python -m pytest` for the pure layers. The 14
  `contract` tests are deselected by default and need Presidio and the scanner
  reachable on `localhost`; the compose sidecars publish no host ports, so they
  do not currently run against this stack.

> The guardrail metrics are only correct while the proxy runs a single worker
> and `PROMETHEUS_MULTIPROC_DIR` is unset. See the comment above `command:` in
> `docker-compose.yml` before changing either.

### Measured latency

25 iterations against a local `qwen2.5:0.5b`, shadow mode, all five controls
registered (`npm run bench:guardrails`, 2026-07-28):

| control | n | mean | p50 | p95 | p99 |
|---|---|---|---|---|---|
| G1 injection (pre) | 25 | 103.7 | 91.7 | 187.5 | 197.5 |
| G2a PII input (pre) | 25 | 4.1 | <5.0 | <5.0 | 8.8 |
| G2b PII output (post) | 25 | 67.0 | 69.1 | 137.5 | 187.5 |
| G4 output handling (post) | 25 | 0.0 | <5.0 | <5.0 | <5.0 |

All figures in milliseconds. `<5.0` means the value falls inside the lowest
histogram bucket and is not resolvable further — trust the mean beside it.
G3 recorded no samples: it needs a system message, and the benchmark prompt
sends none.

**Against the design's 100–200 ms budget this holds at the mean and fails at
the tail.** Mean total added latency is ~175 ms (G1 + G2a + G2b + G4). But G1
and G2b alone reach 325 ms at p95 and 385 ms at p99, and those two run on
opposite sides of the model call, so they add rather than overlap. The budget
needs either re-stating as a mean, or work on the tail, before anyone promises
it externally.

### Known false-positive risks — measure before enforcing

Two are already measured. Both would degrade ordinary traffic the moment the
control enforces, which is exactly how the previous generation of these
guardrails ended up switched off.

**1. G2b redacts ordinary place names, on essentially every response.** The
default `PII_ENTITIES` list (`litellm/guardrails/entrypoints.py`) includes
`LOCATION` and `PERSON`, and both thresholds are `0.50`. Presidio scores the
word *Hanoi* as `LOCATION` at **0.85** and *Thai* (in "Ly Thai To") as `NRP` at
0.85 — both far above the threshold. In the benchmark run above, the benign
prompt *"summarise the history of Hanoi"* produced a G2b `redact` decision on
**25 of 25 requests**, and the running stack has recorded 228 of them.

If G2b were enforced today, any answer naming a city or a person would come
back with `[redacted:LOCATION]` in it. This is not a tail risk; it is the modal
case. The decision to make before enforcing G2b is whether `LOCATION` and
`PERSON` belong in the entity list at all — a city name in a history answer is
not sensitive information disclosure, while a customer's name in a support
transcript is. That is a policy question, not a tuning question.

G2a is unaffected in practice: its action is `log`, never `mask`. Input masking
was already tried and reverted (W5.1, May 2026) because the model began
answering the placeholder instead of the question.

**2. G1 reacts to repetition, independently of any payload.** A long
repetitive-but-benign span measured **0.9988** against G1's user threshold of
0.90. Pasted logs, CSV extracts, wide tables and boilerplate-heavy code could
be blocked outright the moment G1 enforces. Count `logging_only` blocks whose
spans are repetitive-but-benign before enforcing, and raise the threshold or
add a repetition-aware exemption if the rate is material. The attack corpus
passing is not evidence that enforcement is safe; it only measures the other
direction.

### Turning a control on

1. Run in `logging_only` for several days and read
   `nufi_guardrail_decisions_total` — an action with `enforced="false"` is what
   *would* have happened.
2. Tune thresholds, and for G2 the entity list, in `policy.yaml` until the
   false-positive rate is acceptable.
3. Change that control's `mode` and restart the proxy.

Two tests currently fail on the first enforcement flip
(`test_health.py::test_status_reports_every_control_with_its_mode` and
`test_policy.py::test_logging_only_mode_downgrades_a_block_to_log`); they pin
the shipping `policy.yaml` rather than the semantics. Fix them as part of the
rollout rather than treating red tests as a reason not to proceed.

### Swapping the injection classifier

`SCANNER_MODEL_ID` selects the model, and `SCANNER_MODEL_REVISION` pins it to a
commit so it cannot change underneath a security control. The default is
ungated and Apache-2.0. Using `meta-llama/Llama-Prompt-Guard-2-22M` requires
accepting the Llama 4 Community License and setting `HF_TOKEN`; change the
revision to that model's commit sha at the same time.

## Project conventions

- All services run in Docker Compose. Do not run Python / Node directly on host.
- Pin every Docker image version. Never use `:latest`.
- Secrets only via `.env`. Never hardcode.
- LiteLLM `config.yaml` must include `model_info.backend_type: gpu | npu` from
  W1 onward, so W8 NPU integration does not require a refactor.
- Every request must log `hardware_id` so W6 reports can aggregate by hardware.

## Layout

```
npuops-platform/
├── docker-compose.yml
├── litellm/          # config.yaml + Dockerfile
├── langfuse/         # Langfuse setup
├── librechat/        # runtime config only — see "LibreChat customization"
│   └── librechat.yaml  # mounted into the container; image lives in the fork
├── monitoring/       # Prometheus, Grafana, alert rules
├── scripts/          # helper scripts (smoke test, backups)
└── docs/             # internal documentation (roadmap.md)
```

## Console (self-service UI)

The console at `http://localhost:3001` is where users self-issue LiteLLM API
keys and view their own usage. The source lives in a separate repo —
[dudaji-vn/nufi-console](https://github.com/dudaji-vn/nufi-console) — and is
deployed here as a pre-built image (`ghcr.io/dudaji-vn/nufi-console`). See
`docs/separate-developer-console.md` for the rationale.

**SSO**: the console verifies the LibreChat-issued JWT (shared `JWT_SECRET`)
out of the cookie jar — sign in once at LibreChat, then open the console in
the same browser. No second login.

**Pages**:

- `/` — profile + this-period spend (combined chat + issued-key usage)
- `/keys` — list / generate / revoke API keys with budgets and rpm/tpm limits

**Pin a specific image tag** (default is `main`):

```bash
# in .env
NUFI_CONSOLE_TAG=v0.2.0
```

**Develop locally**: clone the [nufi-console](https://github.com/dudaji-vn/nufi-console)
repo as a sibling directory and run `bun run dev` there. Set the same
`JWT_SECRET` / `JWT_REFRESH_SECRET` / `LITELLM_MASTER_KEY` as the running
stack so auth and admin calls work in dev.

## LibreChat customization

LibreChat is forked at https://github.com/dudaji-vn/LibreChat
(branch `npuops/main`, pinned to upstream `v0.7.5`). The fork's CI builds and
publishes a multi-arch image to `ghcr.io/dudaji-vn/librechat:npuops-v0.7.5-N`,
which this repo pulls via the `image:` line in `docker-compose.yml`. There
is no local LibreChat source in this repo — only `librechat.yaml`
runtime config, mounted into the container.

**One-time auth (every contributor + every deploy host):**

```bash
# 1. Create a Personal Access Token at https://github.com/settings/tokens/new
#    Scope: read:packages only. Note: e.g. "npuops-ghcr-read".
# 2. Login (replace ghp_... with your token, <username> with your GH login):
echo ghp_xxxxxxxxxxxxxxxxxxxx | docker login ghcr.io -u <username> --password-stdin
```

Credentials persist in your Docker config — you don't need to do this again
unless you rotate the token.

**Customize LibreChat (add a feature, tweak the UI):**

Work in the fork repo, not here:

```bash
git clone git@github.com:dudaji-vn/LibreChat.git
cd LibreChat
git checkout npuops/main

# Edit normally — IDE, hot reload, all of it works.
$EDITOR client/src/components/Nav/AccountSettings.tsx
git commit -am "feat(nav): add Foo link"
git push

# Tag the next NPUOps release (CI builds + publishes the image).
git tag npuops-v0.7.5-4    # bump the trailing number per release
git push origin npuops-v0.7.5-4
```

Then, in this repo, bump the tag in `docker-compose.yml`:

```yaml
librechat:
  image: ghcr.io/dudaji-vn/librechat:npuops-v0.7.5-4
```

`docker compose pull librechat && docker compose up -d librechat`.

**Upgrade upstream LibreChat:**

In the fork:

```bash
cd LibreChat
git remote add upstream https://github.com/danny-avila/LibreChat.git  # one-time
git fetch upstream --tags
git checkout npuops/main
git merge v0.7.6        # resolve any conflicts in npuops customization commits
git push
git tag npuops-v0.7.6-1
git push origin npuops-v0.7.6-1
```

Then bump the image tag here. The fork keeps a clear `git log upstream/v0.7.5..npuops/main`
diff for "what did NPUOps actually change?" — useful for security audits and
upstream conflict triage.

## Documentation

- `docs/roadmap.md` — weekly plan (W1–W9), acceptance criteria, risks
- `CLAUDE.md` — guidance for AI-assisted contributions

## Useful references

- LiteLLM: https://docs.litellm.ai
- Langfuse: https://langfuse.com/docs
- LibreChat: https://docs.librechat.ai

