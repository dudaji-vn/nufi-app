# Scheduled routines on the box — design

2026-09-14. Closes gap **G** of the box plan ("Routines have no input… Scheduled
routines are a small `nufi-cron` sidecar"), which P3 needs before the Legal, HR,
General Affairs and Strategy weeks can run: four of the routines those weeks
depend on — Renewal tracker, Weekly report draft, Onboarding checklist, the
quarterly renewals sweep — are scheduled, and today a routine only runs when a
person presses a button in Studio.

## What a routine is today

`build_flows.py --box` creates four flows tagged `nufi-routine` under the box's
Studio superuser. Each takes a question (`input_value`), reads one department
drive, and **returns text**. Nothing writes anywhere. `ROUTINE_MAX_TOKENS = 2048`
caps how much a run generates, because the routines talk to Ollama directly and
so are not behind LiteLLM's `request_timeout`.

## Decisions

### The schedule lives in a file on the box, not on the flow

The plan's sentence carries both ("crontab in a config file … a schedule field on
the flow"). Only the file is built.

Langflow has no schedule field, so putting one on the flow means forking more of
the Studio UI. The fork is held at 102 allowlisted lines by
`nufi/check-fork-diff.sh`, and an input box is not worth spending that budget on.

The stronger reason is ownership. Routines are **copied per member**
(`nufi/member_routines.py`), so a schedule attached to a member's copy runs once
per member — eight people in a department means eight identical weekly reports
written into one folder. A department's weekly report belongs to the department,
and the box admin is the one who owns it.

### Scheduled runs execute the superuser's canonical flow

Not a member's copy, for the same reason. The flow is found by name among the
superuser's `nufi-routine` flows — the same canonical set `member_routines.py`
already defines as "what a superuser owns".

### Output is a file on the drive, in `_routines/`

`data/drives/<dept>/_routines/<out>`. A department sees its report in the shared
folder it already uses, with no app to open.

**`nufi-ingest` must skip that folder.** Its `IGNORED_PREFIXES` is `(".", "~$",
"._")`, which does not cover it, so today a weekly report would be embedded and
become part of the knowledge the *next* weekly report is drafted from — a routine
citing itself, more confidently each week. Naming the folder `.routines` would
get the exclusion for free and is rejected: a dot-folder is hidden in Finder and
over Samba, and a report nobody can see is not a report.

### One run at a time, with a wall clock on it

A tick that arrives while the previous run of the same schedule is still going is
**skipped**, and every run gets a hard timeout.

This is the other half of the P3 generation hazard. P2 watched a routine pass
40,000 tokens and outlive the client that asked for it; `num_predict` capped how
much one generation emits, but nothing caps a run that stalls or a client that
walks away.

A client-side timeout alone would be theatre, and `run_flows.py` says so in its
own comment: giving up on the socket **does not stop the run on the box**, which
goes on generating with nobody listening and holds the model against every other
question. So the deadline has to be enforced where the run lives, which decides
the endpoint below.

## Shape

A sidecar, built to the same pattern as `nufi-ingest`, which has been the box's
only long-running daemon and works: Python **stdlib only**, Alpine, a heartbeat
file its Docker `HEALTHCHECK` reads, `restart: unless-stopped`.

```
deploy/platform/adapters/nufi-cron/
  nufi_cron.py        the daemon
  test_nufi_cron.py   stdlib unittest, no Docker, no live box
  Dockerfile
  README.md
```

### Config

INI, via stdlib `configparser` — no YAML parser to vendor, and a person can edit
it by hand. It lives on the box at `${NUFI_DATA_DIR}/schedules.ini`, mounted
read-only into the sidecar.

```ini
[legal-weekly]
cron  = 0 17 * * 5
flow  = Routine · weekly report from the drive
drive = legal
ask   = 이번 주 주간보고 초안을 써줘.
out   = weekly-report-{date}.md
```

- `cron` — five fields, the usual minute/hour/dom/month/dow. Supports `*`,
  numbers, `a-b` ranges, `a,b` lists and `*/n` steps. No `@weekly` aliases and no
  seconds field; both are additions a person can ask for once this is in use.
- `flow` — the name of a superuser `nufi-routine` flow.
- `drive` — which department drive the routine reads and writes into.
- `ask` — the `input_value` the run is given.
- `out` — the file written under `_routines/`. `{date}` is the run's local date;
  a name with no placeholder is overwritten each run, which is a legitimate
  choice for "the current state of X".

A section that names a flow or a drive that does not exist is reported at startup
and **skipped**, not fatal: one bad line must not stop the other schedules.

### Running

Not `POST /api/v1/run/<flow_id>`, which is what `run_flows.py` uses. That call is
synchronous, hands back no handle, and therefore cannot be called off — abandoning
it leaves the run going.

The scheduler drives the job path instead:

| | |
|---|---|
| `POST /api/v1/build/<flow_id>/flow?event_delivery=polling` | returns `{"job_id": …}` |
| `GET /api/v1/build/<job_id>/events` | poll until the run ends |
| `POST /api/v1/build/<job_id>/cancel` | **what makes the deadline real** |

All three take the `x-api-key` already in the box's `.env` as `STUDIO_API_KEY`
(the superuser's): `get_current_user` resolves an API key in the header as well
as a bearer token, so the cancellable path is open to the same credential the
simple one uses.

This is why the scheduler can close the P3 item that is written down as "two
lines in `apps/nufi-agent`, **plus run cancellation**" without touching the fork
at all. The cancel endpoint is already there; nothing on the box was calling it.

Pointing the routine at a drive reuses the node ids `build_flows.py` writes into
`flows.json` (`DRIVE_NODE`, `INDEX_NODE`) as request tweaks, which is how
`run_flows.py` already retargets a recipe at another department — the mechanism
exists and is not invented here.

### State

`/state/` holds the heartbeat and, per schedule, the last tick that was run, so a
box that was off over a scheduled minute does not fire a burst of catch-up runs
when it comes back. A missed run is skipped and logged; it is a report, not a
transaction.

### Surfacing it

- `nufi-box schedule list` — the parsed schedules, when each next fires, and when
  each last ran. Reads the same parser the daemon uses, so the CLI cannot
  disagree with what will actually happen.
- `nufi-box logs nufi-cron` — already works for any compose service.

No new UI. That half of the plan's sentence survives intact.

## What is deliberately not built

- **Event triggers** ("a new file in `onboarding/new/`"). Shipped later, in
  `nufi-cron` itself rather than `nufi-ingest` as assumed above: the thing
  that runs a flow and writes `_routines/` is `Runner`, already here, and a
  second copy of that path in the ingest daemon is exactly what the box's
  one-renderer rule forbids. See
  [`deploy/platform/adapters/nufi-cron/README.md`](../../../deploy/platform/adapters/nufi-cron/README.md).
- **Per-member schedules.** See above.
- **A UI.** See above.
- **Catch-up runs**, retries and backoff. A failed run is logged and the next
  tick tries again.

## Testing

`test_nufi_cron.py`, stdlib `unittest`, no Docker and no live box, in the shape
of `test_ingest.py` and `test_run_box.py` — a fake Studio over
`ThreadingHTTPServer` so the real run path is exercised, not a mock of it.

Cases, each watched failing first:

1. the cron matcher across `*`, ranges, lists and steps, including the two that
   catch a naive implementation: day-of-month and day-of-week are an **or** when
   both are restricted, and a schedule must fire once per matching minute rather
   than once per poll;
2. a run whose output lands in `_routines/` under the named drive, with `{date}`
   filled;
3. a second tick while a run is in flight is skipped, not queued;
4. a run that exceeds the timeout is **cancelled at Studio** — the fake asserts
   the cancel call arrives, because a test that only checks the daemon stopped
   waiting would pass against the version that leaves the box generating;
5. a section naming a missing flow is skipped and the others still run;
6. a box that was off across several scheduled minutes fires **once**, not once
   per missed tick;
7. `nufi-ingest` does not embed anything under `_routines/` — added to
   `test_ingest.py`, where the walker lives.

## Migration

None. The sidecar is inert until `schedules.ini` exists; an existing box gains a
stopped-and-empty scheduler and behaves exactly as before.
