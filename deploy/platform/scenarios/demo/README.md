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

The other two cuts follow the same split against the same `stage.mjs`:
`week.mjs` + `record-week.mjs` for the weekly report on the Studio scenarios,
and `box-script.mjs` + `box.mjs` for [the box cut](#the-box-cut).

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

## The box cut

`box.mjs` is the weekly report about the NuFi box: one command, and then a
department's drive becoming its agent's knowledge. Same look, same rules, a
different subject and a different live target — a real box on the LAN rather
than the platform stack.

```bash
node box.mjs --lang en --out box-en.webm --box ../../../box
node box.mjs --lang ko --out box-ko.webm --box ../../../box
ffmpeg -i box-en.webm -c:v libx264 -pix_fmt yuv420p -crf 24 -movflags +faststart box-en.mp4
```

`--box` is the installed box's directory: the recorder reads its `.env` for the
box name, its address, the admin login and the model, so nothing about the
target is hard-coded here. `--ingest` names the ingest container
(`nufi-box-nufi-ingest-1`), `--evidence` the acceptance JSON the closing card is
computed from. `box-en.mp4` and `box-ko.mp4` run about four minutes each.

### The shots

| # | Shot | What it verifies before it is captioned |
|---|---|---|
| 1 | Title | — |
| 2 | One command | Each of the four URLs the banner prints is fetched in a scratch tab; a non-2xx aborts the run |
| 3 | The app | Login lands on `/c/…`, and the model badge on screen equals `NUFI_MODEL` from `.env` |
| 4 | The acceptance question | The Legal agent is found by name through the app's own API; the answer is read back and the caption picked from it (leaked tool call, or the number) |
| 5 | A question it answers | Up to three tries, counted on screen; the answer must contain both the year and the file name before the "cited" caption is used |
| 6 | The drive | The document is written, `stat`ed, and `ls`-ed; the panel shows the real listing and byte count |
| 7 | Ingest | `docker logs` is polled from the moment of the write until this file's own `added … (embedded=True)` line appears, and the elapsed seconds go on the card |
| 8 | The new file's own question | Two tries; the "cited" caption needs the new file's name in the answer |
| 9 | One login | The account menu's console tab must carry no password field |
| 10 | Studio | Same — plus whether it has flows, which chooses between two captions |
| 11 | What it scores | 8 / 32 / 10 is recomputed from `../evidence/box.json`, not typed |
| 12 | Next | — |

### Three things it deliberately does

**The banner is the README's, not the installer's.** `install-box.sh --dry-run`
prints the generated admin password, the JWT secrets and the LiteLLM master key.
A recording that goes to a board cannot film that, so the card carries the
banner as the box README documents it and proves it instead by asking all four
of its URLs live, during the take.

**It puts the drive back.** The cut writes one document into
`data/drives/legal` on camera and removes it in a `finally`, then waits for the
daemon's `removed …` line. The daemon deletes the server-side file and its
embedding on that scan, so a recording leaves the Legal corpus exactly as it
found it and the next acceptance run measures the same thing as the last one.

**It resolves the box's name itself.** The installer announces `nufi.local` with
a background `dns-sd` holding the address the machine had at install time, so a
new DHCP lease leaves the name pointing at a stranger. Rather than reconfigure a
box this recording is only supposed to use, Chromium is launched with
`--host-resolver-rules=MAP <box host> <BOX_IP from .env>`. The name in the frame
and the certificate behind it are both the box's own.

### What it does not have

**No Studio flow shot.** The box installs the four products but no flows —
`build_flows.py --box` is P2 work and is not done — so Studio opens signed in
and empty, and the caption says exactly that. When flows do ship with the
installer the recorder already carries the other caption and will pick it.

### What this box does, filmed rather than argued about

The first question the acceptance run asks Legal (`자동연장 … 며칠 전까지`,
answer 60) leaked its tool call as prose on every take. The second
(`NDA … 몇 년간`) answered, cited `계약검토_표준조항.txt`, and the passage it
retrieved is the one that also holds the 60. Retrieval is not the weak part.

One thing worth knowing before relying on a drive: measured on this box on
2026-09-09, the same NDA question answered 3/3 with one file on the Legal drive
and leaked its tool call 5/5 with two. The recorder handles both — that is why
shots 5 and 8 each carry a "cited" and a "did not" caption — but a 7B model
choosing between two documents is a real limit, not a flaky take.

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
