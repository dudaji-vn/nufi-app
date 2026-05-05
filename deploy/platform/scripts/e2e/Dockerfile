# Pinned to the Python 3.12.7 slim image so the e2e harness matches the
# stack's "no :latest, pin everything" convention.
FROM python:3.12.7-slim-bookworm

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY e2e_smoke_test.py /app/e2e_smoke_test.py

CMD ["python", "/app/e2e_smoke_test.py"]
