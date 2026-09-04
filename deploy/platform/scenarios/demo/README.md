# 데모 영상 — 박스가 스스로 찍는 3분

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

The cut follows the frame the board set out: a department buys a PC and uses a
**shared drive**, a **chat tool**, and an **AI agent** — plus the connector that
has to be as easy as Tailscale. An earlier cut showed only RAG and the refusals;
it was a good film about trust and the wrong film for the question asked.

## The storyboard

1. **Title** — one box, the department's work stays inside it.
2. **How it is wired** — laptop → mesh → **MeshBox** (*runs no model*) → **three
   adapters** (`nufi-app`) → **on-box model**. The whole integration, said first.
3. **The seam answering for itself** — the adapters' real `/healthz` replies.
4. **The console will not flatter the box** — `available` only after a probe.
5. **Connect** — a laptop registered in the console, and the one-click
   `meshbox-connect.command` it hands back. The part that has to be as easy as
   Tailscale, and the part the board is building.
6. **The drive** — eight shares, and a contract guide uploaded to 법무 while
   the camera is running.
7. **Chat** — an internal notice drafted on the box.
8. **RAG** — a 총무 question answered from the uploaded policy, with sources.
9. **The refusal** — a question the documents do not cover, declined.
10. **Agent** — a routine run, and an honest word about what it receives today.
11. **The wall** — the same adapter aimed at a public host, `403`.
12. **Breadth, and close** — eight departments, thirty-two checks, all passing.

Shots 9 and 11 are the ones worth watching. Anything can answer; the value is in
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
