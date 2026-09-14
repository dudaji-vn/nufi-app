# nufi-cron — stdlib only, so the image stays tiny and multi-arch, the same
# bargain nufi-ingest makes.
FROM python:3.12-alpine
WORKDIR /app
COPY nufi_cron.py /app/nufi_cron.py
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=30s \
  CMD test -n "$(find /state/heartbeat -mmin -3 2>/dev/null)"
CMD ["python3", "/app/nufi_cron.py"]
