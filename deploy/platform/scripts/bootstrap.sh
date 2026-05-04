#!/usr/bin/env bash
# =============================================================================
# scripts/bootstrap.sh — one-command local-dev setup for the NPUOps platform.
# =============================================================================
#
# USAGE
#   ./scripts/bootstrap.sh                    # interactive (prompts for model)
#   ./scripts/bootstrap.sh --model qwen2.5:3b
#   ./scripts/bootstrap.sh --skip-pull        # don't `ollama pull`
#   ./scripts/bootstrap.sh --skip-smoke-test  # don't run smoke test at the end
#   ./scripts/bootstrap.sh --help
#
# PREREQUISITES (install these first, one-time per machine)
#   • Docker Desktop  ≥ 4.0  — https://www.docker.com   (give it ≥4 GB RAM)
#   • Ollama                 — https://ollama.com
#       macOS:  brew install ollama && brew services start ollama
#       Linux:  curl -fsSL https://ollama.com/install.sh | sh
#                ollama serve &     # if not already a service
#
# WHAT THIS SCRIPT DOES (idempotent — safe to re-run any time)
#   1. Verifies Docker + Ollama are installed and running
#   2. Asks which Ollama model to use as the local "GPU" backend
#   3. Pulls that model via `ollama pull`
#   4. Creates `.env` from `.env.example` if missing, fills in random secrets,
#      and points GPU_MODEL at your chosen model
#   5. Runs `docker compose up -d` and waits for the stack to be healthy
#   6. Runs the smoke test
#
# AFTER IT FINISHES
#   LiteLLM proxy   http://localhost:4000   (master key in .env: LITELLM_MASTER_KEY)
#   Langfuse UI     http://localhost:3000   (login printed at the end)
#
# TROUBLESHOOTING (most common issues)
#   • "Docker daemon not running"     — start Docker Desktop
#   • "ollama daemon not reachable"   — `brew services start ollama` (mac)
#   • clickhouse stuck unhealthy      — see docs/roadmap.md Task 1.2 gotchas
#   • smoke test step 6 fails         — `docker compose restart litellm-proxy`
# =============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

# -----------------------------------------------------------------------------
# pretty output helpers
# -----------------------------------------------------------------------------
if [ -t 1 ]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
  RED=$'\033[31m'; CYAN=$'\033[36m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; RED=""; CYAN=""; RESET=""
fi
step() { echo "${CYAN}==>${RESET} ${BOLD}$*${RESET}"; }
ok()   { echo "    ${GREEN}✓${RESET} $*"; }
warn() { echo "    ${YELLOW}!${RESET} $*"; }
die()  { echo "${RED}error:${RESET} $*" >&2; exit 1; }

# -----------------------------------------------------------------------------
# argument parsing
# -----------------------------------------------------------------------------
MODEL=""
SKIP_PULL=0
SKIP_SMOKE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --model)             MODEL="$2"; shift 2 ;;
    --model=*)           MODEL="${1#*=}"; shift ;;
    --skip-pull)         SKIP_PULL=1; shift ;;
    --skip-smoke-test)   SKIP_SMOKE=1; shift ;;
    -h|--help)           sed -n '2,40p' "$0"; exit 0 ;;
    *)                   die "unknown argument: $1 (try --help)" ;;
  esac
done

# -----------------------------------------------------------------------------
# 1. prerequisites
# -----------------------------------------------------------------------------
step "1/6 Checking prerequisites"
command -v docker  >/dev/null || die "docker not installed — https://www.docker.com"
docker compose version >/dev/null 2>&1 || die "docker compose plugin missing"
command -v openssl >/dev/null || die "openssl not installed"
command -v curl    >/dev/null || die "curl not installed"
docker info >/dev/null 2>&1   || die "Docker daemon not running — start Docker Desktop"
ok "docker, openssl, curl ok"

# -----------------------------------------------------------------------------
# 2. Ollama (local model server, runs on the host — see CLAUDE.md / README.md)
# -----------------------------------------------------------------------------
step "2/6 Checking Ollama"
if ! command -v ollama >/dev/null; then
  cat <<EOF

  Ollama is needed to serve a model locally for development.
  Install with:
    macOS:  brew install ollama && brew services start ollama
    Linux:  curl -fsSL https://ollama.com/install.sh | sh
            ollama serve &
  Or download from https://ollama.com

EOF
  die "Install Ollama and re-run."
fi

if ! curl -sSf http://localhost:11434/api/tags >/dev/null 2>&1; then
  cat <<EOF

  Ollama is installed but the daemon isn't reachable on :11434.
  Start it:
    macOS:  brew services start ollama
    Linux:  ollama serve &

EOF
  die "Start Ollama and re-run."
fi
ok "ollama daemon reachable on http://localhost:11434"

# -----------------------------------------------------------------------------
# 3. model selection + pull
# -----------------------------------------------------------------------------
step "3/6 Choosing local model"
if [ -z "$MODEL" ]; then
  cat <<EOF
    Which Ollama model do you want to use as the GPU backend?

    Suggestions (pick by RAM / speed):
      qwen2.5:3b   — small, fast, ~2 GB  (default)
      llama3.2:3b  — small, fast, ~2 GB
      phi3:mini    — small, fast, ~2 GB
      qwen2.5:7b   — medium, ~4.5 GB, smarter
      mistral:7b   — medium, ~4 GB

    Browse more: https://ollama.com/library
EOF
  printf "    model name [qwen2.5:3b]: "
  read -r MODEL
  MODEL="${MODEL:-qwen2.5:3b}"
fi
ok "model: ${MODEL}"

if [ "$SKIP_PULL" -eq 0 ]; then
  if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$MODEL"; then
    ok "already pulled (skipping)"
  else
    echo "    pulling ${MODEL} via ollama (this can take a few minutes)"
    ollama pull "$MODEL"
    ok "pulled"
  fi
fi

# -----------------------------------------------------------------------------
# 4. .env (create + fill secrets + sync derived values)
# -----------------------------------------------------------------------------
step "4/6 Configuring .env"

# Each line: KEY,GENERATOR
# Generators: sk_hex32, hex32, hex16, hex12, b64_32
# A secret is only generated if the value in .env is currently `replace-me`.
SECRETS_DEF='
LITELLM_MASTER_KEY,sk_hex32
LITELLM_SALT_KEY,hex32
POSTGRES_PASSWORD,hex16
JWT_SECRET,hex32
JWT_REFRESH_SECRET,hex32
CREDS_KEY,hex32
CREDS_IV,hex16
MONGO_INITDB_ROOT_PASSWORD,hex16
LANGFUSE_NEXTAUTH_SECRET,b64_32
LANGFUSE_SALT,b64_32
LANGFUSE_ENCRYPTION_KEY,hex32
LANGFUSE_INIT_USER_PASSWORD,hex12
CLICKHOUSE_PASSWORD,hex16
MINIO_ROOT_PASSWORD,hex16
GRAFANA_ADMIN_PASSWORD,hex12
'

gen() {
  case "$1" in
    sk_hex32) printf "sk-%s" "$(openssl rand -hex 32)" ;;
    hex32)    openssl rand -hex 32 ;;
    hex16)    openssl rand -hex 16 ;;
    hex12)    openssl rand -hex 12 ;;
    b64_32)   openssl rand -base64 32 ;;
    *)        die "unknown generator: $1" ;;
  esac
}

if [ ! -f .env ]; then
  cp .env.example .env
  ok ".env created from .env.example"
else
  ok ".env already exists — only filling missing secrets"
fi

TMPFILE=$(mktemp)
cp .env "$TMPFILE"

# Replace any KEY=replace-me with a freshly generated value of the right kind.
echo "$SECRETS_DEF" | while IFS=, read -r KEY GENERATOR; do
  [ -z "$KEY" ] && continue
  if grep -qE "^${KEY}=replace-me$" "$TMPFILE"; then
    NEWVAL=$(gen "$GENERATOR")
    awk -v k="$KEY" -v v="$NEWVAL" \
        '$0 ~ "^" k "=replace-me$" { print k"="v; next } { print }' \
        "$TMPFILE" > "${TMPFILE}.new" && mv "${TMPFILE}.new" "$TMPFILE"
  fi
done

# Sync derived values that depend on the generated secrets.
PG_PASS=$(grep -E "^POSTGRES_PASSWORD=" "$TMPFILE" | cut -d= -f2-)
MONGO_PASS=$(grep -E "^MONGO_INITDB_ROOT_PASSWORD=" "$TMPFILE" | cut -d= -f2-)

awk \
  -v pg="$PG_PASS" \
  -v mg="$MONGO_PASS" \
  -v gpu="openai/${MODEL}" '
  /^DATABASE_URL=/ { print "DATABASE_URL=postgresql://npuops:" pg "@postgres:5432/npuops"; next }
  /^MONGO_URI=/    { print "MONGO_URI=mongodb://librechat:" mg "@mongodb:27017/LibreChat?authSource=admin"; next }
  /^GPU_MODEL=/    { print "GPU_MODEL=" gpu; next }
  { print }
' "$TMPFILE" > "${TMPFILE}.new" && mv "${TMPFILE}.new" "$TMPFILE"

mv "$TMPFILE" .env
ok "secrets populated, GPU_MODEL=openai/${MODEL}"

# -----------------------------------------------------------------------------
# 5. docker compose up + wait for healthy
# -----------------------------------------------------------------------------
step "5/6 Starting Docker stack"
docker compose up -d
ok "compose up -d issued"

echo "    waiting for litellm-proxy to be healthy (first boot can take ~2 min)..."
for i in $(seq 1 60); do
  state=$(docker inspect --format '{{.State.Health.Status}}' npuops-litellm 2>/dev/null || echo missing)
  if [ "$state" = "healthy" ]; then
    echo
    ok "stack healthy"
    break
  fi
  printf "."
  sleep 5
  if [ "$i" -eq 60 ]; then
    echo
    die "litellm-proxy did not become healthy in 5 minutes — try: docker compose logs litellm-proxy"
  fi
done

# -----------------------------------------------------------------------------
# 6. smoke test
# -----------------------------------------------------------------------------
if [ "$SKIP_SMOKE" -eq 0 ]; then
  step "6/6 Running smoke test"
  ./scripts/smoke-test.sh
else
  step "6/6 Smoke test skipped (--skip-smoke-test)"
fi

# -----------------------------------------------------------------------------
# summary
# -----------------------------------------------------------------------------
ADMIN_PW=$(grep -E "^LANGFUSE_INIT_USER_PASSWORD=" .env | cut -d= -f2-)
echo
step "Setup complete"
cat <<EOF

  ${BOLD}URLs:${RESET}
    LiteLLM proxy    http://localhost:4000
    Langfuse UI      http://localhost:3000
    LibreChat        http://localhost:3080   (W2 — not yet deployed)
    Grafana          http://localhost:3002   (W5 — not yet deployed)

  ${BOLD}Langfuse login:${RESET}
    email:    admin@npuops.local
    password: ${ADMIN_PW}
    (also in .env as LANGFUSE_INIT_USER_PASSWORD)

  ${BOLD}Common commands:${RESET}
    docker compose ps                      # see status of all services
    docker compose logs -f litellm-proxy   # tail logs of any service
    docker compose down                    # stop the stack (data persists)
    docker compose down -v                 # stop and WIPE all data volumes
    ./scripts/smoke-test.sh                # re-run verification

EOF
