# 데모 영상 — 박스가 실제로 일하는 70초

`record.mjs` records a live box doing department work and writes `demo.webm`
(plus `demo.mp4` if you convert it). Roughly 70 seconds, no presenter needed:
each step carries a caption stating the claim it is demonstrating.

```bash
node record.mjs --base http://127.0.0.1:8080 --out demo.webm
ffmpeg -i demo.webm -c:v libx264 -pix_fmt yuv420p -crf 26 -movflags +faststart demo.mp4
```

## What it shows

1. A department signs in to its own box.
2. Three modules read `available` — and only because their endpoints answered a
   probe. Unwired reads `not_connected`, never a flattering green.
3. Eight department shares on the drive — the same folders a laptop mounts.
4. A 총무팀 question answered from the uploaded policy, on this machine.
5. **A question the documents do not cover — declined, not invented.**
6. **The same adapter pointed at a public host — `HTTP 403`, refusing to carry
   department text off the mesh.**

Steps 5 and 6 are the ones worth watching. Anything can answer; the value is in
what it refuses.

## The recorder checks itself

The first cut captioned *"Answered from the document"* over a panel that read
`AI 백엔드에 연결하지 못했습니다: timed out`. A recording that narrates a success
the screen did not show is worse than no recording. So:

- every answer step **reads the panel back** and aborts if an error landed there;
- the second question is compared against the first answer, because the panel
  keeps the previous result and would otherwise let a stale read pass as fresh;
- an answer containing Han characters **stops the run** — the on-box model
  sometimes finishes a Korean sentence in Chinese, and while that defect is
  recorded in [`../README.md`](../README.md), filming a garbled frame teaches a
  viewer nothing;
- the model is warmed before recording, because the portal caps an AI call at
  10s and a cold model load alone exceeds that.

The `403` in the last shot is a real POST made during the recording, rendered
from the adapter's own response — not a page written to look like one.

## Preconditions

A live box with the three modules `available`, `NUFI_RAG_K` at 16 or more (see
[`../README.md`](../README.md)), and a second chat adapter on `:8903` configured
with `NUFI_EGRESS_MODE=enforce` against a public upstream, which is what
produces the refusal in the closing shot.
