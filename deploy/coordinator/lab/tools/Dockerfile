# The member's laptop, minus Tailscale. This container shares node-a's network
# namespace, so it sees node-a's tailscale0 interface, mesh address and routes
# — it is the "what the human actually types" end of the lab.
#
# It exists because the official tailscale image carries no curl and no
# smbclient (confirmed: /bin, /usr/bin, /sbin and /usr/sbin hold busybox plus
# tailscale/tailscaled/containerboot/iptables and nothing else), and because
# installing them at runtime would need egress that --force-relay deliberately
# blocks.
FROM alpine:3.22.1

RUN apk add --no-cache curl samba-client bind-tools

COPY entrypoint.sh /tools-entrypoint.sh

ENTRYPOINT ["/bin/sh", "/tools-entrypoint.sh"]
