"""Prompt-injection classifier sidecar.

Scores each span independently so the caller can apply a different threshold
to user-authored text than to retrieved or tool-produced content.

MODEL_ID defaults to an ungated Apache-2.0 classifier. Llama Prompt Guard 2
(`meta-llama/Llama-Prompt-Guard-2-22M`) is a drop-in upgrade but its
repository is gated, so it needs HF_TOKEN and an accepted licence.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from pydantic import BaseModel
from transformers import pipeline

MODEL_ID = os.environ.get(
    "SCANNER_MODEL_ID", "protectai/deberta-v3-base-prompt-injection-v2"
)
# Pinned so the classifier cannot change under us — this is a security control,
# and an unpinned model is the same supply-chain exposure as an unpinned image.
# Verified 2026-07-27: apache-2.0, ungated.
MODEL_REVISION = os.environ.get(
    "SCANNER_MODEL_REVISION", "90c9989b1a342275dd0d1a95aad283c04e075671"
)
MAX_CHARS = int(os.environ.get("SCANNER_MAX_CHARS", "4000"))
_MALICIOUS_LABELS = {"INJECTION", "MALICIOUS", "LABEL_1", "JAILBREAK"}

app = FastAPI(title="nufi-scanner")
_classifier = pipeline(
    "text-classification", model=MODEL_ID, revision=MODEL_REVISION, truncation=True
)


class SpanIn(BaseModel):
    text: str
    source: str = "user"


class ScanRequest(BaseModel):
    spans: list[SpanIn]


class SpanResult(BaseModel):
    score: float
    label: str


class ScanResponse(BaseModel):
    model: str
    results: list[SpanResult]


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "model": MODEL_ID, "revision": MODEL_REVISION}


@app.post("/scan/spans", response_model=ScanResponse)
def scan_spans(request: ScanRequest) -> ScanResponse:
    if not request.spans:
        return ScanResponse(model=MODEL_ID, results=[])

    texts = [span.text[:MAX_CHARS] for span in request.spans]
    raw = _classifier(texts)

    results = []
    for item in raw:
        label = str(item["label"]).upper()
        score = float(item["score"])
        malicious = label in _MALICIOUS_LABELS
        results.append(SpanResult(score=score if malicious else 1.0 - score, label=label))

    return ScanResponse(model=MODEL_ID, results=results)
