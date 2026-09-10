#!/bin/sh
# The NAT router in front of one lab LAN.
#
#   LAN_SUBNET     the LAN this router serves, e.g. 10.10.0.0/24
#   WAN_SUBNET     the shared "internet" segment, e.g. 172.30.0.0/24
#   WAN_GATEWAY    the WAN bridge's gateway, e.g. 172.30.0.1
#   FORCE_RELAY    1 = drop forwarded UDP except STUN, so no direct WireGuard
#                  path can survive and DERP (TCP 443) has to carry the mesh
#   STUN_PORT      the one UDP port that still gets out (3478)
#
# What it does, in order:
#   * MASQUERADE towards the WAN, and no unsolicited inbound — the "NAT with no
#     port forwarding" half of the hostile case. Every packet a LAN node sends
#     is rewritten to this router's WAN address, and only replies that match a
#     conntrack entry come back.
#   * LEAKGUARD: refuse to forward private destinations upstream, because the
#     docker host would happily route them straight to the other lab LAN.
#   * With FORCE_RELAY=1, everything UDP except STUN is dropped in both
#     directions. WireGuard is UDP, so a direct path becomes impossible while
#     STUN (which only tells a node its own mapped address) and TCP 443 (which
#     carries DERP) still work.
set -eu

log() { printf '[router %s] %s\n' "${LAN_SUBNET:-?}" "$*"; }

: "${LAN_SUBNET:?LAN_SUBNET is required}"
: "${WAN_SUBNET:?WAN_SUBNET is required}"
: "${WAN_GATEWAY:?WAN_GATEWAY is required}"
FORCE_RELAY="${FORCE_RELAY:-0}"
STUN_PORT="${STUN_PORT:-3478}"

# Which interface is which? Docker hands out eth0/eth1 in an order that depends
# on how it sorted the `networks:` map, so match on the address instead of
# trusting the name.
iface_in() {  # iface_in <cidr-prefix-without-mask-bits>
  ip -o -4 addr show | awk -v pfx="$1" '$4 ~ ("^" pfx) { print $2; exit }'
}
WAN_PREFIX="$(printf '%s' "$WAN_SUBNET" | cut -d. -f1-3)."
LAN_PREFIX="$(printf '%s' "$LAN_SUBNET" | cut -d. -f1-3)."

WAN_IF=""
LAN_IF=""
i=0
while [ "$i" -lt 30 ]; do
  WAN_IF="$(iface_in "$WAN_PREFIX")"
  LAN_IF="$(iface_in "$LAN_PREFIX")"
  [ -n "$WAN_IF" ] && [ -n "$LAN_IF" ] && break
  i=$((i + 1))
  sleep 1
done
[ -n "$WAN_IF" ] || { log "no interface on $WAN_SUBNET"; exit 1; }
[ -n "$LAN_IF" ] || { log "no interface on $LAN_SUBNET"; exit 1; }
log "wan=$WAN_IF ($WAN_SUBNET) lan=$LAN_IF ($LAN_SUBNET) force_relay=$FORCE_RELAY"

# Docker picks a default route for a multi-homed container by its own rules;
# pin it to the WAN side so forwarded traffic leaves the way we expect.
ip route replace default via "$WAN_GATEWAY" dev "$WAN_IF" 2>/dev/null \
  || { ip route del default 2>/dev/null || true; ip route add default via "$WAN_GATEWAY" dev "$WAN_IF"; }

iptables -t nat -A POSTROUTING -s "$LAN_SUBNET" -o "$WAN_IF" -j MASQUERADE
log "MASQUERADE $LAN_SUBNET out $WAN_IF"

# No unsolicited inbound on the WAN address. A real router drops it, and here
# it is also load-bearing: without this the peer's hole-punch packets, which
# arrive addressed to this router's own WAN ip:port before the NAT binding for
# them exists, are delivered to INPUT and conntrack records them as a brand new
# connection *to the router*. That entry's reply tuple is exactly the one the
# LAN node needs a moment later, so nf_nat finds the port taken and hands the
# node a different external port (observed live: 52872 -> 48955). The NAT then
# behaves as symmetric, the two mapped addresses never line up and no direct
# path can ever form. Dropping in INPUT stops the entry being confirmed and the
# mapping stays endpoint-independent.
iptables -A INPUT -i "$WAN_IF" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -i "$WAN_IF" -j DROP
log "INPUT on $WAN_IF: established only"

# No route to anyone else's private network. An ISP does not carry RFC1918
# traffic, and here the docker host would: it has an interface on every lab
# bridge, so a packet this router hands upstream for 10.20.0.0/24 is delivered
# straight to the far LAN. Left open, the two nodes find each other's *LAN*
# addresses and "direct" means "they were never really behind NAT" — observed
# live as `pong ... via 10.20.0.3:52004`. RETURN for the WAN segment itself so
# the rest of the chain (--force-relay's UDP block) still sees those packets.
iptables -N LEAKGUARD
iptables -A LEAKGUARD -d "$WAN_SUBNET" -j RETURN
for private in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10 169.254.0.0/16; do
  iptables -A LEAKGUARD -d "$private" -j DROP
done
iptables -A FORWARD -i "$LAN_IF" -o "$WAN_IF" -j LEAKGUARD
log "LEAKGUARD: no forwarding to private networks other than $WAN_SUBNET"

if [ "$FORCE_RELAY" = "1" ]; then
  # Outbound: only STUN leaves. Inbound: only STUN replies come back. Anything
  # else UDP — WireGuard's 41641, DNS, everything — is dropped, so the only
  # path left between the two LANs is DERP over TCP 443.
  iptables -A FORWARD -i "$LAN_IF" -o "$WAN_IF" -p udp ! --dport "$STUN_PORT" -j DROP
  iptables -A FORWARD -i "$WAN_IF" -o "$LAN_IF" -p udp ! --sport "$STUN_PORT" -j DROP
  log "FORCE_RELAY: forwarded UDP dropped except port $STUN_PORT"
fi

touch /run/router-ready
log "ready"

# Nothing to serve; the container exists to hold the namespace and its rules.
while :; do sleep 3600; done
