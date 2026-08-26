# MeshBox⇄nufi-app agent adapter — stdlib only, so the image stays tiny.
FROM python:3.12-alpine
WORKDIR /app
COPY nufi_agent_adapter.py /app/nufi_agent_adapter.py
EXPOSE 8902
# Healthcheck hits the adapter's own /healthz, which probes nufi-agent.
HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=10s \
  CMD python3 -c "import urllib.request,sys; \
    sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8902/healthz').status==200 else 1)" \
    || exit 1
CMD ["python3", "/app/nufi_agent_adapter.py"]
