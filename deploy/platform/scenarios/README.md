# 부서별 시나리오 — 실행되는 사용기

The appliance sells 17 use cases across 8 departments, and its catalog engine
carries eight published use stories. All eight are `covered_by=mesh`: remote
access, shared drives, permissions, audit. The AI half — `covered_by=platform`,
the Chat/RAG/Agent the product introduction is built around — is **empty**,
because `portal/blog.py` refuses such a story with `409` until the module
genuinely answers.

This directory fills that slot the way the appliance's own `GUARDRAILS.md`
demands: *안 해 본 것을 "해봤다"고 공개하지 않습니다* — do not publish what you
have not done. So nothing here is written prose about what a department *could*
do. `run.py` drives a live box through its own `/api/v1` surface and writes down
the request and the response.

## What it walks

Per department, the daily triad the product introduction names:

```
공유 드라이브  →  근거와 함께 답하는 RAG  →  에이전트 루틴
```

Four departments, sixteen questions: 법무 · 인사 · 총무 · 전략기획.

Each question is one of two kinds, and they check opposite things:

- **extract** — the answer must contain the fact the document states.
- **refuse** — the box must decline. Inventing a plausible answer to a question
  the documents do not cover is the failure mode that matters most here, so a
  fluent reply with no refusal marker is recorded as a failure.

Answers are also scanned for **한국어 이탈** — the on-box model occasionally
finishes a Korean sentence in Chinese. That is reported separately from
correctness, because a right answer in the wrong language is a different defect
from a wrong answer.

## Run it

```bash
python3 run.py --base http://127.0.0.1:8080          # all four
python3 run.py --only hr                             # one department
```

Exit `0` = every check passed. Output lands in `evidence/scenarios.md`
(the transcript, for a reader) and `evidence/scenarios.json` (the same run,
for a diff).

Preconditions: the box's three AI modules must read `available`
(`GET /api/v1/ai/status`) — the runner records their state in the evidence
header, so a run against a half-wired box says so rather than looking clean.

## Why the evidence reproduces

A published use story has to carry evidence a reader can reproduce, so the
generation path is pinned twice. `temperature: 0` fixes the *fact*; a fixed
`seed` fixes the *wording*. Without the seed the same question came back as
`10일입니다` on one run and `10일간 부여됩니다` on the next, and once picked the
wrong adjacent number outright — enough to make a published block fail to
reproduce. With both pinned, two consecutive full runs differ in **0 of 16**
answers.

## What these runs show about the box, honestly

**It is reliable at extraction and at declining.** All sixteen checks pass:
every stated fact comes back correct with its source, and every question outside
the documents is refused rather than invented.

**It is not reliable at deriving.** Asked to apply *"1 day per 2 years beyond the
first year"* to three years of service, it answers 20 where the policy gives 16 —
and at temperature 0 it answers 20 every time. Retrieval grounds *finding*; it
does not ground *reasoning*. The honest claim is extraction with citation.

**Three gaps belong to the appliance's contract, not to this repo:**

1. **Sources cite every document on the box.** `/v1/query` carries only
   `{question}`, so retrieval cannot be scoped to a department — a 법무 answer
   lists 인사 documents among its sources. rag_api supports `entity_id`; the
   MeshBox contract has no field to carry it.
2. **A routine has no input channel.** The portal's run call sends
   `{routine_id, routine}` — the routine's *name*. The model receives
   `'회의록 요약·액션아이템' 루틴을 실행하세요.` and nothing else, so it replies
   asking which meeting. The two recipes the deck sells as daily work —
   meeting summary and weekly report — cannot yet act on department data. The
   agent section of the evidence records exactly that, unedited.
3. **`DEFAULT_TIMEOUT = 10.0` in `portal/ai.py` is hardcoded.** Warm, an on-box
   routine finishes in 5–8s. Cold, the first run after the box has been idle
   exceeds it and the member is told *AI 백엔드에 연결하지 못했습니다* — a
   connection error, for a model that is working.
