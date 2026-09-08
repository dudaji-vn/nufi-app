#!/bin/bash
# install-box.sh — bring up a NuFi box on this machine.
#
#   curl -fsSL https://get.nufi.me/box | bash            # later: hosted
#   ./install-box.sh [--yes] [--dry-run] [--src DIR]      # from a checkout
#
# Asks four questions (box name, admin email, departments, inference profile),
# generates every secret here, renders the LiteLLM config, starts the stack,
# pulls the models, creates the admin and the ingest service account, and prints
# the URLs. Re-running keeps .env and the answers. bash 3.2 compatible.
set -euo pipefail

YES=0; DRY=0; SRC=""
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1 ;;
    --dry-run) DRY=1 ;;
    --src) SRC="${2:-}"; shift ;;
    --src=*) SRC="${1#--src=}" ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
  esac
  shift
done
[ "${NUFI_BOX_DRY_RUN:-0}" = "1" ] && DRY=1

# ---------- tiny helpers -----------------------------------------------------
say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m !!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m xx\033[0m %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY" = 1 ]; then printf '  $ %s\n' "$*"; else "$@"; fi; }
ask()  { # ask VAR "prompt" default
  local var="$1" prompt="$2" def="$3" cur
  eval "cur=\${$var:-}"
  if [ -n "$cur" ]; then return; fi
  if [ "$YES" = 1 ]; then eval "$var=\"\$def\""; return; fi
  printf '%s [%s]: ' "$prompt" "$def"; read -r ans; eval "$var=\"\${ans:-\$def}\""
}
gen_hex() { openssl rand -hex "$1"; }
gen_fernet() { openssl rand -base64 32 | tr '+/' '-_'; }

# ---------- where am I --------------------------------------------------------
OS="${NUFI_BOX_FAKE_OS:-$(uname -s)}"
ARCH="$(uname -m)"
HERE="$(cd "$(dirname "$0")" && pwd)"
BOX_HOME="${SRC:-$HERE}"
cd "$BOX_HOME"

have() { command -v "$1" >/dev/null 2>&1; }
has_nvidia() { [ "${NUFI_BOX_FAKE_NVIDIA:-}" = "1" ] || have nvidia-smi; }

# ---------- prerequisites ------------------------------------------------------
say "Checking prerequisites on $OS/$ARCH"
have openssl || die "openssl is required"
if [ "$DRY" = 0 ]; then
  have curl || die "curl is required"
  case "$OS" in
    Darwin)
      have brew || die "Homebrew is required on macOS: https://brew.sh"
      have docker || { say "Installing OrbStack (Docker-compatible, lighter than Docker Desktop)"; brew install --cask orbstack; }
      have ollama || { say "Installing Ollama"; brew install ollama; }
      pgrep -x ollama >/dev/null 2>&1 || brew services start ollama || (ollama serve >/dev/null 2>&1 &)
      ;;
    Linux)
      if ! have docker; then
        say "Installing Docker Engine"
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker "$USER" || true
      fi
      if has_nvidia && ! dpkg -s nvidia-container-toolkit >/dev/null 2>&1; then
        say "Installing the NVIDIA container toolkit"
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -sL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
          sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
          sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
        sudo apt-get update -qq && sudo apt-get install -y -qq nvidia-container-toolkit
        sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
      fi
      ;;
    *) die "unsupported OS: $OS (Windows: run this inside WSL2 Ubuntu)" ;;
  esac
  docker compose version >/dev/null 2>&1 || die "docker compose v2 is required"
  if [ "$OS" = "Darwin" ]; then
    mem=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
    [ "$mem" -lt 11000000000 ] && warn "Docker VM has $((mem/1073741824)) GB; give it 12 GB (Docker Desktop → Settings → Resources) or use OrbStack"
  fi
fi

# ---------- keep previous answers on a re-run; explicit overrides always win --
# NUFI_BOX_ENV can point .env somewhere else (tests use this to avoid touching
# the checkout). Caller-provided values for these are captured before sourcing
# the existing file and re-applied after, so `DEPARTMENTS=... ./install-box.sh`
# on an existing box always wins over what is already on disk; anything the
# caller did NOT set falls back to what the file has, which is what makes a
# bare re-run keep the previous answers instead of silently reverting them.
NUFI_BOX_ENV="${NUFI_BOX_ENV:-$BOX_HOME/.env}"
REUSE_VARS="BOX_NAME ADMIN_EMAIL DEPARTMENTS INFERENCE_PROFILE INFERENCE_MODEL INFERENCE_BASE_URL INFERENCE_API_KEY OLLAMA_BASE_URL EMBEDDINGS_MODEL NUFI_DATA_DIR"
for v in $REUSE_VARS; do eval "_caller_$v=\${$v:-}"; done
if [ -f "$NUFI_BOX_ENV" ]; then
  ok ".env exists; keeping its answers and secrets"
  # shellcheck disable=SC1090
  set -a; . "$NUFI_BOX_ENV"; set +a
fi
for v in $REUSE_VARS; do
  eval "_cv=\${_caller_$v}"
  [ -n "$_cv" ] && eval "$v=\"\$_cv\""
done

# ---------- the four questions ------------------------------------------------
say "Four questions"
ask BOX_NAME "Box name (becomes <name>.local)" "nufi"
ask ADMIN_EMAIL "Admin email" "admin@$BOX_NAME.local"
ask DEPARTMENTS "Departments (comma separated; one drive, team and agent each)" "legal,hr,ga,strategy"
for d in $(printf '%s' "$DEPARTMENTS" | tr ',' ' '); do
  case "$d" in
    *[!a-z0-9_-]*|"") die "invalid department name '$d': use lowercase letters, digits, '_' or '-' only" ;;
  esac
done
if [ "$OS" = "Darwin" ]; then def_profile=ollama
elif has_nvidia; then def_profile=ollama-docker
elif have ollama; then def_profile=ollama
else def_profile=ollama-docker; fi
ask INFERENCE_PROFILE "Inference profile (ollama | ollama-docker | remote | cloud)" "$def_profile"
case "$INFERENCE_PROFILE" in
  ollama)        ask INFERENCE_MODEL "Ollama model" "qwen2.5:7b"
                 INFERENCE_BASE_URL="http://host.docker.internal:11434/v1"; INFERENCE_API_KEY=ollama
                 OLLAMA_BASE_URL="http://host.docker.internal:11434" ;;
  ollama-docker) ask INFERENCE_MODEL "Ollama model" "qwen2.5:7b"
                 INFERENCE_BASE_URL="http://ollama:11434/v1"; INFERENCE_API_KEY=ollama
                 OLLAMA_BASE_URL="http://ollama:11434" ;;
  remote)        ask INFERENCE_BASE_URL "OpenAI-compatible base URL (…/v1)" "http://192.168.1.20:8000/v1"
                 ask INFERENCE_API_KEY "API key (any string if none)" "none"
                 ask INFERENCE_MODEL "Model id on that server" "qwen2.5-7b-instruct"
                 ask OLLAMA_BASE_URL "Ollama URL for embeddings" "http://host.docker.internal:11434" ;;
  cloud)         ask INFERENCE_BASE_URL "Provider base URL" "https://api.openai.com/v1"
                 ask INFERENCE_API_KEY "Provider API key" ""
                 ask INFERENCE_MODEL "Model id" "gpt-4o-mini"
                 ask OLLAMA_BASE_URL "Ollama URL for embeddings" "http://host.docker.internal:11434"
                 warn "cloud profile: prompts leave this machine; the box is not air-gapped" ;;
  *) die "unknown profile $INFERENCE_PROFILE" ;;
esac
NUFI_MODEL="$(printf '%s' "$INFERENCE_MODEL" | tr ':/' '--')"
EMBEDDINGS_MODEL="${EMBEDDINGS_MODEL:-bge-m3}"
BOX_HOST="$BOX_NAME.local"
if [ "$OS" = "Darwin" ]; then BOX_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1)"
else BOX_IP="$(hostname -I 2>/dev/null | awk '{print $1}')" || true; BOX_IP="${BOX_IP:-127.0.0.1}"; fi
[ "$DRY" = 1 ] && BOX_IP="${BOX_IP:-192.168.1.10}"
NUFI_DATA_DIR="${NUFI_DATA_DIR:-$BOX_HOME/data}"

# ---------- .env ----------------------------------------------------------------
say "Writing .env"
sec() { # sec VAR generator — keep an existing non-placeholder value
  local var="$1" gen="$2" cur; eval "cur=\${$var:-}"
  case "$cur" in ""|*replace-me*) eval "$var=\"\$($gen)\"" ;; esac
}
sec JWT_SECRET "gen_hex 32"; sec JWT_REFRESH_SECRET "gen_hex 32"; sec CREDS_KEY "gen_hex 32"; sec CREDS_IV "gen_hex 16"
sec LITELLM_MASTER_KEY "printf sk-%s \$(gen_hex 32)"; sec LITELLM_SALT_KEY "gen_hex 32"
sec POSTGRES_PASSWORD "gen_hex 16"; sec MONGO_PASSWORD "gen_hex 16"
sec ADMIN_PASSWORD "gen_hex 8"; sec INGEST_PASSWORD "gen_hex 16"
sec LANGFLOW_SECRET_KEY "gen_fernet"; sec STUDIO_SUPERUSER_PASSWORD "gen_hex 12"
sec ADMIN_SESSION_SECRET "gen_hex 32"; sec SAMBA_PASSWORD "gen_hex 8"
INGEST_EMAIL="${INGEST_EMAIL:-ingest@$BOX_NAME.local}"
if [ -z "${OIDC_PRIVATE_KEY_PEM:-}" ] || [ "$OIDC_PRIVATE_KEY_PEM" = "replace-me" ]; then
  OIDC_PRIVATE_KEY_PEM="$(openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 2>/dev/null | awk 'BEGIN{ORS="\\n"}{print}')"
fi
NVIDIA_VISIBLE_DEVICES=""
if [ "$OS" = "Linux" ] && has_nvidia; then NVIDIA_VISIBLE_DEVICES=all; fi

render_env() {
  cat <<EOF
BOX_NAME=$BOX_NAME
BOX_HOST=$BOX_HOST
BOX_IP=$BOX_IP
NUFI_DATA_DIR=$NUFI_DATA_DIR
NUFI_CHAT_TAG=${NUFI_CHAT_TAG:-main}
NUFI_CONSOLE_TAG=${NUFI_CONSOLE_TAG:-main}
NUFI_ADMIN_TAG=${NUFI_ADMIN_TAG:-main}
NUFI_STUDIO_TAG=${NUFI_STUDIO_TAG:-box-main}
NUFI_LITELLM_TAG=${NUFI_LITELLM_TAG:-main}
NUFI_INGEST_TAG=${NUFI_INGEST_TAG:-main}
NUFI_RAG_IMAGE=${NUFI_RAG_IMAGE:-ghcr.io/danny-avila/librechat-rag-api-dev-lite@sha256:f9f34c8ed6884b0ff9b17387e6174fed737dba29f21622ecb75604d82bc47bf8}
INFERENCE_PROFILE=$INFERENCE_PROFILE
INFERENCE_BASE_URL=$INFERENCE_BASE_URL
INFERENCE_API_KEY=$INFERENCE_API_KEY
INFERENCE_MODEL=$INFERENCE_MODEL
NUFI_MODEL=$NUFI_MODEL
EMBEDDINGS_MODEL=$EMBEDDINGS_MODEL
OLLAMA_BASE_URL=$OLLAMA_BASE_URL
NVIDIA_VISIBLE_DEVICES=$NVIDIA_VISIBLE_DEVICES
ADMIN_EMAIL=$ADMIN_EMAIL
ADMIN_PASSWORD=$ADMIN_PASSWORD
INGEST_EMAIL=$INGEST_EMAIL
INGEST_PASSWORD=$INGEST_PASSWORD
DEPARTMENTS=$DEPARTMENTS
JWT_SECRET=$JWT_SECRET
JWT_REFRESH_SECRET=$JWT_REFRESH_SECRET
CREDS_KEY=$CREDS_KEY
CREDS_IV=$CREDS_IV
LITELLM_MASTER_KEY=$LITELLM_MASTER_KEY
LITELLM_SALT_KEY=$LITELLM_SALT_KEY
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
MONGO_PASSWORD=$MONGO_PASSWORD
OIDC_PRIVATE_KEY_PEM="$OIDC_PRIVATE_KEY_PEM"
LANGFLOW_SECRET_KEY=$LANGFLOW_SECRET_KEY
STUDIO_SUPERUSER_PASSWORD=$STUDIO_SUPERUSER_PASSWORD
ADMIN_SESSION_SECRET=$ADMIN_SESSION_SECRET
SAMBA_PASSWORD=$SAMBA_PASSWORD
EOF
  local d key
  for d in $(printf '%s' "$DEPARTMENTS" | tr ',' ' '); do
    key="$(printf '%s' "$d" | tr -c 'a-z0-9_\n' '_')"
    printf 'SAMBA_VOLUME_CONFIG_%s="[%s]; path=/shares/%s; valid users = nufi; guest ok = no; read only = no; browseable = yes"\n' "$key" "$d" "$d"
  done
}
if [ "$DRY" = 1 ]; then render_env; else render_env > "$NUFI_BOX_ENV"; ok ".env written"; fi

# ---------- rendered files -----------------------------------------------------
say "Rendering litellm/config.yaml and the drive folders"
if [ "$DRY" = 1 ]; then
  printf '  $ sed -e s|@NUFI_MODEL@|%s| -e s|@INFERENCE_MODEL@|%s| litellm/config.yaml.tmpl > litellm/config.yaml\n' "$NUFI_MODEL" "$INFERENCE_MODEL"
else
  sed -e "s|@NUFI_MODEL@|$NUFI_MODEL|" -e "s|@INFERENCE_MODEL@|$INFERENCE_MODEL|" litellm/config.yaml.tmpl > litellm/config.yaml
fi
for d in $(printf '%s' "$DEPARTMENTS" | tr ',' ' '); do run mkdir -p "$NUFI_DATA_DIR/drives/$d"; done

# ---------- start -----------------------------------------------------------------
COMPOSE="docker compose -f docker-compose.yml"
if [ "$OS" = "Linux" ]; then
  COMPOSE="$COMPOSE -f docker-compose.linux.yml --profile linux"
  has_nvidia && COMPOSE="$COMPOSE -f docker-compose.gpu.yml --profile gpu"
fi
say "Pulling images and starting the stack"
run $COMPOSE pull
run $COMPOSE up -d
if [ "$DRY" = 0 ]; then
  say "Waiting for the app (up to 5 minutes)"
  for i in $(seq 1 60); do
    if docker compose ps --format '{{.Name}} {{.Health}}' | grep -q 'librechat.*healthy'; then break; fi
    sleep 5
  done
fi

# ---------- models ------------------------------------------------------------------
say "Pulling models ($INFERENCE_MODEL, $EMBEDDINGS_MODEL)"
case "$INFERENCE_PROFILE" in
  ollama)        run ollama pull "$INFERENCE_MODEL"; run ollama pull "$EMBEDDINGS_MODEL" ;;
  ollama-docker) run $COMPOSE exec ollama ollama pull "$INFERENCE_MODEL"; run $COMPOSE exec ollama ollama pull "$EMBEDDINGS_MODEL" ;;
  *)             run ollama pull "$EMBEDDINGS_MODEL" ;;
esac

# ---------- people ----------------------------------------------------------------
say "Creating the admin and the ingest service account"
mkuser() { # mkuser email name username password
  run $COMPOSE exec -T librechat npm run create-user -- "$1" "$2" "$3" "$4" --email-verified=true
  run $COMPOSE exec -T mongodb mongo --quiet -u nufi -p "$MONGO_PASSWORD" --authenticationDatabase admin LibreChat \
    --eval "db.users.updateOne({email:'$1'},{\$set:{role:'ADMIN'}})"
}
mkuser "$ADMIN_EMAIL" "Admin" "admin" "$ADMIN_PASSWORD"
mkuser "$INGEST_EMAIL" "Ingest bot" "ingest" "$INGEST_PASSWORD"
run $COMPOSE restart nufi-ingest

# ---------- name, CA, drives ------------------------------------------------------
say "Announcing $BOX_HOST on the LAN and exporting the certificate"
case "$OS" in
  Darwin) run sh -c "nohup dns-sd -P $BOX_NAME _https._tcp local 3080 $BOX_HOST $BOX_IP >/dev/null 2>&1 &"
          say "Drives: enable File Sharing for $NUFI_DATA_DIR/drives (System Settings → General → Sharing → File Sharing), share each department folder"
          for d in $(printf '%s' "$DEPARTMENTS" | tr ',' ' '); do
            if [ "$DRY" = 1 ] || [ -t 0 ]; then
              run sudo sharing -a "$NUFI_DATA_DIR/drives/$d" -S "$d" -s 001 \
                || warn "could not share $d automatically; add it by hand (System Settings → General → Sharing → File Sharing)"
            else
              warn "no interactive terminal; share $NUFI_DATA_DIR/drives/$d by hand (System Settings → General → Sharing → File Sharing)"
            fi
          done ;;
  Linux)  have avahi-publish && run sh -c "nohup avahi-publish -a -R $BOX_HOST $BOX_IP >/dev/null 2>&1 &" || warn "install avahi-utils to announce $BOX_HOST" ;;
esac
run sh -c "docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt '$NUFI_DATA_DIR/nufi-box-ca.crt'"
if [ "$OS" = "Darwin" ] && [ "$DRY" = 0 ]; then
  security add-trusted-cert -r trustRoot -k "$HOME/Library/Keychains/login.keychain-db" "$NUFI_DATA_DIR/nufi-box-ca.crt" 2>/dev/null \
    && ok "box certificate trusted in your login keychain" || warn "trust $NUFI_DATA_DIR/nufi-box-ca.crt by hand (Keychain Access → Always Trust)"
fi
run ln -sf "$BOX_HOME/nufi-box" "$( [ -d /opt/homebrew/bin ] && echo /opt/homebrew/bin || echo /usr/local/bin )/nufi-box"

# ---------- done ---------------------------------------------------------------------
cat <<EOF

  NuFi box "$BOX_NAME" is up.

  Chat:        https://$BOX_HOST:3080     (also https://$BOX_IP:3080)
  Agents:      https://$BOX_HOST:3001/choose
  Console:     https://$BOX_HOST:3001
  Admin panel: https://$BOX_HOST:3002
  Certificate: http://$BOX_HOST/   ← laptops trust it once

  Admin login: $ADMIN_EMAIL / $ADMIN_PASSWORD
  Drives:      $NUFI_DATA_DIR/drives/<department>  → become that department's knowledge

  Day two:     nufi-box status | logs | drive add <name> | ca-cert | doctor
EOF
