# 데모 영상 — 박스가 스스로 찍는 96초

`record.mjs` records a live box doing department work and writes an English and
a Korean cut of the same storyboard. 1600×1000, about 96 seconds each, no
presenter needed.

```bash
node record.mjs --lang en --out demo-en.webm
node record.mjs --lang ko --out demo-ko.webm
ffmpeg -i demo-en.webm -c:v libx264 -pix_fmt yuv420p -crf 24 -movflags +faststart demo-en.mp4
```

Three files, three jobs, deliberately separate:

| file | holds |
|---|---|
| `script.mjs` | every line of narration, both languages |
| `stage.mjs` | the look — title cards, caption card, architecture diagram |
| `record.mjs` | the storyboard, and the checks that keep it honest |

Wording can be argued about without touching the machinery that verifies it.

## The storyboard

1. **Title** — one box, the department's work stays inside it.
2. **How it is wired** — a diagram built in three beats: laptop → mesh →
   **MeshBox** (portal, drives, console; *runs no model*) → **three adapters**
   (`nufi-app`; chat 8900, rag 8901, agent 8902) → **on-box model**. This is the
   whole integration, and the shot most people ask for first.
3. **The seam answering for itself** — the three adapters' real `/healthz`
   replies, fetched during the recording, showing what each is actually talking
   to and the `k` / `documents` ratio retrieval depends on.
4. **The console will not flatter the box** — `available` only because a probe
   was answered.
5. **The drive** — eight department shares; the folder a laptop mounts is the
   folder the AI answers from.
6. **A real question**, answered from the uploaded policy.
7. **A question the documents do not cover** — declined, not invented.
8. **The wall** — the same adapter aimed at a public host, answering `403`.
9. **Close.**

Shots 7 and 8 are the ones worth watching. Anything can answer; the value is in
what it refuses.

## The recorder checks its own claims

An early cut captioned *"Answered from the document"* over a panel reading
`AI 백엔드에 연결하지 못했습니다: timed out`. A recording that narrates a success
the screen did not show is worse than no recording — and this one goes to a
board. So the run **aborts** rather than film a lie:

- every answer step reads the panel back and fails on an error;
- the second question is compared against the first answer, because the panel
  keeps the previous result and would otherwise let a stale read pass as fresh
  — it did, silently, until this was added;
- an answer containing Han characters stops the run. The on-box model sometimes
  finishes a Korean sentence in Chinese; that defect is recorded in
  [`../README.md`](../README.md), but filming a garbled frame teaches nothing;
- the closing `403` is asserted to be a `403`. If that adapter ever stops
  refusing, the recording fails instead of quietly showing a `200`.

Two production details worth knowing:

- **Everything slow runs behind the architecture card** — signing in, warming
  the model, probing three adapters. Done afterwards, the clip sat on a
  motionless page for most of a minute.
- **The overlay is `pointer-events:none`.** Without it the presentation layer
  swallows the click meant for the app, and the recording films itself.

## Preconditions

A live box with the three modules `available`, `NUFI_RAG_K` at 16 or more (see
[`../README.md`](../README.md)), and a second chat adapter on `:8903` running
`NUFI_EGRESS_MODE=enforce` against a public upstream — that adapter is what
produces the refusal in the closing shot.

## Known blemish, not ours to fix

In the English cut the console's **AI module names stay Korean**
(`안전한 사내 Chat`, badge `정상`) while the surrounding chrome is English. The
appliance's i18n translates data-module strings at the view boundary, and these
ones are not covered. It belongs to the appliance repo; noted here so nobody
mistakes it for a recording fault.
