# works-egress -- the one way out of the sandbox network.
#
# tinyproxy, with its filter rendered at start from WORKS_EGRESS_ALLOW. Pinned
# by digest like every third-party image the box runs.
FROM alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc
RUN apk add --no-cache tinyproxy=1.11.2-r0 \
 && mkdir -p /etc/tinyproxy /var/log/tinyproxy /run/tinyproxy \
 && chown -R tinyproxy:tinyproxy /etc/tinyproxy /var/log/tinyproxy /run/tinyproxy
COPY render.sh entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/render.sh /usr/local/bin/entrypoint.sh
USER tinyproxy
EXPOSE 3128
# Healthcheck lives in compose, not here: `docker compose config` never sees
# an image's own HEALTHCHECK, and the house-rules test reads compose.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
