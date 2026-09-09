# nufi-ingest — stdlib only, so the image stays tiny and multi-arch.
FROM python:3.12-alpine
WORKDIR /app
COPY nufi_ingest.py /app/nufi_ingest.py
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=60s \
  CMD test -n "$(find /state/heartbeat -mmin -3 2>/dev/null)"
CMD ["python3", "/app/nufi_ingest.py"]
