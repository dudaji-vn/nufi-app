# MeshBox⇄nufi-app chat adapter — stdlib only, so the image stays tiny.
FROM python:3.12-alpine
WORKDIR /app
COPY nufi_egress.py /app/nufi_egress.py
COPY nufi_chat_adapter.py /app/nufi_chat_adapter.py
EXPOSE 8900
# Healthcheck hits the adapter's own /healthz, which in turn probes the upstream.
HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=10s \
  CMD python3 -c "import urllib.request,sys; \
    sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8900/healthz').status==200 else 1)" \
    || exit 1
CMD ["python3", "/app/nufi_chat_adapter.py"]
