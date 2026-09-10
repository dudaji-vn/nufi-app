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

# python3 is here for the same reason curl is: the acceptance a member runs from
# home is deploy/platform/scenarios/run_box.py and studio/run_flows.py, both
# stdlib-only, and they have to run on THIS side of the NAT — resolving
# nufi.box.lab through MagicDNS and routing over node-a's tailscale0. Running
# them on the Mac instead would prove nothing about the mesh.
RUN apk add --no-cache curl samba-client bind-tools python3

COPY entrypoint.sh /tools-entrypoint.sh

ENTRYPOINT ["/bin/sh", "/tools-entrypoint.sh"]
