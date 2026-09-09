# A home router: one foot on the "WAN", one on an internal LAN, MASQUERADE in
# between and no port forwarding. iptables-nft is what alpine's `iptables`
# package installs; the kernel is Docker Desktop's Linux VM, shared with every
# other container, so the rules below are confined to this container's own
# network namespace (NET_ADMIN, not privileged).
FROM alpine:3.22.1

RUN apk add --no-cache iptables iproute2

COPY entrypoint.sh /entrypoint.sh

# The healthcheck ("/run/router-ready exists") is declared in
# lab/docker-compose.yml, next to the rest of the service definition.
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
