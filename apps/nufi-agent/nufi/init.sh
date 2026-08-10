#!/usr/bin/env bash
#
# Safe stand-in for upstream's `make init`.
#
# `make init` (Makefile:84-89) runs `install_backend`, `install_frontend`,
# then `uvx pre-commit install`. That last step is safe in a standalone
# langflow checkout, where apps/nufi-agent/.pre-commit-config.yaml IS the
# repo root's config. It is not safe here: this monorepo has exactly one
# shared .git/hooks/ directory for every app -- apps/chat, apps/agents,
# apps/console, apps/docs, deploy/*, all of it -- and
# .pre-commit-config.yaml's local hooks use `language: system`
# (.pre-commit-config.yaml:18-19, `entry: uv run ruff check`), which
# pre-commit always runs from the GIT ROOT, not from wherever the config
# file lives. The monorepo root has no `uv` project at all, so `uv run
# ruff check` would fail immediately there. Installed exactly as
# upstream's own `make init` does it, this would plausibly break every
# commit in the entire monorepo, not just ones touching
# apps/nufi-agent -- until someone works out the cause is a stray
# .git/hooks/pre-commit and deletes it by hand. Full trace in
# nufi/DEVELOPING.md, under "Skip make init's pre-commit step in this
# monorepo".
#
# This script runs the same two install targets `make init` runs and
# stops there. It does not call `uvx pre-commit install`, and it does not
# write anything to .git/hooks/ itself.
#
# Usage: apps/nufi-agent/nufi/init.sh
# Exits 0 once both installs succeed. set -euo pipefail means a failed
# `make install_backend` stops the script before `install_frontend` runs,
# same as `make init`'s own dependency chain would.

set -euo pipefail

cd "$(dirname "$0")/.."   # apps/nufi-agent

echo "Installing backend dependencies (make install_backend)..."
make install_backend

echo "Installing frontend dependencies (make install_frontend)..."
make install_frontend

cat <<'MSG'

OK -- backend and frontend dependencies installed.

This deliberately did NOT run `uvx pre-commit install`, the third step of
upstream's `make init`. See this script's own header, or
nufi/DEVELOPING.md, for why that command is unsafe in this monorepo.
Nothing was written to .git/hooks/ by this script.
MSG
