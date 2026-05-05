#!/usr/bin/env bash
# =============================================================================
# scripts/add-model.sh — register a new OpenAI-compatible model on the platform
# =============================================================================
#
# USAGE
#   ./scripts/add-model.sh                  # interactive (prompts for fields)
#   ./scripts/add-model.sh --help
#
#   # non-interactive (CI / one-liner):
#   ./scripts/add-model.sh \
#       --name mixtral-8x7b \
#       --model 'openai/mistralai/Mixtral-8x7B-Instruct-v0.1' \
#       --base-url https://api.together.xyz/v1 \
#       --api-key-env TOGETHER_API_KEY \
#       --backend-type cloud \
#       --hardware-id together-cloud \
#       --input-cost 0.0000003 \
#       --output-cost 0.0000009
#
#   # base URL via env var (recommended when several models share one backend):
#   ./scripts/add-model.sh --name gemma4 --model gemma4 \
#       --base-url-env GPU_BACKEND_BASE_URL \
#       --api-key-env  GPU_BACKEND_API_KEY \
#       --backend-type gpu --hardware-id mac-local
#
#   # native LiteLLM provider — no --base-url, LiteLLM has the endpoint built
#   # in. See https://docs.litellm.ai/docs/providers/gemini (and /anthropic,
#   # /cohere, /deepseek, /xai, /mistral, /groq, /perplexity, /ai21, /replicate).
#   ./scripts/add-model.sh \
#       --name gemini-2.0-flash \
#       --model 'gemini/gemini-2.0-flash' \
#       --api-key-env GEMINI_API_KEY \
#       --backend-type cloud \
#       --hardware-id gemini-cloud
#
# WHAT IT DOES
#   1. Validates inputs and checks the name isn't already taken
#   2. Appends a new entry to litellm/config.yaml (model_list[])
#   3. Adds the model name to librechat.yaml dropdown (unless --no-librechat)
#   4. Restarts litellm-proxy + librechat
#   5. Sends a test chat completion (unless --no-test)
#
# REQUIREMENTS
#   - yq  (mikefarah's: https://github.com/mikefarah/yq)
#         macOS:  brew install yq
#         Linux:  snap install yq   # or download from GH releases
#   - docker, curl
#
# CONVENTIONS (enforced by this script)
#   - Every model has `backend_type` and `hardware_id` (see CLAUDE.md).
#   - API keys default to env-var references (`os.environ/<NAME>`) so secrets
#     never land in litellm/config.yaml.
#
# AFTER RUNNING — if you used --api-key-env, add the secret to .env:
#       echo "TOGETHER_API_KEY=sk-..." >> .env
#       docker compose restart litellm-proxy
# =============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

# -----------------------------------------------------------------------------
# pretty output
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
die() {
  echo "${RED}error:${RESET} $*" >&2
  exit 1
}
# helpers for interactive UI — write to stderr so $(...) doesn't capture them
hint() { printf "    ${DIM}%s${RESET}\n" "$*" >&2; }
group() { printf "\n${BOLD}${CYAN}[%s/%s]${RESET} ${BOLD}%s${RESET}\n" "$1" "$2" "$3" >&2; }
bad() { printf "    ${RED}✗${RESET} %s\n" "$*" >&2; }

# -----------------------------------------------------------------------------
# defaults + flags
# -----------------------------------------------------------------------------
NAME=""
UPSTREAM=""
BASE_URL=""
BASE_URL_ENV=""
API_KEY_ENV=""
API_KEY_INLINE=""
BACKEND_TYPE=""
HARDWARE_ID=""
SUPPORTS_VISION="false"
DEFAULT_INPUT_COST="0.00000020"
DEFAULT_OUTPUT_COST="0.00000060"
INPUT_COST=""
OUTPUT_COST=""
ADD_TO_LIBRECHAT=1
RUN_TEST=1
DO_RESTART=1
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --name)
      NAME="$2"
      shift 2
      ;;
    --model)
      UPSTREAM="$2"
      shift 2
      ;;
    --base-url)
      BASE_URL="$2"
      shift 2
      ;;
    --base-url-env)
      BASE_URL_ENV="$2"
      shift 2
      ;;
    --api-key-env)
      API_KEY_ENV="$2"
      shift 2
      ;;
    --api-key)
      API_KEY_INLINE="$2"
      shift 2
      ;;
    --backend-type)
      BACKEND_TYPE="$2"
      shift 2
      ;;
    --hardware-id)
      HARDWARE_ID="$2"
      shift 2
      ;;
    --vision)
      SUPPORTS_VISION="true"
      shift
      ;;
    --input-cost)
      INPUT_COST="$2"
      shift 2
      ;;
    --output-cost)
      OUTPUT_COST="$2"
      shift 2
      ;;
    --no-librechat)
      ADD_TO_LIBRECHAT=0
      shift
      ;;
    --no-test)
      RUN_TEST=0
      shift
      ;;
    --no-restart)
      DO_RESTART=0
      RUN_TEST=0
      shift
      ;; # batch-mode for bootstrap
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h | --help)
      sed -n '2,58p' "$0"
      exit 0
      ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

# -----------------------------------------------------------------------------
# prerequisites
# -----------------------------------------------------------------------------
command -v yq >/dev/null || die "yq required — brew install yq  (https://github.com/mikefarah/yq)"
command -v docker >/dev/null || die "docker required"
command -v curl >/dev/null || die "curl required"

# -----------------------------------------------------------------------------
# interactive prompts (only for fields not passed via flags, only if stdin is a TTY)
#
# IMPORTANT: prompts must go to stderr, not stdout — otherwise $(ask ...) would
# capture the prompt text along with the user's answer.
# -----------------------------------------------------------------------------
ask() {
  local label="$1"
  local default="${2:-}"
  local value
  if [ -n "$default" ]; then
    printf "    ${BOLD}%s${RESET} ${DIM}[%s]${RESET}: " "$label" "$default" >&2
  else
    printf "    ${BOLD}%s${RESET}: " "$label" >&2
  fi
  read -r value
  printf "%s" "${value:-$default}"
}

# Re-prompt until the answer is non-empty.
ask_required() {
  local label="$1" default="${2:-}" value
  while :; do
    value=$(ask "$label" "$default")
    [ -n "$value" ] && {
      printf "%s" "$value"
      return
    }
    bad "required"
  done
}

# Re-prompt until the answer matches one of the space-separated $2 choices.
ask_choice() {
  local label="$1" choices="$2" default="${3:-}" value c
  while :; do
    value=$(ask "$label" "$default")
    for c in $choices; do
      [ "$value" = "$c" ] && {
        printf "%s" "$value"
        return
      }
    done
    bad "must be one of: $choices"
  done
}

# Suggest backend_type / api_key_env / hardware_id based on the URL.
suggest_backend_type() {
  case "$1" in
    *openai.com* | *anthropic.com* | *together.xyz* | *groq.com* | *deepinfra* | *fireworks.ai* | *mistral.ai* | *googleapis.com* | *x.ai*) echo "cloud" ;;
    *) echo "gpu" ;;
  esac
}
suggest_api_key_env() {
  case "$1" in
    *openai.com*) echo "OPENAI_API_KEY" ;;
    *anthropic.com*) echo "ANTHROPIC_API_KEY" ;;
    *together.xyz*) echo "TOGETHER_API_KEY" ;;
    *groq.com*) echo "GROQ_API_KEY" ;;
    *fireworks.ai*) echo "FIREWORKS_API_KEY" ;;
    *mistral.ai*) echo "MISTRAL_API_KEY" ;;
    *x.ai*) echo "XAI_API_KEY" ;;
    *) echo "" ;;
  esac
}
suggest_hardware_id() {
  local backend_type="$1" url="$2"
  if [ "$backend_type" = "cloud" ]; then
    case "$url" in
      *openai.com*) echo "openai-cloud" ;;
      *anthropic.com*) echo "anthropic-cloud" ;;
      *together.xyz*) echo "together-cloud" ;;
      *groq.com*) echo "groq-cloud" ;;
      *fireworks.ai*) echo "fireworks-cloud" ;;
      *mistral.ai*) echo "mistral-cloud" ;;
      *x.ai*) echo "xai-cloud" ;;
      *) echo "" ;;
    esac
  fi
}

# Native LiteLLM providers — these have their endpoint built into LiteLLM, so
# api_base is optional (and usually omitted). When the upstream id starts with
# one of these prefixes we skip the base-URL prompt and write the YAML entry
# without an api_base field. https://docs.litellm.ai/docs/providers
is_native_provider() {
  case "$1" in
    gemini/* | anthropic/* | cohere/* | deepseek/* | xai/* | mistral/* | groq/* | perplexity/* | ai21/* | replicate/*) return 0 ;;
    *) return 1 ;;
  esac
}
suggest_api_key_env_from_provider() {
  case "${1%%/*}" in
    gemini) echo "GEMINI_API_KEY" ;;
    anthropic) echo "ANTHROPIC_API_KEY" ;;
    cohere) echo "COHERE_API_KEY" ;;
    deepseek) echo "DEEPSEEK_API_KEY" ;;
    xai) echo "XAI_API_KEY" ;;
    mistral) echo "MISTRAL_API_KEY" ;;
    groq) echo "GROQ_API_KEY" ;;
    perplexity) echo "PERPLEXITYAI_API_KEY" ;;
    ai21) echo "AI21_API_KEY" ;;
    replicate) echo "REPLICATE_API_KEY" ;;
    *) echo "" ;;
  esac
}
suggest_hardware_id_from_provider() {
  case "${1%%/*}" in
    gemini) echo "gemini-cloud" ;;
    anthropic) echo "anthropic-cloud" ;;
    cohere) echo "cohere-cloud" ;;
    deepseek) echo "deepseek-cloud" ;;
    xai) echo "xai-cloud" ;;
    mistral) echo "mistral-cloud" ;;
    groq) echo "groq-cloud" ;;
    perplexity) echo "perplexity-cloud" ;;
    ai21) echo "ai21-cloud" ;;
    replicate) echo "replicate-cloud" ;;
    *) echo "" ;;
  esac
}

if [ -t 0 ]; then
  step "Add a new OpenAI-compatible model to NPUOps"
  hint "Press Ctrl-C to abort. Defaults shown in [brackets] — hit enter to accept."

  if [ -z "$NAME" ]; then
    group 1 7 "Display name"
    hint "What users see in the LibreChat dropdown."
    hint "Examples: gpt-4o-mini, mixtral-8x7b, claude-3-5-sonnet"
    NAME=$(ask_required "name")
  fi

  if [ -z "$UPSTREAM" ]; then
    group 2 7 "Upstream model id"
    hint "What the backend actually serves. LiteLLM needs a provider prefix to pick"
    hint "the right adapter — if you omit it, we'll add 'openai/' (correct for any"
    hint "OpenAI-compatible backend: Ollama, vLLM, TGI, Together, …)."
    hint "Examples:"
    hint "  gemma4                                          → openai/gemma4"
    hint "  openai/gpt-4o-mini"
    hint "  anthropic/claude-3-5-sonnet-20241022"
    UPSTREAM=$(ask_required "upstream model id")
  fi

  if [ -z "$BASE_URL" ] && [ -z "$BASE_URL_ENV" ]; then
    group 3 7 "API base URL"
    if is_native_provider "$UPSTREAM"; then
      hint "Skipping — '${UPSTREAM%%/*}/' is a native LiteLLM provider with a"
      hint "built-in endpoint. (Pass --base-url only if routing through a proxy.)"
    else
      hint "Two options — pick one:"
      hint "  • env var name (recommended: shared between models, easy to change)"
      hint "  • inline URL (one-off backends)"
      hint "Common env vars in .env: GPU_BACKEND_BASE_URL, NPU_BACKEND_BASE_URL"
      hint "Inline examples: https://api.openai.com/v1, http://host.docker.internal:11434/v1"
      BASE_URL_ENV=$(ask "env var name (blank to enter URL inline)")
      if [ -z "$BASE_URL_ENV" ]; then
        BASE_URL=$(ask_required "base URL")
      fi
    fi
  fi

  # We need a concrete URL for downstream suggestions (api-key-env, hardware-id);
  # if the user picked an env var, resolve it from .env so suggest_* still works.
  url_for_suggestions="$BASE_URL"
  if [ -z "$url_for_suggestions" ] && [ -n "$BASE_URL_ENV" ] && [ -f .env ]; then
    url_for_suggestions=$(grep -E "^${BASE_URL_ENV}=" .env | head -1 | cut -d= -f2-)
  fi

  if [ -z "$API_KEY_ENV" ] && [ -z "$API_KEY_INLINE" ]; then
    group 4 7 "API key"
    hint "Recommended: store in .env, reference by env var name (no secrets in git)."
    hint "Leave blank to provide an inline key instead (only safe for dummy/dev backends)."
    suggested_env=$(suggest_api_key_env "$url_for_suggestions")
    [ -z "$suggested_env" ] && suggested_env=$(suggest_api_key_env_from_provider "$UPSTREAM")
    API_KEY_ENV=$(ask "env var name (e.g. OPENAI_API_KEY)" "$suggested_env")
    if [ -z "$API_KEY_ENV" ]; then
      API_KEY_INLINE=$(ask_required "inline API key")
    fi
  fi

  if [ -z "$BACKEND_TYPE" ]; then
    group 5 7 "Backend type"
    hint "gpu = local GPU node, npu = NPU node, cloud = managed provider."
    suggested_bt=$(suggest_backend_type "$url_for_suggestions")
    is_native_provider "$UPSTREAM" && suggested_bt="cloud"
    BACKEND_TYPE=$(ask_choice "backend type (gpu/npu/cloud)" "gpu npu cloud" "$suggested_bt")
  fi

  if [ -z "$HARDWARE_ID" ]; then
    group 6 7 "Hardware ID"
    hint "Used by cost / usage reports to aggregate by hardware or cloud."
    hint "Examples: gpu-node-01, npu-node-01, openai-cloud, together-cloud"
    suggested_hw=$(suggest_hardware_id "$BACKEND_TYPE" "$url_for_suggestions")
    [ -z "$suggested_hw" ] && suggested_hw=$(suggest_hardware_id_from_provider "$UPSTREAM")
    HARDWARE_ID=$(ask_required "hardware ID" "$suggested_hw")
  fi

  if [ -z "$INPUT_COST" ] || [ -z "$OUTPUT_COST" ]; then
    group 7 7 "Cost per token (USD)"
    hint "Shown in Langfuse / cost reports. Defaults are platform-wide guesses;"
    hint "override per-model when you have real numbers from your provider."
    [ -z "$INPUT_COST" ] && INPUT_COST=$(ask "input  cost / token" "$DEFAULT_INPUT_COST")
    [ -z "$OUTPUT_COST" ] && OUTPUT_COST=$(ask "output cost / token" "$DEFAULT_OUTPUT_COST")
  fi
fi

# Apply defaults for non-interactive runs that didn't pass --input-cost/--output-cost.
[ -n "$INPUT_COST" ] || INPUT_COST="$DEFAULT_INPUT_COST"
[ -n "$OUTPUT_COST" ] || OUTPUT_COST="$DEFAULT_OUTPUT_COST"

# -----------------------------------------------------------------------------
# validate
# -----------------------------------------------------------------------------
[ -n "$NAME" ] || die "model name required (--name)"
[ -n "$UPSTREAM" ] || die "upstream model id required (--model)"
if [ -z "$BASE_URL" ] && [ -z "$BASE_URL_ENV" ]; then
  is_native_provider "$UPSTREAM" || die "base URL required (--base-url or --base-url-env) for OpenAI-compatible backends"
fi
[ -n "$HARDWARE_ID" ] || die "hardware ID required (--hardware-id)"
[ -n "$BACKEND_TYPE" ] || BACKEND_TYPE="gpu"
[[ "$BACKEND_TYPE" =~ ^(gpu|npu|cloud)$ ]] || die "backend type must be gpu, npu, or cloud (got: $BACKEND_TYPE)"

# Resolve base URL — env-var ref takes precedence over inline. May be empty
# for native LiteLLM providers (gemini/, anthropic/, …); the YAML write below
# strips api_base in that case.
if [ -n "$BASE_URL_ENV" ]; then
  BASE_URL_VALUE="os.environ/$BASE_URL_ENV"
else
  BASE_URL_VALUE="$BASE_URL"
fi

# LiteLLM needs a provider prefix to pick the right adapter. Bare ids like
# "gemma4" silently fail with "no healthy deployments" — auto-prefix with
# "openai/" since every supported backend in this stack is OpenAI-compatible.
if [[ "$UPSTREAM" != */* ]]; then
  warn "no provider prefix on '$UPSTREAM' — using 'openai/$UPSTREAM' (OpenAI-compatible adapter)"
  UPSTREAM="openai/$UPSTREAM"
fi

if [ -n "$API_KEY_ENV" ]; then
  API_KEY_VALUE="os.environ/$API_KEY_ENV"
elif [ -n "$API_KEY_INLINE" ]; then
  API_KEY_VALUE="$API_KEY_INLINE"
  warn "Inline API key — this will be written to litellm/config.yaml (which is in git)"
else
  die "API key required (--api-key-env or --api-key)"
fi

# Idempotency check. Re-runs with an existing model_name skip the litellm/config.yaml
# append silently (the LibreChat sync below already dedupes via `| unique`, and
# the test/restart still run). To *update* an existing entry, remove it first.
#
# IMPORTANT: do NOT pipe yq into `grep -q`. `grep -q` exits early on the first
# match, sending SIGPIPE to yq, which makes the pipeline exit 141 under
# `set -o pipefail` — the `if` then evaluates the success case as false. Use
# yq's own boolean operator instead.
ALREADY_REGISTERED=0
if [ "$(NAME="$NAME" yq eval '.model_list | any_c(.model_name == strenv(NAME))' litellm/config.yaml 2>/dev/null)" = "true" ]; then
  ALREADY_REGISTERED=1
fi

# -----------------------------------------------------------------------------
# summary + confirm
# -----------------------------------------------------------------------------
echo
step "Summary"
printf "    %-22s ${BOLD}%s${RESET}\n" \
  "name" "${NAME}" \
  "upstream" "${UPSTREAM}" \
  "base URL" "${BASE_URL_VALUE:-(none — native provider)}" \
  "api_key" "${API_KEY_VALUE}" \
  "backend_type" "${BACKEND_TYPE}" \
  "hardware_id" "${HARDWARE_ID}" \
  "supports_vision" "${SUPPORTS_VISION}" \
  "input cost / token" "${INPUT_COST}" \
  "output cost / token" "${OUTPUT_COST}" \
  "add to LibreChat" "$([ "$ADD_TO_LIBRECHAT" -eq 1 ] && echo yes || echo no)"

if [ "$DRY_RUN" -eq 1 ]; then
  step "Dry run — no files written"
  exit 0
fi

if [ -t 0 ]; then
  echo
  # Default Y — by this point the user has filled out the whole form, so a
  # bare enter should accept. Any unrecognized input re-prompts (so a stray
  # keypress doesn't trash the in-progress registration).
  while :; do
    printf "    %sProceed?%s [Y/n]: " "$BOLD" "$RESET"
    read -r confirm
    case "$confirm" in
      "" | [Yy] | [Yy][Ee][Ss]) break ;;
      [Nn] | [Nn][Oo]) die "aborted" ;;
      *) bad "please answer y or n (or Ctrl-C to abort)" ;;
    esac
  done
fi

# -----------------------------------------------------------------------------
# update litellm/config.yaml
# -----------------------------------------------------------------------------
export NAME UPSTREAM BASE_URL_VALUE API_KEY_VALUE BACKEND_TYPE HARDWARE_ID SUPPORTS_VISION INPUT_COST OUTPUT_COST
if [ "$ALREADY_REGISTERED" -eq 1 ]; then
  step "Skipping litellm/config.yaml — '$NAME' already registered"
  warn "to update params for '$NAME', remove it from litellm/config.yaml first, then re-run"
else
  step "Updating litellm/config.yaml"
  yq eval -i '
    .model_list += [{
      "model_name": strenv(NAME),
      "litellm_params": {
        "model": strenv(UPSTREAM),
        "api_base": strenv(BASE_URL_VALUE),
        "api_key": strenv(API_KEY_VALUE),
        "input_cost_per_token": (strenv(INPUT_COST) | from_yaml),
        "output_cost_per_token": (strenv(OUTPUT_COST) | from_yaml)
      },
      "model_info": {
        "backend_type": strenv(BACKEND_TYPE),
        "hardware_id": strenv(HARDWARE_ID),
        "supports_vision": (strenv(SUPPORTS_VISION) | from_yaml)
      }
    }]
  ' litellm/config.yaml
  # Native LiteLLM providers (gemini/, anthropic/, …) don't take an api_base —
  # strip it back out if the user didn't supply one.
  if [ -z "$BASE_URL_VALUE" ]; then
    yq eval -i 'del(.model_list[-1].litellm_params.api_base)' litellm/config.yaml
  fi
  ok "appended '$NAME' to model_list"
fi

# -----------------------------------------------------------------------------
# update librechat/librechat.yaml
# -----------------------------------------------------------------------------
if [ "$ADD_TO_LIBRECHAT" -eq 1 ] && [ -f librechat/librechat.yaml ]; then
  step "Updating librechat/librechat.yaml"
  # Append + dedupe in one shot. The dedupe self-heals any duplicates left
  # behind by earlier runs (the litellm uniqueness check protects model_list
  # but the dropdown was previously append-only).
  yq eval -i '.endpoints.custom[0].models.default = ((.endpoints.custom[0].models.default + [strenv(NAME)]) | unique)' librechat/librechat.yaml
  ok "added to LibreChat dropdown"
fi

# -----------------------------------------------------------------------------
# .env reminder
#
# Order matters: we MUST resolve missing env vars BEFORE the restart below.
# litellm-proxy uses `env_file: .env` (see docker-compose.yml), so vars added
# here flow into the container automatically on the next start. Without this
# step, the proxy boots with empty values and the smoke test fails — the user
# then has to edit .env and restart manually, which is exactly the trap the
# Gemini onboarding hit.
# -----------------------------------------------------------------------------
prompt_or_warn_missing_env() {
  # $1 = env var name, $2 = example value (for the manual-fix hint)
  local var="$1" example="$2" entered=""
  [ -z "$var" ] && return 0
  grep -qE "^${var}=" .env 2>/dev/null && return 0

  if [ -t 0 ]; then
    warn "${var} is not in .env yet — the proxy will start with it empty."
    printf "    Paste the value now (or press enter to skip): "
    # -s so secrets don't appear on the terminal; print our own newline since
    # the user's enter keystroke isn't echoed.
    read -rs entered
    echo
    if [ -n "$entered" ]; then
      printf "%s=%s\n" "$var" "$entered" >>.env
      ok "wrote ${var} to .env"
      return 0
    fi
  else
    warn "${var} is not set in .env."
  fi
  warn "skipping restart + test — set it manually, then run:"
  echo "      echo '${var}=${example}' >> .env"
  echo "      docker compose restart litellm-proxy"
  DO_RESTART=0
  RUN_TEST=0
}
prompt_or_warn_missing_env "$API_KEY_ENV" "<your-real-key>"
prompt_or_warn_missing_env "$BASE_URL_ENV" "https://..."

# -----------------------------------------------------------------------------
# restart services
# -----------------------------------------------------------------------------
if [ "$DO_RESTART" -eq 1 ]; then
  step "Restarting services"
  RECREATE_LIST=("litellm-proxy")
  [ "$ADD_TO_LIBRECHAT" -eq 1 ] && RECREATE_LIST+=("librechat")
  docker compose up -d --force-recreate "${RECREATE_LIST[@]}" >/dev/null
  ok "restarted ${RECREATE_LIST[*]}"

  echo "    waiting for litellm-proxy to be healthy..."
  for i in $(seq 1 24); do
    state=$(docker inspect --format '{{.State.Health.Status}}' npuops-litellm 2>/dev/null || echo missing)
    if [ "$state" = "healthy" ]; then
      echo
      ok "healthy"
      break
    fi
    printf "."
    sleep 5
    if [ "$i" -eq 24 ]; then
      echo
      warn "litellm-proxy did not become healthy in 2 minutes"
      warn "check: docker compose logs litellm-proxy"
    fi
  done
else
  step "Skipping restart (--no-restart) — caller will batch-restart"
fi

# -----------------------------------------------------------------------------
# test
# -----------------------------------------------------------------------------
if [ "$RUN_TEST" -eq 1 ]; then
  step "Sending test chat completion to '$NAME'"
  if [ -z "${LITELLM_MASTER_KEY:-}" ] && [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . .env
    set +a
  fi
  if [ -z "${LITELLM_MASTER_KEY:-}" ]; then
    warn "LITELLM_MASTER_KEY not set; skipping test"
  else
    body="{\"model\":\"$NAME\",\"messages\":[{\"role\":\"user\",\"content\":\"say hi in 5 words\"}],\"max_tokens\":20}"
    if response=$(curl -fsS \
      -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
      -H "Content-Type: application/json" \
      -X POST "http://localhost:4000/v1/chat/completions" \
      -d "$body" 2>&1); then
      ok "test passed"
      echo "    response (first 200 chars): $(echo "$response" | head -c 200)"
    else
      warn "test failed"
      echo "    error: $response"
      echo "    check: docker compose logs litellm-proxy"
    fi
  fi
fi

# -----------------------------------------------------------------------------
# done
# -----------------------------------------------------------------------------
step "Done!"
cat <<EOF

  ${BOLD}'${NAME}' is now registered.${RESET}
  • LibreChat:  http://localhost:3080  (refresh — '${NAME}' in the model dropdown)
  • Langfuse:   http://localhost:3000  (traces tagged hardware_id=${HARDWARE_ID})
  • To remove:  edit litellm/config.yaml and librechat/librechat.yaml directly,
                then restart with docker compose restart litellm-proxy librechat

EOF
