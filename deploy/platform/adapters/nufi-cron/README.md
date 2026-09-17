# nufi-cron

Runs the box's department routines on a clock, and leaves each answer as a file
on the department's own drive.

A routine is a Studio flow tagged `nufi-routine`, built by
`build_flows.py --box`. Until this sidecar existed one only ran when a person
opened Studio and pressed a button, which is no use for *"the weekly report,
every Friday at five"*.

Design and the decisions behind it:
[`docs/superpowers/specs/2026-09-14-box-scheduled-routines-design.md`](../../../../docs/superpowers/specs/2026-09-14-box-scheduled-routines-design.md).

## The schedule file

`data/schedules.ini` on the box, one section per scheduled routine. The daemon
re-reads it every tick, so adding a report needs no restart.

```ini
[legal-weekly]
cron  = 0 17 * * 5
flow  = Routine · weekly report from the drive
drive = legal
ask   = 이번 주 주간보고 초안을 써줘.
out   = weekly-report-{date}.md
```

| key | |
|---|---|
| `cron` | five fields — minute, hour, day-of-month, month, day-of-week. `*`, numbers, `a-b`, `a,b` and `*/n`. No `@weekly` aliases. |
| `flow` | the name of a routine, exactly as Studio shows it |
| `drive` | which department drive it reads, and writes into |
| `ask` | the question the routine is given |
| `out` | the file name. `{date}` becomes the run's date; a name without it is overwritten each run. |

`nufi-box schedule list` prints what this file means and when each schedule next
fires — through the daemon's own parser, so the two cannot disagree.

A section that cannot be understood is logged and skipped. One typo does not
stop the other reports.

## Or a folder instead of a clock

A section names exactly one trigger: `cron`, above, or `watch` — a folder
relative to the drive, fired when a file lands in it. Two rules keep that
from misfiring: the first scan of a `watch` folder records everything
already there and fires nothing (the same "nothing is caught up" rule
`cron` follows), and a file has to hold still — same size, same modified
time — for two ticks in a row before it fires, so a copy still landing over
Samba is never triggered on half a file. Details and the full key table:
[`deploy/box/README.md`](../../../box/README.md).

## Where the answer goes

`data/drives/<drive>/_routines/<out>` — inside the department's shared folder,
where people already look.

**`nufi-ingest` refuses to embed anything under `_routines/`.** Without that, last
week's report becomes a source this week's is drafted from: a routine citing
itself, a little more confidently each week, with nothing on the drive to blame.
The folder is not named `.routines` — that would have been ignored for free, and
a folder hidden in Finder and over Samba is a report nobody can see.

## Why the build endpoint and not `/api/v1/run`

`run_flows.py` uses the simple `/run` call and says in its own comment what is
wrong with it here: giving up on the socket **does not stop the run on the box**.
It keeps generating with nobody listening, holding the one model on the box
against every other question — P2 watched a routine pass 40,000 tokens after its
client had been killed.

So a scheduled run goes through the job path, which can be called off:

```
POST /api/v1/build/<flow_id>/flow?event_delivery=polling   -> {"job_id": …}
GET  /api/v1/build/<job_id>/events                          poll until `end`
POST /api/v1/build/<job_id>/cancel                          when the deadline passes
```

All three take the superuser's `x-api-key`. The cost is that the build endpoint
takes no `tweaks`, so pointing a routine at a department is a patched graph
rather than an override — `graph_for()` sets the drive path and the vector
collection together, because a report written from one department's files and
another's index is worse than one that fails.

## Environment

| | |
|---|---|
| `NUFI_STUDIO_URL` | `http://studio:7860` |
| `STUDIO_API_KEY` | the box's Studio superuser key, from `.env` |
| `NUFI_DRIVES_DIR` | `/drives`, mounted **read-write** (unlike nufi-ingest's) |
| `NUFI_SCHEDULES` | `/config/schedules.ini` |
| `NUFI_STATE_DIR` | `/state` — heartbeat, and the last minute each schedule fired |
| `NUFI_CRON_TICK_INTERVAL` | seconds between ticks, default 20 |
| `NUFI_CRON_RUN_TIMEOUT` | seconds before a run is cancelled, default 900 |

## What it will not do

- **Catch up.** A box that was off over a scheduled minute has missed that
  report. Firing five hours of them at boot is worse than the gap.
- **Overlap.** A schedule still running when its next tick arrives is skipped and
  logged. The box answers one question at a time.
- **Retry.** A failed run is logged; the next tick tries again.

## Tests

```sh
python3 test_nufi_cron.py     # exit 0 = PASS
```

No Docker, no live box. The cron matcher and the config parser are exercised
against a clock the test controls; the run path is driven against a fake Studio
over `ThreadingHTTPServer`, so what is tested is the sequence of calls that will
actually be made.

Two of those tests exist because of something a fake alone would never have
caught, and were added after pointing the daemon at the real box:

- the fake **gzips** its flow listing. The first live tick died on
  `'utf-8' codec can't decode byte 0x8b in position 1` — Studio compresses its
  responses and urllib does not ask it not to. Remove the two-line fix and three
  tests fail.
- the timeout test asserts the **cancel call arrives**, not merely that the
  daemon stopped waiting — a test that checked only the latter would pass
  against the bug this daemon exists to avoid.
