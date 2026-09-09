#!/bin/bash
# install-box.sh — bring up a NuFi box on this machine.
#
#   curl -fsSL https://get.nufi.me/box | bash            # later: hosted
#   ./install-box.sh [--yes] [--dry-run] [--src DIR]      # from a checkout
#              [--no-pull] [--emulate-amd64] [--no-trust]
#              [--registry HOST[:PORT][/path]]
#              [--mesh URL --auth-key KEY [--mesh-api-key KEY]]
#
# Asks four questions (box name, admin email, departments, inference profile),
# generates every secret here, renders the LiteLLM config, starts the stack,
# pulls the models, creates the admin and the ingest service account, and prints
# the URLs. Re-running keeps .env and the answers. bash 3.2 compatible.
#
#   --no-pull        do not `docker compose pull`; use what is already local
#   --emulate-amd64  run the amd64-only images under emulation (Apple Silicon)
#   --no-trust       do not touch the login keychain; print the trust step
#   --registry HOST[:PORT][/path]
#                    pull NuFi images from here instead of ghcr.io/dudaji-vn —
#                    a LAN registry for a box without GitHub access. Marked
#                    insecure automatically when it looks like host:port or a
#                    bare IP (Linux: /etc/docker/daemon.json; macOS: prints
#                    the Docker Desktop step).
#   --mesh URL       join the mesh coordinator at URL so this box can be
#                    reached from outside the office (deploy/coordinator).
#   --auth-key KEY   the single-use pre-auth key (tag:box) that coordinator
#                    minted for this box; required with --mesh.
#   --mesh-api-key KEY
#                    the coordinator's headscale API key, so `nufi-box
#                    invite | members | revoke` can talk to it. Optional:
#                    without it the box joins but cannot invite anyone.
#
# NUFI_BOX_COMPOSE_EXTRA — space-separated extra compose files to layer last,
# for a machine that needs a site-local tweak (a port map when something else
# already holds 3080, a mount, a resource cap) without editing what ships.
set -euo pipefail

# ---------- tiny helpers -----------------------------------------------------
say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m !!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m xx\033[0m %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY" = 1 ]; then printf '  $ %s\n' "$*"; else "$@"; fi; }

YES=0; DRY=0; SRC=""; NO_PULL=0; NO_TRUST=0
# The flags this run was given, requoted, so the docker-group re-exec in the
# Linux prerequisites below can repeat this command exactly. Captured here
# because the loop that follows consumes "$@".
NUFI_BOX_FLAGS=""
for _a in "$@"; do NUFI_BOX_FLAGS="$NUFI_BOX_FLAGS $(printf '%q' "$_a")"; done
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1 ;;
    --dry-run) DRY=1 ;;
    --no-pull) NO_PULL=1 ;;
    --no-trust) NO_TRUST=1 ;;
    --emulate-amd64) NUFI_EMULATE_AMD64=1 ;;
    # `shift` on a bare --src would fail under `set -e` and exit 1 with no word
    # of explanation, so check for the value before consuming it.
    --src) [ $# -ge 2 ] || die "--src needs a directory"; SRC="$2"; shift ;;
    --src=*) SRC="${1#--src=}"; [ -n "$SRC" ] || die "--src needs a directory" ;;
    --registry) [ $# -ge 2 ] || die "--registry needs a value"; NUFI_REGISTRY="$2"; shift ;;
    --registry=*) NUFI_REGISTRY="${1#--registry=}"; [ -n "$NUFI_REGISTRY" ] || die "--registry needs a value" ;;
    --mesh) [ $# -ge 2 ] || die "--mesh needs a coordinator URL"; MESH_SERVER_URL="$2"; shift ;;
    --mesh=*) MESH_SERVER_URL="${1#--mesh=}"; [ -n "$MESH_SERVER_URL" ] || die "--mesh needs a coordinator URL" ;;
    --auth-key) [ $# -ge 2 ] || die "--auth-key needs a value"; MESH_AUTH_KEY="$2"; shift ;;
    --auth-key=*) MESH_AUTH_KEY="${1#--auth-key=}"; [ -n "$MESH_AUTH_KEY" ] || die "--auth-key needs a value" ;;
    --mesh-api-key) [ $# -ge 2 ] || die "--mesh-api-key needs a value"; MESH_API_KEY="$2"; shift ;;
    --mesh-api-key=*) MESH_API_KEY="${1#--mesh-api-key=}"; [ -n "$MESH_API_KEY" ] || die "--mesh-api-key needs a value" ;;
    -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
  esac
  shift
done
[ "${NUFI_BOX_DRY_RUN:-0}" = "1" ] && DRY=1
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
  # A group added with usermod only applies to new logins, so a shell older
  # than the membership cannot open /var/run/docker.sock even though the user
  # is a member: the shell that just installed Docker here, or any session
  # that was already open when someone ran usermod. `docker compose version`
  # never touches the daemon and passes anyway, so the install used to run on
  # and die minutes later at `docker compose pull` with Docker's own
  # "permission denied while trying to connect to the docker API". `id -nG
  # <user>` reads the group database rather than this process's credentials,
  # so it sees the membership the session is missing; `sg` starts a shell that
  # has it, and keeps the environment, so every answer the caller passed on
  # the command line survives. Once only, then say what to do.
  if [ "$OS" = "Linux" ] && ! docker info >/dev/null 2>&1 \
     && [ "${NUFI_BOX_REEXEC:-0}" != "1" ] && have sg \
     && id -nG "$USER" 2>/dev/null | tr ' ' '\n' | grep -qx docker; then
    say "Re-running inside the new docker group"
    export NUFI_BOX_REEXEC=1
    exec sg docker -c "$(printf '%q' "$HERE/${0##*/}")$NUFI_BOX_FLAGS"
  fi
  docker compose version >/dev/null 2>&1 || die "docker compose v2 is required"
  # Neither `docker compose version` nor `docker --version` opens the socket,
  # so without this the first thing to notice an unreachable daemon is the
  # image pull, minutes in, in Docker's own words.
  docker info >/dev/null 2>&1 || die "cannot reach the Docker daemon as $USER: start it (sudo systemctl start docker), or join the docker group and open a new shell (sudo usermod -aG docker $USER; newgrp docker)"
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
REUSE_VARS="BOX_NAME ADMIN_EMAIL DEPARTMENTS INFERENCE_PROFILE INFERENCE_MODEL INFERENCE_BASE_URL INFERENCE_API_KEY OLLAMA_BASE_URL EMBEDDINGS_MODEL NUFI_DATA_DIR NUFI_EMULATE_AMD64 NUFI_REGISTRY MESH_SERVER_URL MESH_AUTH_KEY MESH_API_KEY MESH_CA_FILE"
# BOX_MESH_IP/BOX_MESH_HOST are `nufi-box mesh up`'s answers, not the
# operator's, and they are in the join files already handed to members —
# a re-install must not blank them. They are reused but never asked for.
REUSE_VARS="$REUSE_VARS BOX_MESH_IP BOX_MESH_HOST"
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
NUFI_EMULATE_AMD64="${NUFI_EMULATE_AMD64:-0}"
NUFI_REGISTRY="${NUFI_REGISTRY:-ghcr.io/dudaji-vn}"
MESH_SERVER_URL="${MESH_SERVER_URL:-}"
MESH_AUTH_KEY="${MESH_AUTH_KEY:-}"
MESH_API_KEY="${MESH_API_KEY:-}"
MESH_CA_FILE="${MESH_CA_FILE:-/etc/ssl/certs/ca-certificates.crt}"
BOX_MESH_IP="${BOX_MESH_IP:-}"
BOX_MESH_HOST="${BOX_MESH_HOST:-}"
# One without the other is always a mistake, and the failure it causes is slow:
# the container comes up, tailscaled has nothing to log in with, and the box
# looks joined until somebody tries to reach it from home.
if [ -n "$MESH_SERVER_URL" ] && [ -z "$MESH_AUTH_KEY" ]; then
  die "--mesh needs --auth-key: ask the coordinator for this box's pre-auth key (headscale preauthkeys create --user box --tags tag:box)"
fi
if [ -z "$MESH_SERVER_URL" ] && [ -n "$MESH_AUTH_KEY" ]; then
  die "--auth-key without --mesh: name the coordinator too, e.g. --mesh https://mesh.nufi.me"
fi
# --registry exists for a box that cannot reach ghcr.io. Two of the third-party
# images live on ghcr.io as well (the RAG API and Samba), so pointing only the
# NuFi images at the mirror leaves an install that still cannot finish — this
# is what a blank-VM install proved, dying three times on the RAG image's blob
# store. `make registry-push` mirrors those two next to the NuFi six; name them
# there unless the caller (or an existing .env) already named an image.
if [ "$NUFI_REGISTRY" != "ghcr.io/dudaji-vn" ]; then
  NUFI_RAG_IMAGE="${NUFI_RAG_IMAGE:-$NUFI_REGISTRY/librechat-rag-api-dev-lite:${NUFI_RAG_TAG:-main}}"
  NUFI_SAMBA_IMAGE="${NUFI_SAMBA_IMAGE:-$NUFI_REGISTRY/samba:${NUFI_SAMBA_TAG:-main}}"
fi

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

# ---------- who the department drives belong to ---------------------------------
# The Samba account members log in as and the person who installed the box have
# to be the same uid, or exactly one of them can write to a department drive.
# This installer creates data/drives as whoever runs it; the container's `nufi`
# account used to be pinned to uid 1000, so on any box whose admin is not
# uid 1000 the account was neither the owner nor in the group of a 775
# directory, fell through to `other` (r-x), and every `smbclient put` came back
# NT_STATUS_ACCESS_DENIED. Read yes, write no — the half of the promise a
# member actually uses from home.
#
# Rendered rather than assumed, and rendered from `id`, so a box installed by
# the machine's second user (1001), by a service account, or by root works the
# same as one installed by its first user.
NUFI_SMB_UID="${NUFI_BOX_FAKE_UID:-$(id -u)}"
NUFI_SMB_GID="${NUFI_BOX_FAKE_GID:-$(id -g)}"
if [ "$NUFI_SMB_UID" = "0" ]; then
  # A root install cannot hand the share root's uid: the Samba image only
  # honours `UID_nufi` when it is greater than zero (`[ "$ACCOUNT_UID" -gt 0 ]`
  # in its entrypoint), and an SMB account running as root would own every
  # right on whatever directory it is given. Use the conventional first-user
  # id and give the drives to it below instead.
  NUFI_SMB_UID=1000
  NUFI_SMB_GID=1000
fi

# ---------- .env ----------------------------------------------------------------
say "Writing .env"
sec() { # sec VAR generator — keep an existing non-placeholder value
  local var="$1" gen="$2" cur; eval "cur=\${$var:-}"
  case "$cur" in ""|*replace-me*) eval "$var=\"\$($gen)\"" ;; esac
}
sec JWT_SECRET "gen_hex 32"; sec JWT_REFRESH_SECRET "gen_hex 32"; sec CREDS_KEY "gen_hex 32"; sec CREDS_IV "gen_hex 16"
sec LITELLM_MASTER_KEY "printf sk-%s \$(gen_hex 32)"; sec LITELLM_SALT_KEY "gen_hex 32"
sec POSTGRES_PASSWORD "gen_hex 16"; sec MONGO_PASSWORD "gen_hex 16"
sec ADMIN_PASSWORD "gen_hex 8"
sec LANGFLOW_SECRET_KEY "gen_fernet"; sec STUDIO_SUPERUSER_PASSWORD "gen_hex 12"
sec ADMIN_SESSION_SECRET "gen_hex 32"; sec SAMBA_PASSWORD "gen_hex 8"
# The ingest daemon runs as the admin by default. Whoever creates a department
# team owns it, and the daemon is the only thing that ever creates one — so if
# it runs as its own bot account, the admin logs into a fresh box and sees no
# teams and no agents at all, with no way to join them (team membership only
# goes through an invite the invitee accepts). Running it as the admin makes
# the admin the author of every department team and agent, free to invite
# colleagues from the app's Teams UI. Set BOTH INGEST_EMAIL and INGEST_PASSWORD
# to run it as a separate service account instead.
INGEST_EMAIL="${INGEST_EMAIL:-$ADMIN_EMAIL}"
if [ "$INGEST_EMAIL" = "$ADMIN_EMAIL" ]; then INGEST_PASSWORD="$ADMIN_PASSWORD"
else sec INGEST_PASSWORD "gen_hex 16"; fi
# Compose does NOT expand \n inside a double-quoted .env value (verified with
# `docker compose config` on 2.39.2): X="a\nb" renders as the four characters
# a\nb, while a real multi-line double-quoted value renders with a real
# newline. So the PEM has to be stored with real newlines — bash writes them
# verbatim inside the double quotes in render_env below, and `set -a; . .env`
# on a re-run reads them back intact. A box installed with the old installer
# has the broken one-line form on disk (a literal backslash-n, not a real
# newline); heal it by regenerating rather than leaving it broken forever.
case "${OIDC_PRIVATE_KEY_PEM:-}" in
  ""|replace-me)
    OIDC_PRIVATE_KEY_PEM="$(openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 2>/dev/null)" ;;
  *'\n'*)
    warn "regenerated the console signing key (the old one was stored on one line); Studio sessions will need a fresh sign-in"
    OIDC_PRIVATE_KEY_PEM="$(openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 2>/dev/null)" ;;
esac
NVIDIA_VISIBLE_DEVICES=""
if [ "$OS" = "Linux" ] && has_nvidia; then NVIDIA_VISIBLE_DEVICES=all; fi

render_env() {
  cat <<EOF
BOX_NAME=$BOX_NAME
BOX_HOST=$BOX_HOST
BOX_IP=$BOX_IP
NUFI_DATA_DIR=$NUFI_DATA_DIR
NUFI_SMB_UID=$NUFI_SMB_UID
NUFI_SMB_GID=$NUFI_SMB_GID
NUFI_REGISTRY=$NUFI_REGISTRY
NUFI_CHAT_TAG=${NUFI_CHAT_TAG:-main}
NUFI_CONSOLE_TAG=${NUFI_CONSOLE_TAG:-main}
NUFI_ADMIN_TAG=${NUFI_ADMIN_TAG:-main}
NUFI_STUDIO_TAG=${NUFI_STUDIO_TAG:-box-main}
NUFI_LITELLM_TAG=${NUFI_LITELLM_TAG:-main}
NUFI_INGEST_TAG=${NUFI_INGEST_TAG:-main}
NUFI_EMULATE_AMD64=$NUFI_EMULATE_AMD64
NUFI_RAG_IMAGE=${NUFI_RAG_IMAGE:-ghcr.io/danny-avila/librechat-rag-api-dev-lite@sha256:f9f34c8ed6884b0ff9b17387e6174fed737dba29f21622ecb75604d82bc47bf8}
NUFI_SAMBA_IMAGE=${NUFI_SAMBA_IMAGE:-ghcr.io/servercontainers/samba:a3.24.1-s4.23.8-r0}
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
MESH_SERVER_URL=$MESH_SERVER_URL
MESH_AUTH_KEY=$MESH_AUTH_KEY
MESH_API_KEY=$MESH_API_KEY
MESH_CA_FILE=$MESH_CA_FILE
BOX_MESH_IP=$BOX_MESH_IP
BOX_MESH_HOST=$BOX_MESH_HOST
EOF
  local d key
  for d in $(printf '%s' "$DEPARTMENTS" | tr ',' ' '); do
    key="$(printf '%s' "$d" | tr -c 'a-z0-9_\n' '_')"
    printf 'SAMBA_VOLUME_CONFIG_%s="[%s]; path=/shares/%s; valid users = nufi; guest ok = no; read only = no; browseable = yes"\n' "$key" "$d" "$d"
  done
}
if [ "$DRY" = 1 ]; then render_env; else render_env > "$NUFI_BOX_ENV"; ok ".env written"; fi

# ---------- registry trust ---------------------------------------------------
# A LAN registry (`--registry 192.168.1.26:5000`) has no TLS certificate, so
# Docker refuses to pull from it until it is explicitly marked insecure. A
# registry reached over HTTPS (the default ghcr.io/dudaji-vn, or a private
# registry that does have a certificate) never needs this.
looks_like_insecure_registry() {
  case "$1" in
    https://*) return 1 ;;
  esac
  case "$1" in
    *:[0-9]*) return 0 ;;
  esac
  case "$1" in
    [0-9]*.[0-9]*.[0-9]*.[0-9]*) return 0 ;;
  esac
  return 1
}
if looks_like_insecure_registry "$NUFI_REGISTRY"; then
  case "$OS" in
    Darwin)
      say "Docker Desktop must trust $NUFI_REGISTRY as an insecure registry"
      printf '  Docker Desktop -> Settings -> Docker Engine -> add "%s" to "insecure-registries", then Apply & Restart.\n' "$NUFI_REGISTRY"
      ;;
    Linux)
      DAEMON_JSON=/etc/docker/daemon.json
      if [ "$DRY" = 1 ]; then
        say "Would allow the insecure registry $NUFI_REGISTRY"
        printf '  $ python3 - <<PY   # write or merge into %s\n{"insecure-registries": ["%s"]}\nPY\n' "$DAEMON_JSON" "$NUFI_REGISTRY"
        printf '  $ sudo systemctl restart docker\n'
      else
        say "Allowing the insecure registry $NUFI_REGISTRY in $DAEMON_JSON"
        sudo python3 - "$NUFI_REGISTRY" "$DAEMON_JSON" <<'PYEOF'
import json
import sys

registry, path = sys.argv[1], sys.argv[2]
try:
    with open(path) as f:
        cfg = json.load(f)
except (FileNotFoundError, ValueError):
    cfg = {}
regs = cfg.setdefault("insecure-registries", [])
if registry not in regs:
    regs.append(registry)
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PYEOF
        sudo systemctl restart docker || warn "could not restart docker; restart it by hand to pick up $DAEMON_JSON"
        ok "insecure registry $NUFI_REGISTRY written to $DAEMON_JSON"
      fi
      ;;
  esac
fi

# ---------- rendered files -----------------------------------------------------
say "Rendering litellm/config.yaml and the drive folders"
if [ "$DRY" = 1 ]; then
  printf '  $ sed -e s|@NUFI_MODEL@|%s| -e s|@INFERENCE_MODEL@|%s| litellm/config.yaml.tmpl > litellm/config.yaml\n' "$NUFI_MODEL" "$INFERENCE_MODEL"
else
  sed -e "s|@NUFI_MODEL@|$NUFI_MODEL|" -e "s|@INFERENCE_MODEL@|$INFERENCE_MODEL|" litellm/config.yaml.tmpl > litellm/config.yaml
fi
for d in $(printf '%s' "$DEPARTMENTS" | tr ',' ' '); do run mkdir -p "$NUFI_DATA_DIR/drives/$d"; done
# …and owned by the uid the Samba account runs as, or a member cannot write to
# them (see NUFI_SMB_UID above). A drive this run just created already is; this
# is for the two cases where it is not — a box installed as root, whose drives
# are root's, and a box upgraded from the release that pinned the account to
# 1000 while the drives belonged to someone else.
dir_uid() { stat -c '%u' "$1" 2>/dev/null || stat -f '%u' "$1" 2>/dev/null || echo ""; }
for d in $(printf '%s' "$DEPARTMENTS" | tr ',' ' '); do
  _drive="$NUFI_DATA_DIR/drives/$d"
  if [ "$DRY" = 1 ]; then
    printf '  $ chown -R %s:%s %s   # unless it is already\n' "$NUFI_SMB_UID" "$NUFI_SMB_GID" "$_drive"
    continue
  fi
  [ -d "$_drive" ] || continue
  _cur="$(dir_uid "$_drive")"
  if [ "$_cur" != "$NUFI_SMB_UID" ]; then
    chown -R "$NUFI_SMB_UID:$NUFI_SMB_GID" "$_drive" 2>/dev/null \
      || warn "$_drive belongs to uid $_cur, not $NUFI_SMB_UID — members will get NT_STATUS_ACCESS_DENIED writing to it; run: sudo chown -R $NUFI_SMB_UID:$NUFI_SMB_GID $_drive"
  fi
done
# The Caddyfile imports caddy/mesh*.caddy. A box that never joins a mesh
# still gets the empty template, so the import always has a file to read and
# `nufi-box mesh up` only ever overwrites one.
if [ "$DRY" = 1 ]; then
  printf '  $ cp caddy/mesh.caddy.empty caddy/mesh.caddy   # unless it exists\n'
elif [ ! -f caddy/mesh.caddy ]; then
  cp caddy/mesh.caddy.empty caddy/mesh.caddy
fi

# ---------- start -----------------------------------------------------------------
COMPOSE="docker compose -f docker-compose.yml"
if [ "$NUFI_EMULATE_AMD64" = "1" ]; then COMPOSE="$COMPOSE -f docker-compose.emulate.yml"; fi
if [ "$OS" = "Linux" ]; then
  COMPOSE="$COMPOSE -f docker-compose.linux.yml --profile linux"
  has_nvidia && COMPOSE="$COMPOSE -f docker-compose.gpu.yml --profile gpu"
  # The mesh node comes up with the rest of the stack, so one `pull` fetches
  # its image too. macOS gets no container: Docker Desktop's host network is
  # the Linux VM's, so it could never give the Mac a mesh address.
  [ -n "$MESH_SERVER_URL" ] && COMPOSE="$COMPOSE -f docker-compose.mesh.yml --profile mesh"
fi
for f in ${NUFI_BOX_COMPOSE_EXTRA:-}; do
  [ -f "$f" ] || die "NUFI_BOX_COMPOSE_EXTRA: no such file: $f"
  COMPOSE="$COMPOSE -f $f"
done
if [ "$NO_PULL" = 1 ]; then
  say "Starting the stack (--no-pull: using the images already on this machine)"
else
  say "Pulling images and starting the stack"
  # A dozen images over someone else's network: one flaky blob ends the whole
  # install under `set -e`. A TLS handshake timeout to ghcr.io killed a
  # blank-VM install two minutes in, with every other image already down.
  # A pull is resumable and idempotent, so try the whole thing three times
  # before giving up on it.
  pull_ok=0
  for attempt in 1 2 3; do
    if run $COMPOSE pull; then pull_ok=1; break; fi
    warn "image pull attempt $attempt of 3 failed; retrying in 5s"
    sleep 5
  done
  [ "$pull_ok" = 1 ] || die "could not pull the images after 3 attempts; check the network (and, for a --registry box, that the registry is up) and re-run"
fi
run $COMPOSE up -d
if [ "$DRY" = 0 ]; then
  say "Waiting for the app (up to 5 minutes)"
  for i in $(seq 1 60); do
    if docker compose ps --format '{{.Name}} {{.Health}}' | grep -q 'librechat.*healthy'; then break; fi
    sleep 5
  done
fi

# ---------- console signing key -----------------------------------------------------
# The console's OIDC signing key is only usable once it renders as real PEM
# (see the OIDC_PRIVATE_KEY_PEM handling above) — probe the endpoint that
# breaks first when it isn't: Studio's SSO handoff verifies tokens against it.
say "Checking the console's JWKS endpoint"
if [ "$DRY" = 1 ]; then
  printf '  $ %s\n' "curl -fsk https://localhost:3001/.well-known/jwks.json"
else
  jwks_ok=0
  for i in $(seq 1 12); do
    curl -fsk "https://localhost:3001/.well-known/jwks.json" >/dev/null 2>&1 && { jwks_ok=1; break; }
    sleep 5
  done
  if [ "$jwks_ok" = 1 ]; then
    ok "console JWKS is serving"
  else
    warn "console JWKS (https://localhost:3001/.well-known/jwks.json) never came up; check: nufi-box logs console"
  fi
fi

# ---------- models ------------------------------------------------------------------
say "Pulling models ($INFERENCE_MODEL, $EMBEDDINGS_MODEL)"
# A model pull is a multi-gigabyte download over someone else's network. Under
# `set -e` one failed pull ends the installer here — before the accounts, the
# CA export, the symlink and the banner — leaving a box that is actually up and
# an operator with no idea what to do next. Warn with the exact command to
# repeat instead, and carry on.
case "$INFERENCE_PROFILE" in
  ollama)
    run ollama pull "$INFERENCE_MODEL" || warn "could not pull $INFERENCE_MODEL; retry with: ollama pull $INFERENCE_MODEL"
    run ollama pull "$EMBEDDINGS_MODEL" || warn "could not pull $EMBEDDINGS_MODEL; retry with: ollama pull $EMBEDDINGS_MODEL" ;;
  ollama-docker)
    run $COMPOSE exec ollama ollama pull "$INFERENCE_MODEL" || warn "could not pull $INFERENCE_MODEL; retry with: $COMPOSE exec ollama ollama pull $INFERENCE_MODEL"
    run $COMPOSE exec ollama ollama pull "$EMBEDDINGS_MODEL" || warn "could not pull $EMBEDDINGS_MODEL; retry with: $COMPOSE exec ollama ollama pull $EMBEDDINGS_MODEL" ;;
  *)
    run ollama pull "$EMBEDDINGS_MODEL" || warn "could not pull $EMBEDDINGS_MODEL; retry with: ollama pull $EMBEDDINGS_MODEL" ;;
esac

# ---------- people ----------------------------------------------------------------
say "Creating the admin and the ingest service account"
mkuser() { # mkuser email name username password
  # create-user exits 1 when the address is already registered
  # (apps/chat/config/create-user.js → silentExit(1)), so on every re-run of
  # this installer `set -e` killed the script right here: no CA export, no
  # symlink, no `restart nufi-ingest`, no banner — the second run of a command
  # documented as safe to repeat did strictly less than the first. The role
  # update below is an idempotent updateOne and runs either way.
  run $COMPOSE exec -T librechat npm run create-user -- "$1" "$2" "$3" "$4" --email-verified=true \
    || warn "$1 already exists; keeping it"
  run $COMPOSE exec -T mongodb mongo --quiet -u nufi -p "$MONGO_PASSWORD" --authenticationDatabase admin LibreChat \
    --eval "db.users.updateOne({email:'$1'},{\$set:{role:'ADMIN'}})"
}
mkuser "$ADMIN_EMAIL" "Admin" "admin" "$ADMIN_PASSWORD"
if [ "$INGEST_EMAIL" != "$ADMIN_EMAIL" ]; then
  mkuser "$INGEST_EMAIL" "Ingest bot" "ingest" "$INGEST_PASSWORD"
else
  ok "the ingest daemon runs as $ADMIN_EMAIL; no separate bot account"
fi
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
if [ "$OS" = "Darwin" ]; then
  if [ "$NO_TRUST" = 1 ]; then
    say "Not touching the login keychain (--no-trust). Trust the box CA by hand:"
    printf '    security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db %s\n' \
      "$NUFI_DATA_DIR/nufi-box-ca.crt"
  elif [ "$DRY" = 1 ]; then
    printf '  $ security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db %s\n' \
      "$NUFI_DATA_DIR/nufi-box-ca.crt"
  else
    security add-trusted-cert -r trustRoot -k "$HOME/Library/Keychains/login.keychain-db" "$NUFI_DATA_DIR/nufi-box-ca.crt" 2>/dev/null \
      && ok "box certificate trusted in your login keychain" || warn "trust $NUFI_DATA_DIR/nufi-box-ca.crt by hand (Keychain Access → Always Trust)"
  fi
fi
# Homebrew's bin is the user's own on macOS, but /usr/local/bin on Ubuntu is
# root-owned: for the non-root user this installer otherwise supports all the
# way through, `ln -sf` fails and `set -e` swallows the banner that says the
# box is up. The link is a convenience; the box works without it.
LINK_DIR="$( [ -d /opt/homebrew/bin ] && echo /opt/homebrew/bin || echo /usr/local/bin )"
run ln -sf "$BOX_HOME/nufi-box" "$LINK_DIR/nufi-box" \
  || warn "could not link nufi-box into $LINK_DIR; add $BOX_HOME to your PATH or run: sudo ln -sf $BOX_HOME/nufi-box $LINK_DIR/nufi-box"

# ---------- the department routines ---------------------------------------------------
# The four routines the box is bought for, as flows a person can open and edit:
# they read the department drives this installer just created, mounted
# read-only into Studio. Delegated to `nufi-box flows install` for the same
# reason as the mesh below — re-installing them is day-two work too, and two
# copies of "mint a key, then build" would drift. It mints the box's own Studio
# API key on the first run and writes it to .env as STUDIO_API_KEY.
#
# A warning, not a die: a box whose routines did not install is still a box
# with chat, drives and Studio, and the operator can repeat the one command.
say "Installing the department routines into Studio"
if [ "$DRY" = 1 ]; then
  _flows_env="$(mktemp)"
  render_env > "$_flows_env"
  NUFI_BOX_DRY_RUN=1 NUFI_BOX_FAKE_OS="$OS" NUFI_BOX_ENV="$_flows_env" "$BOX_HOME/nufi-box" flows install || true
  rm -f "$_flows_env"
else
  "$BOX_HOME/nufi-box" flows install || warn "the routines are not in Studio yet; run: nufi-box flows install"
fi

# ---------- the mesh ------------------------------------------------------------------
# Delegate to `nufi-box mesh up` rather than repeating it: waiting for the
# address, writing BOX_MESH_*, rendering caddy/mesh.caddy and reloading Caddy
# is day-two work too, and two copies of it would drift. The dry run points
# nufi-box at a throwaway .env rendered from these same answers, so the plan
# it prints is the one the real run executes.
if [ -n "$MESH_SERVER_URL" ]; then
  say "Joining the mesh at $MESH_SERVER_URL"
  if [ "$DRY" = 1 ]; then
    _mesh_env="$(mktemp)"
    render_env > "$_mesh_env"
    NUFI_BOX_DRY_RUN=1 NUFI_BOX_FAKE_OS="$OS" NUFI_BOX_ENV="$_mesh_env" "$BOX_HOME/nufi-box" mesh up || true
    rm -f "$_mesh_env"
  else
    "$BOX_HOME/nufi-box" mesh up || warn "the box is up but not on the mesh yet; run: nufi-box mesh up"
  fi
fi

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

  Routines:    https://$BOX_HOST:7860  → sign in as $ADMIN_EMAIL with the
               Studio password in .env (STUDIO_SUPERUSER_PASSWORD). The four
               department routines are there; members who arrive through the
               app get their own empty Studio.

  Day two:     nufi-box status | logs | drive add <name> | ca-cert | doctor
               nufi-box flows install | flows list
EOF
if [ -n "$MESH_SERVER_URL" ]; then
  cat <<EOF
  From home:   nufi-box mesh status         (this box on the mesh)
               nufi-box invite <name>       (a join file for one laptop)
EOF
fi
