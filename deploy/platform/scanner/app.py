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
# Work budget, not a detection boundary — `_MAX_CHUNKS` is the real bound.
MAX_CHARS = int(os.environ.get("SCANNER_MAX_CHARS", "64000"))

# Measured on the pinned model: an injection appended after ~640 tokens of
# ordinary prose scores SAFE with high confidence, and six long spans converged
# on the identical floor score of a payload-free control. The attention horizon,
# not the character budget, is the real limit — and it sits well inside the old
# 4000-character cap, so head-only scoring was a bypass costing an attacker
# nothing but padding. Windows stay comfortably under it.
_CHUNK_TOKENS = 450
_CHUNK_OVERLAP = 64
_MAX_CHUNKS = int(os.environ.get("SCANNER_MAX_CHUNKS", "24"))
# Bounds worst-case request latency. At ~200 ms per window this keeps a scan
# under roughly 5 s, which is what the caller allows before failing closed.
_MAX_WINDOWS_PER_REQUEST = int(os.environ.get("SCANNER_MAX_WINDOWS", "24"))

_MALICIOUS_LABELS = {"INJECTION", "MALICIOUS", "LABEL_1", "JAILBREAK"}
_SAFE_LABELS = {"SAFE", "BENIGN", "CLEAN", "LABEL_0"}

app = FastAPI(title="nufi-scanner")
_classifier = pipeline("text-classification", model=MODEL_ID, revision=MODEL_REVISION)
_tokenizer = _classifier.tokenizer


def _assert_labels_understood() -> None:
    """Refuse to start against a model whose labels we cannot interpret.

    Scores are normalised to "probability this span is an injection", which
    requires knowing which label means which. An unrecognised label previously
    fell through to `1.0 - score`, so a model emitting SUSPICIOUS=0.92 reported
    an injection score of 0.08 — confidently wrong, silently, with no error.
    A guardrail that misreads its own detector must not boot.
    """
    labels = {str(name).upper() for name in _classifier.model.config.id2label.values()}
    unknown = sorted(labels - _MALICIOUS_LABELS - _SAFE_LABELS)
    if unknown:
        raise RuntimeError(
            f"{MODEL_ID}@{MODEL_REVISION} emits unrecognised label(s) {unknown}. "
            f"Add them to _MALICIOUS_LABELS or _SAFE_LABELS before using this model."
        )
    if not labels & _MALICIOUS_LABELS:
        raise RuntimeError(
            f"{MODEL_ID}@{MODEL_REVISION} declares no malicious label; "
            f"every span would score as safe."
        )


_assert_labels_understood()


def _windows(text: str) -> list[str]:
    """Split a span into overlapping windows the model can actually attend to.

    Every window is scored and the span takes the maximum, so a payload buried
    anywhere in a long document is still seen. Overlap keeps an injection that
    straddles a boundary intact.
    """
    ids = _tokenizer.encode(text, add_special_tokens=False)
    if len(ids) <= _CHUNK_TOKENS:
        return [text]

    step = _CHUNK_TOKENS - _CHUNK_OVERLAP
    windows: list[str] = []
    for start in range(0, len(ids), step):
        window = ids[start : start + _CHUNK_TOKENS]
        if not window:
            break
        windows.append(_tokenizer.decode(window, skip_special_tokens=True))
        if len(windows) >= _MAX_CHUNKS or start + _CHUNK_TOKENS >= len(ids):
            break
    return windows


def _injection_score(label: str, score: float) -> float:
    upper = label.upper()
    if upper in _MALICIOUS_LABELS:
        return score
    if upper in _SAFE_LABELS:
        return 1.0 - score
    # Startup validation should have prevented this. Fail closed rather than
    # inverting a label we do not understand.
    return 1.0


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

    per_span = [_windows(span.text[:MAX_CHARS]) for span in request.spans]

    # Cap windows per REQUEST, not just per span. Measured: ~200 ms per window,
    # so a RAG turn carrying several long documents would otherwise blow past
    # the caller's timeout — and G1 fails closed, which turns a slow scan into a
    # 503 for the user. Windows are dropped from the tail of the longest spans
    # first, so every span keeps its head and no span goes entirely unscored.
    while sum(len(w) for w in per_span) > _MAX_WINDOWS_PER_REQUEST:
        longest = max(range(len(per_span)), key=lambda index: len(per_span[index]))
        if len(per_span[longest]) <= 1:
            break
        per_span[longest].pop()

    flat = [window for windows in per_span for window in windows]
    raw = _classifier(flat) if flat else []
    scored = [_injection_score(str(item["label"]), float(item["score"])) for item in raw]
    labels = [str(item["label"]).upper() for item in raw]

    results: list[SpanResult] = []
    cursor = 0
    for windows in per_span:
        count = len(windows)
        span_scores = scored[cursor : cursor + count]
        span_labels = labels[cursor : cursor + count]
        cursor += count
        if not span_scores:
            results.append(SpanResult(score=0.0, label="EMPTY"))
            continue
        best = max(range(count), key=lambda index: span_scores[index])
        results.append(SpanResult(score=span_scores[best], label=span_labels[best]))

    return ScanResponse(model=MODEL_ID, results=results)
