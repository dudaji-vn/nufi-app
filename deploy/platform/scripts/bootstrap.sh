#!/usr/bin/env bash
# =============================================================================
# scripts/bootstrap.sh — one-command local-dev setup for the NPUOps platform.
# =============================================================================
#
# USAGE
#   ./scripts/bootstrap.sh                       # interactive — picks backend + model
#   ./scripts/bootstrap.sh --backend ollama --model qwen2.5:3b
#   ./scripts/bootstrap.sh --backend remote      # hands off to add-model.sh (vLLM/TGI/custom)
#   ./scripts/bootstrap.sh --backend cloud       # hands off to add-model.sh (OpenAI/etc.)
#   ./scripts/bootstrap.sh --backend mock-npu    # clone a registered model as backend_type=npu
#   ./scripts/bootstrap.sh --backend skip        # bring up stack only
#   ./scripts/bootstrap.sh --domain codechi.me   # rewrite public URLs after secrets are set
#   ./scripts/bootstrap.sh --skip-pull           # don't `ollama pull`
#   ./scripts/bootstrap.sh --skip-smoke-test     # don't run smoke test at the end
#   ./scripts/bootstrap.sh --help
#
# PREREQUISITES (install these first, one-time per machine)
#   • Docker Desktop  ≥ 4.0  — https://www.docker.com   (give it ≥4 GB RAM)
#   • git
#   • A `docker login ghcr.io` session with a PAT scoped read:packages —
#     LibreChat ships from ghcr.io/dudaji-vn/librechat (private). See
#     README.md → "LibreChat customization" for the one-time login.
#   • yq (Mike Farah's, NOT Ubuntu's apt python-yq) —
#       macOS:    brew install yq
#       Linux:    sudo snap install yq  (or binary from github.com/mikefarah/yq/releases)
#       Windows:  winget install MikeFarah.yq  (or the Linux binary above)
#   • Ollama (only if you'll use --backend ollama) — https://ollama.com
#       macOS:    brew install ollama && brew services start ollama
#       Linux:    curl -fsSL https://ollama.com/install.sh | sh && ollama serve &
#       Windows:  winget install Ollama.Ollama   (or installer from ollama.com)
#
#   On Windows, run this script from Git Bash or WSL2 — not from cmd.exe
#   or PowerShell. (Git Bash ships with bash, openssl, curl, awk, sed.)
#   Recommended on Windows: `git config --global core.autocrlf input` so
#   shell scripts stay LF — the .gitattributes at the repo root pins
#   .sh / Dockerfile to LF regardless.
#
# WHAT THIS SCRIPT DOES (idempotent — safe to re-run any time)
#   1. Verifies Docker, openssl, curl, yq
#   2. Asks which backend you want — five options:
#        • ollama     — local Ollama on this machine (pulls + auto-registers)
#        • remote     — vLLM / TGI / custom OpenAI-compatible server on the network
#        • cloud      — OpenAI / Anthropic / Together / Groq / etc.
#        • mock-npu   — clone an existing model entry, tag as backend_type=npu
#                       (useful for canary UI dev before the real NPU lands)
#        • skip       — bring up the stack only, register models later
#   3. (ollama) multi-pick from already-pulled models (or pull a new one);
#      (remote/cloud) deferred to add-model.sh after the stack is up;
#      (mock-npu) deferred — picks a source after the stack is up
#   4. Creates `.env` from `.env.example` if missing and fills in random secrets
#   5. Runs `docker compose up -d` and waits for the stack to be healthy
#   5b. Registers the chosen model via `./scripts/add-model.sh` (cloud is
#       interactive; ollama is non-interactive)
#   6. Runs the smoke test (skipped if no model was registered)
#
# AFTER IT FINISHES
#   LiteLLM proxy   http://localhost:4000   (master key in .env: LITELLM_MASTER_KEY)
#   LibreChat       http://localhost:3080
#   Langfuse UI     http://localhost:3000   (login printed at the end)
#
# TROUBLESHOOTING (most common issues)
#   • "Docker daemon not running"     — start Docker Desktop
#   • "ollama daemon not reachable"   — start Ollama:
#                                         macOS:    brew services start ollama
#                                         Linux:    ollama serve &
#                                         Windows:  launch Ollama from Start menu
#   • clickhouse stuck unhealthy      — see docs/roadmap.md Task 1.2 gotchas
#   • smoke test step 6 fails         — `docker compose restart litellm-proxy`
# =============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

# -----------------------------------------------------------------------------
# pretty output helpers
# -----------------------------------------------------------------------------
if [ -t 1 ]; then
  BOLD=$'\033[1m'
  DIM=$'\033[2m'
  GREEN=$'\033[32m'
  YELLOW=$'\033[33m'
  RED=$'\033[31m'
  CYAN=$'\033[36m'
  RESET=$'\033[0m'
else
  BOLD=""
  DIM=""
  GREEN=""
  YELLOW=""
  RED=""
  CYAN=""
  RESET=""
fi
step() { echo "${CYAN}==>${RESET} ${BOLD}$*${RESET}"; }
ok() { echo "    ${GREEN}✓${RESET} $*"; }
warn() { echo "    ${YELLOW}!${RESET} $*"; }
bad() { echo "    ${RED}✗${RESET} $*" >&2; }
die() {
  echo "${RED}error:${RESET} $*" >&2
  exit 1
}

# Recreate litellm + librechat and wait for litellm to be healthy.
# Used after batched config changes (multi-model registration, mock-NPU clone)
# where add-model.sh's per-call restart was suppressed with --no-restart.
restart_stack() {
  step "Restarting litellm-proxy + librechat"
  docker compose up -d --force-recreate litellm-proxy librechat >/dev/null
  echo "    waiting for litellm-proxy to be healthy..."
  for i in $(seq 1 24); do
    s=$(docker inspect --format '{{.State.Health.Status}}' npuops-litellm 2>/dev/null || echo missing)
    if [ "$s" = "healthy" ]; then
      echo
      ok "healthy"
      return 0
    fi
    printf "."
    sleep 5
  done
  echo
  warn "litellm-proxy did not become healthy in 2 minutes — check: docker compose logs litellm-proxy"
}

# Arrow-key pickers. Bash 3.2 compatible (macOS default shell).
#
#   pick "Title" "opt1" "opt2" ...
#     ↑/↓ (or k/j) navigate · enter confirm · q quit
#     Sets PICK_INDEX (1-based) and PICK_VALUE.
#
#   pick_multi "Title" "opt1" "opt2" ...
#     ↑/↓ navigate · space toggle · enter confirm · q quit
#     Sets PICK_INDICES_ARR (1-based ints) and PICK_VALUES_ARR.
#
# If stdin or stderr isn't a TTY, both pickers fall back to the first option
# so non-interactive runs (CI, --backend foo) keep working.

_pick_saved_tty=""
_pick_restore_tty() {
  [ -n "$_pick_saved_tty" ] && stty "$_pick_saved_tty" 2>/dev/null
  printf "\033[?25h" >&2 # show cursor
  _pick_saved_tty=""
}
_pick_setup_tty() {
  _pick_saved_tty=$(stty -g)
  stty -echo -icanon
  printf "\033[?25l" >&2 # hide cursor
  trap '_pick_restore_tty' EXIT INT TERM
}

# Read one keystroke into KEY. Maps arrow / vim / space / enter / q / esc.
# `read -t 1` (integer seconds — bash 3.2 safe) gives us a 1s window to detect
# the rest of an arrow's escape sequence after we see ESC; bare ESC also exits.
_pick_read_key() {
  local k rest
  IFS= read -rsn1 k
  case "$k" in
    $'\033')
      rest=""
      IFS= read -rsn2 -t 1 rest 2>/dev/null || true
      case "$rest" in
        '[A') KEY=up ;;
        '[B') KEY=down ;;
        *) KEY=esc ;;
      esac
      ;;
    "") KEY=enter ;;
    " ") KEY=space ;;
    k | K) KEY=up ;;
    j | J) KEY=down ;;
    q | Q) KEY=q ;;
    *) KEY=other ;;
  esac
}

# Move cursor up N lines, clearing each line as we go. Used to redraw the menu
# in place after every keystroke.
_pick_clear_lines() {
  local n=$1 i
  for i in $(seq 1 "$n"); do
    printf "\033[A\033[2K" >&2
  done
}

pick() {
  local title="$1"
  shift
  local opts=("$@")
  local n=${#opts[@]} cur=0 i

  # Non-TTY fallback — autoselect first option. Lets `--backend skip` etc.
  # work when stdin is closed.
  if [ ! -t 0 ] || [ ! -t 2 ]; then
    PICK_INDEX=1
    PICK_VALUE="${opts[0]}"
    return 0
  fi

  printf "    %s\n" "$title" >&2
  printf "    %s↑/↓ navigate · enter to select · q to quit%s\n\n" "$DIM" "$RESET" >&2

  _pick_setup_tty
  _pick_draw_single() {
    for i in $(seq 0 $((n - 1))); do
      if [ "$i" -eq "$cur" ]; then
        printf "    ${CYAN}▸${RESET} ${BOLD}%s${RESET}\n" "${opts[$i]}" >&2
      else
        printf "      %s\n" "${opts[$i]}" >&2
      fi
    done
  }
  _pick_draw_single
  while :; do
    _pick_read_key
    case "$KEY" in
      up) cur=$(((cur - 1 + n) % n)) ;;
      down) cur=$(((cur + 1) % n)) ;;
      enter) break ;;
      q | esc)
        _pick_restore_tty
        die "aborted"
        ;;
    esac
    _pick_clear_lines "$n"
    _pick_draw_single
  done
  _pick_restore_tty

  PICK_INDEX=$((cur + 1))
  PICK_VALUE="${opts[$cur]}"
}

pick_multi() {
  local title="$1"
  shift
  local opts=("$@")
  local n=${#opts[@]} cur=0 i any sel
  declare -a selected
  for i in $(seq 0 $((n - 1))); do selected[i]=0; done

  if [ ! -t 0 ] || [ ! -t 2 ]; then
    PICK_INDICES_ARR=(1)
    PICK_VALUES_ARR=("${opts[0]}")
    return 0
  fi

  printf "    %s\n" "$title" >&2
  printf "    %s↑/↓ navigate · space toggle · enter to confirm · q to quit%s\n\n" "$DIM" "$RESET" >&2

  _pick_setup_tty
  _pick_draw_multi() {
    for i in $(seq 0 $((n - 1))); do
      if [ "${selected[$i]}" -eq 1 ]; then
        sel="[${GREEN}✓${RESET}]"
      else
        sel="[ ]"
      fi
      if [ "$i" -eq "$cur" ]; then
        printf "    ${CYAN}▸${RESET} %s ${BOLD}%s${RESET}\n" "$sel" "${opts[$i]}" >&2
      else
        printf "      %s %s\n" "$sel" "${opts[$i]}" >&2
      fi
    done
  }
  _pick_draw_multi
  while :; do
    _pick_read_key
    case "$KEY" in
      up) cur=$(((cur - 1 + n) % n)) ;;
      down) cur=$(((cur + 1) % n)) ;;
      space) selected[cur]=$((1 - selected[cur])) ;;
      enter)
        any=0
        for i in $(seq 0 $((n - 1))); do
          [ "${selected[$i]}" -eq 1 ] && any=1
        done
        [ "$any" -eq 1 ] && break
        ;;
      q | esc)
        _pick_restore_tty
        die "aborted"
        ;;
    esac
    _pick_clear_lines "$n"
    _pick_draw_multi
  done
  _pick_restore_tty

  PICK_INDICES_ARR=()
  PICK_VALUES_ARR=()
  for i in $(seq 0 $((n - 1))); do
    if [ "${selected[$i]}" -eq 1 ]; then
      PICK_INDICES_ARR+=($((i + 1)))
      PICK_VALUES_ARR+=("${opts[$i]}")
    fi
  done
}

# -----------------------------------------------------------------------------
# argument parsing
# -----------------------------------------------------------------------------
BACKEND=""
MODEL=""
DOMAIN=""
SKIP_PULL=0
SKIP_SMOKE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --backend)
      BACKEND="$2"
      shift 2
      ;;
    --backend=*)
      BACKEND="${1#*=}"
      shift
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    --model=*)
      MODEL="${1#*=}"
      shift
      ;;
    --domain)
      DOMAIN="$2"
      shift 2
      ;;
    --domain=*)
      DOMAIN="${1#*=}"
      shift
      ;;
    --skip-pull)
      SKIP_PULL=1
      shift
      ;;
    --skip-smoke-test)
      SKIP_SMOKE=1
      shift
      ;;
    -h | --help)
      sed -n '2,59p' "$0"
      exit 0
      ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

# --model implies Ollama (preserves the old single-flag UX).
[ -n "$MODEL" ] && [ -z "$BACKEND" ] && BACKEND=ollama
case "$BACKEND" in
  "" | ollama | remote | cloud | mock-npu | skip) ;;
  *) die "--backend must be one of: ollama, remote, cloud, mock-npu, skip (got: $BACKEND)" ;;
esac

# -----------------------------------------------------------------------------
# 1. prerequisites
# -----------------------------------------------------------------------------
step "1/6 Checking prerequisites"
command -v docker >/dev/null || die "docker not installed — https://www.docker.com"
docker compose version >/dev/null 2>&1 || die "docker compose plugin missing"
command -v openssl >/dev/null || die "openssl not installed"
command -v curl >/dev/null || die "curl not installed"
command -v git >/dev/null || die "git not installed"
if ! command -v yq >/dev/null; then
  cat >&2 <<'EOF'

  yq (Mike Farah's, used by add-model.sh) is missing. Install with:
    macOS:    brew install yq
    Linux:    sudo snap install yq   (or binary from github.com/mikefarah/yq/releases)
    Windows:  winget install MikeFarah.yq
  Note: Ubuntu's "apt install yq" is a different Python tool — don't use it.

EOF
  die "yq not installed."
fi
docker info >/dev/null 2>&1 || die "Docker daemon not running — start Docker Desktop"
ok "docker, openssl, curl, git, yq ok"

# -----------------------------------------------------------------------------
# 2. backend choice — local Ollama vs cloud provider vs skip
# -----------------------------------------------------------------------------
step "2/6 Backend selection"
if [ -z "$BACKEND" ]; then
  pick "Where will the LLMs run?" \
    "Local Ollama       — runs models on this machine (good for dev, no API key)" \
    "Remote OpenAI-API  — vLLM / TGI / a real GPU or NPU box on the network" \
    "Cloud provider     — OpenAI / Anthropic / Together / Groq / etc. (needs key)" \
    "Mock NPU           — clone an existing model, tag as backend_type=npu (dev helper)" \
    "Skip               — bring the stack up only, register models later"
  case "$PICK_INDEX" in
    1) BACKEND=ollama ;;
    2) BACKEND=remote ;;
    3) BACKEND=cloud ;;
    4) BACKEND=mock-npu ;;
    5) BACKEND=skip ;;
  esac
fi
ok "backend: ${BACKEND}"

# -----------------------------------------------------------------------------
# 3. model selection — branches by backend
# -----------------------------------------------------------------------------
step "3/6 Model selection"
case "$BACKEND" in

  ollama)
    # 3a. Ollama must be installed + reachable.
    if ! command -v ollama >/dev/null; then
      cat <<EOF

  Ollama is needed for the local backend. Install with:
    macOS:    brew install ollama && brew services start ollama
    Linux:    curl -fsSL https://ollama.com/install.sh | sh && ollama serve &
    Windows:  winget install Ollama.Ollama  (or installer at https://ollama.com)

EOF
      die "Install Ollama and re-run (or re-run with --backend cloud)."
    fi
    if ! curl -sSf http://localhost:11434/api/tags >/dev/null 2>&1; then
      cat <<EOF

  Ollama is installed but the daemon isn't reachable on :11434. Start it:
    macOS:    brew services start ollama
    Linux:    ollama serve &
    Windows:  launch Ollama from the Start menu (it runs as a tray app)

EOF
      die "Start Ollama and re-run."
    fi
    ok "ollama daemon reachable on http://localhost:11434"

    # 3b. Build the list of models to register (multi-select supported).
    # Pulled via `ollama pull` in step 3c, then registered with add-model.sh in step 5b.
    MODELS_TO_REGISTER=()

    if [ -n "$MODEL" ]; then
      # --model flag: legacy single-model path
      MODELS_TO_REGISTER=("$MODEL")
    else
      installed=()
      while IFS= read -r line; do
        [ -n "$line" ] && installed+=("$line")
      done < <(ollama list 2>/dev/null | awk 'NR>1 {print $1}')

      if [ "${#installed[@]}" -gt 0 ]; then
        echo
        pick_multi "Models already on this machine — pick one or more (or pull a new one):" \
          "${installed[@]}" \
          "Pull a different model →"

        pull_new_idx=$((${#installed[@]} + 1))
        for idx in "${PICK_INDICES_ARR[@]}"; do
          if [ "$idx" -eq "$pull_new_idx" ]; then
            echo
            while :; do
              printf "    model to pull (e.g. qwen2.5:3b): "
              read -r new_model
              [ -n "$new_model" ] && break
              bad "name required — type a model id (e.g. qwen2.5:3b) or Ctrl-C to abort"
            done
            MODELS_TO_REGISTER+=("$new_model")
          else
            MODELS_TO_REGISTER+=("${installed[$((idx - 1))]}")
          fi
        done
      else
        echo "    No models pulled yet."
        echo "    Suggestions: qwen2.5:3b (~2 GB), llama3.2:3b (~2 GB), phi3:mini (~2 GB)"
        echo "    Browse: https://ollama.com/library"
        printf "    model to pull [qwen2.5:3b]: "
        read -r new_model
        new_model="${new_model:-qwen2.5:3b}"
        MODELS_TO_REGISTER+=("$new_model")
      fi
    fi
    ok "models: ${MODELS_TO_REGISTER[*]}"

    # 3c. Pull anything that isn't already on disk.
    if [ "$SKIP_PULL" -eq 0 ]; then
      for m in "${MODELS_TO_REGISTER[@]}"; do
        if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$m"; then
          ok "${m}: already pulled"
        else
          echo "    pulling ${m} (this can take a few minutes)"
          ollama pull "$m"
          ok "pulled ${m}"
        fi
      done
    fi
    ;;

  remote | cloud)
    ok "deferred — you'll be prompted by add-model.sh after the stack starts"
    ;;

  mock-npu)
    # Mock NPU clones an existing entry. We can only pick the source after the
    # stack is up + a real backend is registered, so the actual selection
    # happens in step 5b. Just tell the user what's coming.
    ok "deferred — you'll pick which model to mirror after the stack is up"
    ;;

  skip)
    ok "no model selected — register one later with ./scripts/add-model.sh"
    ;;

esac

# -----------------------------------------------------------------------------
# 4. .env (create + fill secrets + sync derived values)
# -----------------------------------------------------------------------------
step "4/6 Configuring .env"

# Each line: KEY,GENERATOR
# Generators: hex32, hex16, hex12, b64_32
# A secret is only generated if the value in .env currently ends in `replace-me`
# (e.g. `replace-me`, `sk-replace-me`, `pk-lf-replace-me`). The leading prefix
# from .env.example is preserved — the generator only fills the random tail.
SECRETS_DEF='
LITELLM_MASTER_KEY,hex32
LITELLM_SALT_KEY,hex32
POSTGRES_PASSWORD,hex16
JWT_SECRET,hex32
JWT_REFRESH_SECRET,hex32
CREDS_KEY,hex32
CREDS_IV,hex16
MONGO_INITDB_ROOT_PASSWORD,hex16
LANGFUSE_PUBLIC_KEY,hex16
LANGFUSE_SECRET_KEY,hex16
LANGFUSE_NEXTAUTH_SECRET,b64_32
LANGFUSE_SALT,b64_32
LANGFUSE_ENCRYPTION_KEY,hex32
LANGFUSE_INIT_USER_PASSWORD,hex12
CLICKHOUSE_PASSWORD,hex16
MINIO_ROOT_PASSWORD,hex16
GRAFANA_ADMIN_PASSWORD,hex12
E2E_USER_PASSWORD,hex16
'

gen() {
  case "$1" in
    hex32) openssl rand -hex 32 ;;
    hex16) openssl rand -hex 16 ;;
    hex12) openssl rand -hex 12 ;;
    b64_32) openssl rand -base64 32 ;;
    *) die "unknown generator: $1" ;;
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

# Replace any KEY=<prefix>replace-me with <prefix> + a freshly generated value.
# The prefix (e.g. `sk-`, `pk-lf-`, `sk-lf-`) is preserved from .env.example so
# provider-specific key shapes survive secret generation. Prefix-extraction is
# done in shell to stay portable across BSD awk (macOS) and gawk.
echo "$SECRETS_DEF" | while IFS=, read -r KEY GENERATOR; do
  [ -z "$KEY" ] && continue
  LINE=$(grep -E "^${KEY}=.*replace-me$" "$TMPFILE" || true)
  [ -z "$LINE" ] && continue
  CURRENT="${LINE#"${KEY}"=}"
  PREFIX="${CURRENT%replace-me}"
  NEWVAL="${PREFIX}$(gen "$GENERATOR")"
  awk -v k="$KEY" -v v="$NEWVAL" \
    '$0 ~ "^" k "=.*replace-me$" { print k"="v; next } { print }' \
    "$TMPFILE" >"${TMPFILE}.new" && mv "${TMPFILE}.new" "$TMPFILE"
done

# Sync derived values that depend on the generated secrets.
PG_PASS=$(grep -E "^POSTGRES_PASSWORD=" "$TMPFILE" | cut -d= -f2-)
MONGO_PASS=$(grep -E "^MONGO_INITDB_ROOT_PASSWORD=" "$TMPFILE" | cut -d= -f2-)

awk \
  -v pg="$PG_PASS" \
  -v mg="$MONGO_PASS" '
  /^DATABASE_URL=/ { print "DATABASE_URL=postgresql://npuops:" pg "@postgres:5432/npuops"; next }
  /^MONGO_URI=/    { print "MONGO_URI=mongodb://librechat:" mg "@mongodb:27017/LibreChat?authSource=admin"; next }
  { print }
' "$TMPFILE" >"${TMPFILE}.new" && mv "${TMPFILE}.new" "$TMPFILE"

mv "$TMPFILE" .env
ok "secrets populated"

# 4b. Rewrite public URLs for the given domain (Cloudflare Tunnel deploys).
# Skipped on local dev runs (no --domain).
if [ -n "$DOMAIN" ]; then
  ./scripts/update-domain.sh "$DOMAIN" --yes
  ok "public URLs pointed at ${DOMAIN}"
fi

# -----------------------------------------------------------------------------
# 5. docker compose up + wait for healthy
# -----------------------------------------------------------------------------
step "5/6 Starting Docker stack"

# LibreChat ships from the fork repo at ghcr.io/dudaji-vn/librechat. Pull it
# explicitly first so the ~150 MB download shows progress instead of
# disappearing inside `docker compose up -d`. Requires `docker login ghcr.io`
# beforehand — see README.md "LibreChat customization" for the one-time auth.
docker compose pull librechat
ok "librechat image ready"

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
# 5b. Register a model with the proxy.
# litellm/config.yaml ships with an empty model_list — every model gets
# registered through add-model.sh so the convention (backend_type, hardware_id,
# costs) is enforced in one place. add-model.sh refuses to add a duplicate
# model_name, so re-runs of bootstrap don't double-register.
# -----------------------------------------------------------------------------
MODEL_NAME=""
case "$BACKEND" in

  ollama)
    # Register each picked model with --no-restart so we don't recreate the
    # stack N times. We do one explicit restart at the end if anything was
    # actually added (skipped if every model was already registered).
    any_added=0
    for m in "${MODELS_TO_REGISTER[@]}"; do
      mname=$(echo "$m" | tr ':/' '--') # qwen2.5:3b → qwen2.5-3b
      # Avoid `yq | grep -q`: under `set -o pipefail`, grep -q closes the pipe
      # early and yq exits 141 (SIGPIPE), making the `if` evaluate the success
      # case as false. Use yq's own boolean operator instead.
      if [ "$(mname="$mname" yq eval '.model_list | any_c(.model_name == strenv(mname))' litellm/config.yaml 2>/dev/null)" = "true" ]; then
        ok "model '${mname}' already registered (skipping)"
      else
        step "Registering '${mname}' with the proxy"
        ./scripts/add-model.sh \
          --name "$mname" \
          --model "openai/${m}" \
          --base-url-env GPU_BACKEND_BASE_URL \
          --api-key-env GPU_BACKEND_API_KEY \
          --backend-type gpu \
          --hardware-id "${GPU_HARDWARE_ID:-mac-local}" \
          --no-test --no-restart
        any_added=1
      fi
      MODEL_NAME="$mname" # smoke test runs against the last picked model
    done

    [ "$any_added" -eq 1 ] && restart_stack
    ;;

  remote)
    step "Registering a remote OpenAI-compatible model"
    cat <<EOF
    Hand-off to add-model.sh — answer its prompts. For vLLM / TGI / a real
    GPU or NPU box, the typical answers look like:
      Upstream id    openai/llama-3-8b      (the openai/ prefix routes via the
                                             OpenAI-compatible adapter — works
                                             with vLLM, TGI, custom servers)
      Base URL       http://10.0.0.5:8000/v1
                     http://gpu-node-01.internal:8000/v1
      API key        often "dummy" if your server doesn't auth
      backend_type   gpu  (or npu when pointing at the real NPU box)
      hardware ID    gpu-node-01, npu-node-01
EOF
    echo
    ./scripts/add-model.sh
    MODEL_NAME=$(yq eval '.model_list[-1].model_name' litellm/config.yaml 2>/dev/null || echo "")
    ;;

  cloud)
    step "Registering a cloud model"
    cat <<EOF
    Hand-off to add-model.sh — answer its prompts. Common provider formats:
      OpenAI     → openai/gpt-4o-mini
      Anthropic  → anthropic/claude-3-5-sonnet-20241022
      Together   → together_ai/mistralai/Mixtral-8x7B-Instruct-v0.1
      Groq       → groq/llama-3.1-70b-versatile
EOF
    echo
    ./scripts/add-model.sh
    MODEL_NAME=$(yq eval '.model_list[-1].model_name' litellm/config.yaml 2>/dev/null || echo "")
    ;;

  mock-npu)
    # Clone an existing entry, rename it <orig>-mock-npu, and flip
    # backend_type=npu / hardware_id=mock-npu. Bypasses add-model.sh because
    # we're literally copying an entry that already passed validation.
    existing=()
    while IFS= read -r line; do
      [ -n "$line" ] && existing+=("$line")
    done < <(yq eval '.model_list[].model_name' litellm/config.yaml 2>/dev/null)

    if [ "${#existing[@]}" -eq 0 ]; then
      die "no models registered to clone — run bootstrap with --backend ollama|remote|cloud first"
    fi

    echo
    pick "Pick a model to mirror as a mock NPU (canary UI dev):" "${existing[@]}"
    src="$PICK_VALUE"
    mock_name="${src}-mock-npu"

    # See note on the SIGPIPE pitfall above.
    if [ "$(mock_name="$mock_name" yq eval '.model_list | any_c(.model_name == strenv(mock_name))' litellm/config.yaml)" = "true" ]; then
      ok "mock '${mock_name}' already exists (skipping)"
    else
      step "Cloning '${src}' as '${mock_name}' (backend_type=npu, hardware_id=mock-npu)"
      export src mock_name
      yq eval -i '
        .model_list += [(
          .model_list[] | select(.model_name == strenv(src))
          | .model_name              = strenv(mock_name)
          | .model_info.backend_type = "npu"
          | .model_info.hardware_id  = "mock-npu"
        )]
      ' litellm/config.yaml
      # Match add-model.sh's dedup posture (`| unique`) so a re-run can't create
      # a duplicate entry in the LibreChat fallback list.
      yq eval -i '.endpoints.custom[0].models.default = ((.endpoints.custom[0].models.default + [strenv(mock_name)]) | unique)' librechat.yaml
      ok "wrote ${mock_name} to litellm/config.yaml + librechat.yaml"
      restart_stack
    fi
    MODEL_NAME="$mock_name"
    ;;

  skip)
    warn "no model registered — run ./scripts/add-model.sh whenever you're ready"
    ;;

esac

# -----------------------------------------------------------------------------
# 6. smoke test (only meaningful if a model is registered)
# -----------------------------------------------------------------------------
if [ "$SKIP_SMOKE" -eq 1 ]; then
  step "6/6 Smoke test skipped (--skip-smoke-test)"
elif [ -z "$MODEL_NAME" ]; then
  step "6/6 Smoke test skipped (no model registered)"
else
  step "6/6 Running smoke test"
  MODEL="$MODEL_NAME" ./scripts/smoke-test.sh
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
    LibreChat        http://localhost:3080
    Grafana          http://localhost:3002   (not yet deployed)

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
