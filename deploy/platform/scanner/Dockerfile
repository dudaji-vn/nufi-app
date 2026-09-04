FROM python:3.12.7-slim-bookworm

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=180s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

# Three workers, because one made the gateway unusable with more than one
# caller.
#
# `scan_spans` is a synchronous endpoint running a CPU-bound transformer, so a
# single worker serialises every request behind the one in front. The guardrail
# gives it 8 seconds (SCANNER_TIMEOUT_S) and fails closed, so a queue does not
# slow requests down, it refuses them. Measured on the live gateway 2026-09-03
# with a full agent payload:
#
#     1 concurrent request  -> ok
#     3 concurrent requests -> 3/3 GUARDRAIL_UNAVAILABLE
#     6 concurrent requests -> 6/6 GUARDRAIL_UNAVAILABLE
#
# Every NUFI Works company with two working agents failed on that. It also
# explains a day of "intermittent" guardrail errors that were nothing of the
# sort — each one coincided with a second agent running.
#
# Three, not more: each worker loads its own copy of the classifier. Measured on
# the host, one worker holds 1.764 GiB resident — not the ~700 MB the download
# size suggests — so this costs about 3.5 GiB on top. The host has 31.3 GiB with
# roughly 8.3 GiB in containers, so that is comfortable, and three matches the
# agent count a department actually runs. Raising it further is bounded by CPU
# cores rather than memory: check `nproc` before going past it, since these
# workers are compute-bound and oversubscribing them only adds latency.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "3"]
