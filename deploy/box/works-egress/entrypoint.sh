#!/bin/sh
# Render the allow list, write tinyproxy's config, start it in the foreground.
#
# Rendered at container start rather than baked in, so changing
# WORKS_EGRESS_ALLOW in .env is `nufi-box restart works-egress` and not an
# image rebuild -- the same reason nufi-cron re-reads schedules.ini.
set -eu
/usr/local/bin/render.sh > /etc/tinyproxy/filter

cat > /etc/tinyproxy/tinyproxy.conf <<'EOF'
User tinyproxy
Group tinyproxy
Port 3128
# Only the sandbox network may use this proxy. The box network is where the
# proxy goes OUT; nothing on it needs to come IN through here.
Listen 0.0.0.0
Timeout 600
# Refusals are the one thing this design has that Cilium's does not: an
# answer to "what did that agent try to reach". tinyproxy 1.11's safe-open
# check refuses LogFile "/dev/stderr" (a symlink: "has been changed before
# it could be opened") and then logs nothing, so this runs in the foreground
# (-d below) and logs to stdout instead, which nufi-box logs works-egress
# already captures under the box's bounded log rotation.
LogLevel Connect
MaxClients 64
# The filter: exact hostnames, default deny. FilterType fnmatch is what makes
# "pypi.org" match pypi.org and not evil-pypi.org -- FilterExtended's regex
# flavour would substring-match the same way and let it through.
Filter "/etc/tinyproxy/filter"
FilterDefaultDeny Yes
FilterType fnmatch
FilterURLs Off
# CONNECT (what HTTPS uses) only to the ports the allowed hosts actually
# serve: 443 for the world, 3100 for Works, 4000 for the gateway.
ConnectPort 443
ConnectPort 3100
ConnectPort 4000
# No Via / X-Tinyproxy headers: a sandbox does not need to learn the proxy's
# name from its own responses.
DisableViaHeader Yes
ViaProxyName "works-egress"
EOF

exec tinyproxy -d -c /etc/tinyproxy/tinyproxy.conf
