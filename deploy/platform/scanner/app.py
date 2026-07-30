"""Prompt-injection classifier sidecar.

Scores each span independently so the caller can apply a different threshold
to user-authored text than to retrieved or tool-produced content.

MODEL_ID defaults to an ungated Apache-2.0 classifier. Llama Prompt Guard 2
(`meta-llama/Llama-Prompt-Guard-2-22M`) is a drop-in upgrade but its
repository is gated, so it needs HF_TOKEN and an accepted licence.
"""

from __future__ import annotations

import os
import time
from typing import Any

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
# Hard input guard only. The real coverage bound is the window budget below,
# and the two used to disagree: a comment claimed _MAX_CHUNKS was the true limit
# while MAX_CHARS admitted spans nearly 12k tokens longer than the windows could
# reach, so the tail of a 54k-character span was structurally unscored. Coverage
# is now reported per span instead of being implied by a constant.
MAX_CHARS = int(os.environ.get("SCANNER_MAX_CHARS", "200000"))

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
# Wall-clock budget. A window cap alone cannot bound latency: the per-span floor
# of two windows means many spans still add up past any fixed count, and a scan
# that overruns the caller's timeout never delivers its coverage report at all —
# the caller just fails closed on a 503. Scoring stops at the deadline and the
# unscored spans are reported incomplete, which is the whole point of reporting.
_DEADLINE_S = float(os.environ.get("SCANNER_DEADLINE_S", "5.0"))
_BATCH = 8

_MALICIOUS_LABELS = {"INJECTION", "MALICIOUS", "LABEL_1", "JAILBREAK"}
_SAFE_LABELS = {"SAFE", "BENIGN", "CLEAN", "LABEL_0"}

# Who gets the scarce windows when a request exceeds `_MAX_WINDOWS_PER_REQUEST`.
# Lower sorts first. Mirrors the caller's `guardrails.types.SpanSource`; see the
# comment at the sort in `scan_spans` for why this is a table and what an
# unlisted name costs. Not validated against a closed set on purpose -- the
# caller's vocabulary may legitimately move ahead of this file's, and refusing a
# scan over an unrecognised source string would turn a naming skew into an
# outage of a fail-closed control.
_SOURCE_PRIORITY = {
    # Content that arrived from elsewhere mid-conversation. The caller enforces
    # on it from a single detector, so it is the source whose coverage matters
    # most.
    "untrusted": 0,
    # Text a human or the model produced. Real, scanned, reported -- but the
    # caller requires two independent detectors before acting on either, so a
    # window spent here cannot stop a request on its own.
    "user": 1,
    "assistant": 1,
    # `system` shares rank 1 rather than being demoted below `user`, even though
    # every shipped control prices it at 1.01 (unreachable) so windows spent
    # scoring it can change no verdict today. That fact lives in policy.yaml, a
    # file this sidecar cannot read and a deployment is free to edit; a ranking
    # here that depended on it would silently starve a source the moment someone
    # lowered the threshold. Ranks 0 and 1 are therefore exactly the partition
    # the previous `!= "untrusted"` test expressed, so nothing pre-existing
    # re-sorts.
    "system": 1,
}
_UNKNOWN_SOURCE_PRIORITY = 2

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


def _window_starts(total: int, budget: int) -> list[int]:
    """Choose which windows to score when a span needs more than the budget.

    Head and tail are ALWAYS scored. That is the whole point: the classic attack
    is pad-then-append, and a sequential scan that runs out of budget leaves the
    tail structurally unscored — which is how the previous version moved its
    blind spot from 2,500 characters to 52,000 rather than removing it. The
    remaining budget is spread evenly over the middle, so a buried payload faces
    sampled coverage rather than a guaranteed gap.
    """
    step = _CHUNK_TOKENS - _CHUNK_OVERLAP
    sequential = list(range(0, max(total - _CHUNK_OVERLAP, 1), step))
    if len(sequential) <= budget:
        return sequential

    last = sequential[-1]
    if budget <= 2:
        # Floor is BOTH ends, never one. A budget of 1 previously returned the
        # tail alone, which silently dropped head coverage the moment a request
        # squeezed its spans — measured at 2 of 4 head-planted injections caught
        # where the previous version caught 4 of 4. Two windows is the smallest
        # honest scan of a long span; if the budget cannot afford it, the span is
        # reported incomplete rather than scanned badly.
        return [0, last]

    interior = sequential[1:-1]
    take = budget - 2
    stride = len(interior) / take
    sampled = [interior[int(index * stride)] for index in range(take)]
    return [0, *sampled, last]


def _windows(text: str) -> tuple[list[str], bool]:
    """Split a span into overlapping windows, returning (windows, complete).

    `complete` is False when the span needed more windows than the budget
    allowed. Incomplete coverage is reported rather than hidden: a scanner that
    silently examines part of its input is exactly the fail-open shape this
    design exists to remove.
    """
    ids = _tokenizer.encode(text, add_special_tokens=False)
    if len(ids) <= _CHUNK_TOKENS:
        return [text], True

    starts = _window_starts(len(ids), _MAX_CHUNKS)
    step = _CHUNK_TOKENS - _CHUNK_OVERLAP
    complete = len(starts) == len(range(0, max(len(ids) - _CHUNK_OVERLAP, 1), step))
    windows = [
        _tokenizer.decode(ids[start : start + _CHUNK_TOKENS], skip_special_tokens=True)
        for start in starts
    ]
    return windows, complete


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
    # False when the span was longer than the window budget allowed. The caller
    # turns this into a policy input; it must never be silently discarded.
    complete: bool = True


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

    # Clock starts HERE, not at the scoring loop. Windowing and trimming cost
    # 2.6-2.8 s on a 30-span request — measured — and timing only the scoring
    # phase let the total reach 8.6-8.9 s against an 8 s caller budget. The
    # caller then fails closed and the coverage report never arrives, which
    # defeats the whole reason for reporting coverage instead of blocking.
    started = time.monotonic()

    spans = request.spans
    windowed = [_windows(span.text[:MAX_CHARS]) for span in spans]
    per_span = [item[0] for item in windowed]
    complete = [item[1] for item in windowed]

    # Budget windows per REQUEST, not just per span. Measured: ~200 ms per
    # window, so a RAG turn carrying several long documents would otherwise
    # blow past the caller's timeout — and G1 fails closed, which turns a slow
    # scan into a 503 for the user.
    #
    # Untrusted spans are served first. That is the threat model: a jailbreak
    # string inside a retrieved document is near-certain attack, while the same
    # words typed by a user may be a question about the topic. Spending the last
    # windows on user text would starve the source we most need to see.
    #
    # `_SOURCE_PRIORITY` is a table rather than a `!= "untrusted"` test because
    # the caller's source vocabulary GREW: `assistant` was split out of
    # `untrusted` on 2026-07-30 (guardrails/types.py), and a boolean test would
    # have silently re-sorted every prior assistant turn from first place to last
    # with nothing in this file acknowledging it. That re-sort is the right one --
    # a prior assistant turn is the model's own prose, and the caller now
    # requires two independent detectors before acting on it, so it has no claim
    # on the scarce windows that foreign content has -- but it is a decision, and
    # a decision belongs in a table an operator can read.
    #
    # A source name this file does not know sorts LAST, which is a coverage risk
    # worth stating: its long spans get shrunk first, and a shrunk span reports
    # `complete: False`, which reaches the caller as a `coverage_gap` finding.
    # policy.yaml prices that at 1.01 today (ignored), so an unknown source name
    # would lose coverage QUIETLY. Add new names here when the caller adds them;
    # the caller's `SpanSource` is the list.
    #
    # A shrunk span is re-windowed rather than truncated, so it keeps head and
    # tail. Dropping from the tail is what let a payload hide at the end.
    order = sorted(
        range(len(spans)),
        key=lambda index: (
            _SOURCE_PRIORITY.get(spans[index].source, _UNKNOWN_SOURCE_PRIORITY),
            -len(per_span[index]),
        ),
    )
    while sum(len(w) for w in per_span) > _MAX_WINDOWS_PER_REQUEST:
        # Filter must match the floor in `_window_starts`, which is 2. When it
        # said > 1, a span already at its floor was chosen as victim, re-windowed
        # back to 2, and chosen again — a live request hung past 90 seconds. A
        # proxy that hangs is a total outage, worse than anything it was guarding
        # against.
        victim = next(
            (index for index in reversed(order) if len(per_span[index]) > 2), None
        )
        if victim is None:
            break
        ids = _tokenizer.encode(spans[victim].text[:MAX_CHARS], add_special_tokens=False)
        starts = _window_starts(len(ids), len(per_span[victim]) - 1)
        per_span[victim] = [
            _tokenizer.decode(ids[start : start + _CHUNK_TOKENS], skip_special_tokens=True)
            for start in starts
        ]
        complete[victim] = False

    flat = [window for windows in per_span for window in windows]
    owners = [index for index, windows in enumerate(per_span) for _ in windows]

    # Score in batches against the deadline set at entry. Whatever is not
    # reached is reported, never assumed clean.
    raw: list[dict[str, Any]] = []
    for offset in range(0, len(flat), _BATCH):
        if offset and time.monotonic() - started > _DEADLINE_S:
            for owner in owners[offset:]:
                complete[owner] = False
            break
        raw.extend(_classifier(flat[offset : offset + _BATCH]))

    scored = [_injection_score(str(item["label"]), float(item["score"])) for item in raw]
    labels = [str(item["label"]).upper() for item in raw]
    owners = owners[: len(raw)]

    results: list[SpanResult] = []
    for index_of_span in range(len(per_span)):
        picks = [index for index, owner in enumerate(owners) if owner == index_of_span]
        span_scores = [scored[index] for index in picks]
        span_labels = [labels[index] for index in picks]
        count = len(span_scores)
        if not span_scores:
            results.append(SpanResult(score=0.0, label="EMPTY", complete=False))
            continue
        best = max(range(count), key=lambda index: span_scores[index])
        results.append(
            SpanResult(
                score=span_scores[best],
                label=span_labels[best],
                complete=complete[index_of_span],
            )
        )

    return ScanResponse(model=MODEL_ID, results=results)
