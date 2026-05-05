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
# defaults + flags
# -----------------------------------------------------------------------------
NAME=""
UPSTREAM=""
BASE_URL=""
API_KEY_ENV=""
API_KEY_INLINE=""
BACKEND_TYPE=""
HARDWARE_ID=""
SUPPORTS_VISION="false"
INPUT_COST="0.00000020"
OUTPUT_COST="0.00000060"
ADD_TO_LIBRECHAT=1
RUN_TEST=1
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --name)             NAME="$2"; shift 2 ;;
    --model)            UPSTREAM="$2"; shift 2 ;;
    --base-url)         BASE_URL="$2"; shift 2 ;;
    --api-key-env)      API_KEY_ENV="$2"; shift 2 ;;
    --api-key)          API_KEY_INLINE="$2"; shift 2 ;;
    --backend-type)     BACKEND_TYPE="$2"; shift 2 ;;
    --hardware-id)      HARDWARE_ID="$2"; shift 2 ;;
    --vision)           SUPPORTS_VISION="true"; shift ;;
    --input-cost)       INPUT_COST="$2"; shift 2 ;;
    --output-cost)      OUTPUT_COST="$2"; shift 2 ;;
    --no-librechat)     ADD_TO_LIBRECHAT=0; shift ;;
    --no-test)          RUN_TEST=0; shift ;;
    --dry-run)          DRY_RUN=1; shift ;;
    -h|--help)          sed -n '2,45p' "$0"; exit 0 ;;
    *)                  die "unknown argument: $1 (try --help)" ;;
  esac
done

# -----------------------------------------------------------------------------
# prerequisites
# -----------------------------------------------------------------------------
command -v yq >/dev/null     || die "yq required — brew install yq  (https://github.com/mikefarah/yq)"
command -v docker >/dev/null || die "docker required"
command -v curl >/dev/null   || die "curl required"

# -----------------------------------------------------------------------------
# interactive prompts (only for fields not passed via flags, only if stdin is a TTY)
# -----------------------------------------------------------------------------
ask() {
  local label="$1"
  local default="${2:-}"
  local value
  if [ -n "$default" ]; then
    printf "    %s [%s]: " "$label" "$default"
  else
    printf "    %s: " "$label"
  fi
  read -r value
  printf "%s" "${value:-$default}"
}

if [ -t 0 ]; then
  step "Add a new OpenAI-compatible model to NPUOps"

  if [ -z "$NAME" ]; then
    echo "    Display name (what users see in the LibreChat dropdown)."
    echo "    Examples: gpt-4o-mini, mixtral-8x7b, claude-3-5-sonnet"
    NAME=$(ask "  name")
  fi

  if [ -z "$UPSTREAM" ]; then
    echo
    echo "    Upstream model id (what the backend actually serves; must include"
    echo "    the LiteLLM provider prefix). Examples:"
    echo "      openai/gpt-4o-mini"
    echo "      openai/mistralai/Mixtral-8x7B-Instruct-v0.1"
    echo "      anthropic/claude-3-5-sonnet-20241022"
    UPSTREAM=$(ask "  upstream model id")
  fi

  if [ -z "$BASE_URL" ]; then
    echo
    echo "    API base URL. Examples:"
    echo "      https://api.openai.com/v1"
    echo "      https://api.together.xyz/v1"
    echo "      https://api.anthropic.com/v1"
    echo "      http://host.docker.internal:11434/v1     (host Ollama)"
    BASE_URL=$(ask "  base URL")
  fi

  if [ -z "$API_KEY_ENV" ] && [ -z "$API_KEY_INLINE" ]; then
    echo
    echo "    API key — recommended: store in .env, reference by env var name."
    echo "    Inline keys end up in git, only safe for dummy/dev backends."
    API_KEY_ENV=$(ask "  env var name (e.g. OPENAI_API_KEY)")
  fi

  if [ -z "$BACKEND_TYPE" ]; then
    echo
    BACKEND_TYPE=$(ask "  backend type (gpu/npu/cloud)" "gpu")
  fi

  if [ -z "$HARDWARE_ID" ]; then
    echo
    echo "    Hardware ID — used by W6 reports to aggregate by hardware/cloud."
    echo "    Examples: gpu-node-01, npu-node-01, openai-cloud, together-cloud"
    HARDWARE_ID=$(ask "  hardware ID")
  fi
fi

# -----------------------------------------------------------------------------
# validate
# -----------------------------------------------------------------------------
[ -n "$NAME" ]        || die "model name required (--name)"
[ -n "$UPSTREAM" ]    || die "upstream model id required (--model)"
[ -n "$BASE_URL" ]    || die "base URL required (--base-url)"
[ -n "$HARDWARE_ID" ] || die "hardware ID required (--hardware-id)"
[ -n "$BACKEND_TYPE" ] || BACKEND_TYPE="gpu"
[[ "$BACKEND_TYPE" =~ ^(gpu|npu|cloud)$ ]] || die "backend type must be gpu, npu, or cloud (got: $BACKEND_TYPE)"

if [ -n "$API_KEY_ENV" ]; then
  API_KEY_VALUE="os.environ/$API_KEY_ENV"
elif [ -n "$API_KEY_INLINE" ]; then
  API_KEY_VALUE="$API_KEY_INLINE"
  warn "Inline API key — this will be written to litellm/config.yaml (which is in git)"
else
  die "API key required (--api-key-env or --api-key)"
fi

# Uniqueness check
if yq eval '.model_list[].model_name' litellm/config.yaml 2>/dev/null | grep -Fxq "$NAME"; then
  die "model_name '$NAME' already exists in litellm/config.yaml"
fi

# -----------------------------------------------------------------------------
# summary + confirm
# -----------------------------------------------------------------------------
step "Summary"
cat <<EOF
    name:                ${NAME}
    upstream:            ${UPSTREAM}
    base URL:            ${BASE_URL}
    api_key:             ${API_KEY_VALUE}
    backend_type:        ${BACKEND_TYPE}
    hardware_id:         ${HARDWARE_ID}
    supports_vision:     ${SUPPORTS_VISION}
    input cost / token:  ${INPUT_COST}
    output cost / token: ${OUTPUT_COST}
    add to LibreChat:    $([ "$ADD_TO_LIBRECHAT" -eq 1 ] && echo yes || echo no)
EOF

if [ "$DRY_RUN" -eq 1 ]; then
  step "Dry run — no files written"
  exit 0
fi

if [ -t 0 ]; then
  printf "    Proceed? [y/N]: "
  read -r confirm
  case "$confirm" in [Yy]*) ;; *) die "aborted" ;; esac
fi

# -----------------------------------------------------------------------------
# update litellm/config.yaml
# -----------------------------------------------------------------------------
step "Updating litellm/config.yaml"
export NAME UPSTREAM BASE_URL API_KEY_VALUE BACKEND_TYPE HARDWARE_ID SUPPORTS_VISION INPUT_COST OUTPUT_COST
yq eval -i '
  .model_list += [{
    "model_name": strenv(NAME),
    "litellm_params": {
      "model": strenv(UPSTREAM),
      "api_base": strenv(BASE_URL),
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
ok "appended '$NAME' to model_list"

# -----------------------------------------------------------------------------
# update librechat/librechat.yaml
# -----------------------------------------------------------------------------
if [ "$ADD_TO_LIBRECHAT" -eq 1 ] && [ -f librechat/librechat.yaml ]; then
  step "Updating librechat/librechat.yaml"
  yq eval -i '.endpoints.custom[0].models.default += [strenv(NAME)]' librechat/librechat.yaml
  ok "added to LibreChat dropdown"
fi

# -----------------------------------------------------------------------------
# .env reminder
# -----------------------------------------------------------------------------
if [ -n "$API_KEY_ENV" ] && ! grep -qE "^${API_KEY_ENV}=" .env 2>/dev/null; then
  warn "${API_KEY_ENV} is not set in .env yet. Add it before testing:"
  echo "      echo '${API_KEY_ENV}=<your-real-key>' >> .env"
  echo "      docker compose restart litellm-proxy"
fi

# -----------------------------------------------------------------------------
# restart services
# -----------------------------------------------------------------------------
step "Restarting services"
RECREATE_LIST="litellm-proxy"
[ "$ADD_TO_LIBRECHAT" -eq 1 ] && RECREATE_LIST="$RECREATE_LIST librechat"
docker compose up -d --force-recreate $RECREATE_LIST >/dev/null
ok "restarted $RECREATE_LIST"

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
