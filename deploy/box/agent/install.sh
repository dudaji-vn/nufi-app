#!/bin/bash
# Install the NufiBox Agent (run as root). One package — no separate Tailscale.
# Optionally enroll straight away:
#   sudo ./install.sh enroll --server <url> --auth-key <key> [--ca <file>] [--hostname <name>]
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"

install -m 0755 "$HERE/bin/nufibox-tailscaled" /usr/local/bin/nufibox-tailscaled
install -m 0755 "$HERE/bin/nufibox-tailscale"  /usr/local/bin/nufibox-tailscale
install -m 0755 "$HERE/bin/nufibox-agent"      /usr/local/bin/nufibox-agent
install -m 0644 "$HERE/nufibox-agent.service"  /etc/systemd/system/nufibox-agent.service
systemctl daemon-reload
systemctl enable --now nufibox-agent
echo "NufiBox Agent installed (nufibox-agent.service running)."

if [ "${1:-}" = "enroll" ]; then shift; nufibox-agent enroll "$@"; fi
