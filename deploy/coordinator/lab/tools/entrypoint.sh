#!/bin/sh
# Point this container's resolver at MagicDNS and then get out of the way.
#
# `network_mode: service:node-a` shares node-a's *network* namespace, not its
# mount namespace, so this container has node-a's interfaces and routes but its
# own /etc/resolv.conf — which docker filled in with its embedded resolver.
# 100.100.100.100 is tailscaled's resolver, reachable over the shared
# tailscale0, and it is what makes `nufi.box.lab` a real MagicDNS lookup rather
# than a hosts-file shortcut.
#
# /etc/resolv.conf is a bind mount, so it must be rewritten in place (`cat >`),
# never replaced with a rename.
set -eu

MAGICDNS="${LAB_MAGICDNS:-100.100.100.100}"
SEARCH="${LAB_SEARCH_DOMAIN:-box.lab}"

cat > /etc/resolv.conf <<EOF
nameserver $MAGICDNS
search $SEARCH
options ndots:1 timeout:2 attempts:2
EOF

echo "[tools] resolver -> $MAGICDNS (search $SEARCH)"
touch /run/tools-ready

while :; do sleep 3600; done
