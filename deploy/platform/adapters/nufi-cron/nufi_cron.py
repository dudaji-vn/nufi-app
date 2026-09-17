#!/usr/bin/env python3
"""nufi-cron — runs the box's department routines on a schedule.

A routine is a Studio flow tagged `nufi-routine`, created by
`build_flows.py --box` under the box's superuser. Until now one only ran when a
person opened Studio and pressed a button, which is no use for "the weekly
report, every Friday at five" -- or "the onboarding checklist, when a new
hire's file lands in the folder".

A schedules.ini section has exactly one trigger: `cron`, on a clock, or
`watch`, a folder relative to the drive that fires a run when a file appears
in it and settles (see `Daemon._tick_watch`). Both live in one file and one
daemon on purpose -- the thing that runs a flow and writes `_routines/` is
`Runner` here, and a second copy of that path in nufi-ingest (which already
watches the drives for its own reasons) is exactly what the box's
one-renderer rule forbids.

The schedule lives in `schedules.ini` on the box rather than on the flow, because
routines are copied per member: a schedule attached to a member's copy would run
once per member and write the same department report eight times. See
`docs/superpowers/specs/2026-09-14-box-scheduled-routines-design.md`.

Output is a file under `<drive>/_routines/`, which `nufi-ingest` is told to skip
— a weekly report that is embedded becomes knowledge the next weekly report is
drafted from, and cites itself a little more confidently each week.

Stdlib only, like nufi-ingest, so the image stays small and multi-arch.
"""
from __future__ import annotations

import configparser
import dataclasses
import datetime
import gzip
import json
import logging
import os
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.request

LOG = logging.getLogger("nufi-cron")

# The folder a routine writes into, inside the department's own drive. Shared
# with nufi-ingest, which refuses to embed anything under it.
OUTPUT_DIR = "_routines"

# The tag build_flows.py puts on a routine; the canonical set is what a
# superuser owns wearing it, the same rule nufi/member_routines.py uses.
ROUTINE_TAG = "nufi-routine"

FIELDS = ("minute", "hour", "dom", "month", "dow")
BOUNDS = {"minute": (0, 59), "hour": (0, 23), "dom": (1, 31), "month": (1, 12), "dow": (0, 7)}


class Cron:
    """Five crontab fields, and whether a given minute matches them."""

    def __init__(self, sets, dom_restricted, dow_restricted, text):
        self._sets = sets
        self._dom_restricted = dom_restricted
        self._dow_restricted = dow_restricted
        self.text = text

    @classmethod
    def parse(cls, text):
        parts = text.split()
        if len(parts) != 5:
            raise ValueError(f"a cron expression has five fields, got {len(parts)}: {text!r}")
        sets = {}
        for name, part in zip(FIELDS, parts, strict=True):
            try:
                sets[name] = cls._field(part, *BOUNDS[name])
            except ValueError as exc:
                raise ValueError(f"{exc} in the {name} field of {text!r}") from None
        # Sunday is 0 or 7 in crontab(5); a table indexed 0-6 drops 7 silently.
        if 7 in sets["dow"]:
            sets["dow"].add(0)
        return cls(sets, parts[2] != "*", parts[4] != "*", text)

    @staticmethod
    def _field(part, low, high):
        out = set()
        for piece in part.split(","):
            step = 1
            if "/" in piece:
                piece, _, raw_step = piece.partition("/")
                if not raw_step.isdigit() or int(raw_step) < 1:
                    raise ValueError(f"bad step {raw_step!r}")
                step = int(raw_step)
            if piece == "*":
                start, end = low, high
            elif "-" in piece.lstrip("-"):
                a, _, b = piece.partition("-")
                if not (a.isdigit() and b.isdigit()):
                    raise ValueError(f"bad range {piece!r}")
                start, end = int(a), int(b)
            elif piece.isdigit():
                start = end = int(piece)
            else:
                raise ValueError(f"bad value {piece!r}")
            if start < low or end > high or start > end:
                raise ValueError(f"{piece!r} is outside {low}-{high}")
            out.update(range(start, end + 1, step))
        if not out:
            raise ValueError(f"{part!r} matches nothing")
        return out

    def matches(self, when: datetime.datetime) -> bool:
        if when.minute not in self._sets["minute"]:
            return False
        if when.hour not in self._sets["hour"]:
            return False
        if when.month not in self._sets["month"]:
            return False
        dom_hit = when.day in self._sets["dom"]
        # Python's Monday=0 against cron's Sunday=0.
        dow_hit = ((when.weekday() + 1) % 7) in self._sets["dow"]
        # crontab(5): when BOTH day fields are restricted a day matching either
        # one fires. Treating this as an `and` turns "the 1st, and every Monday"
        # into "a Monday that is also the 1st" -- a few times a year instead of
        # weekly, and invisible in any test that leaves one field as `*`.
        if self._dom_restricted and self._dow_restricted:
            return dom_hit or dow_hit
        return dom_hit and dow_hit


def _bare_name(file: str) -> str:
    """The triggering file's name, safe to splice into `ask` or `out`: no
    directory components (a watch folder's own subfolders must not leak into
    a path), and never starting with a dot -- a hidden file is filtered out
    of the scan before this is ever called, but a name is not trusted twice.
    """
    name = pathlib.PurePosixPath(file).name
    return name.lstrip(".") or name


@dataclasses.dataclass
class Schedule:
    name: str
    flow: str
    drive: str
    ask: str
    out: str
    cron: Cron | None = None
    watch: str | None = None

    def filename(self, when: datetime.datetime, file: str | None = None) -> str:
        name = self.out.replace("{date}", when.strftime("%Y-%m-%d"))
        if file is not None:
            # {file} in `out` is the STEM: "kim-minsu.pdf" -> "kim-minsu",
            # so `onboarding-{file}-{date}.md` reads as a name, not a name
            # with the original extension riding along inside it.
            name = name.replace("{file}", pathlib.PurePosixPath(_bare_name(file)).stem)
        return name

    def ask_for(self, file: str | None = None) -> str:
        if file is None:
            return self.ask
        # {file} in `ask` is the full NAME: the question should name the
        # actual file a person just dropped in the folder.
        return self.ask.replace("{file}", _bare_name(file))


REQUIRED = ("flow", "drive", "ask", "out")


def _bad_watch(value: str) -> bool:
    """`watch` validated like `out`: relative, no `..`, no leading `/` or
    `.`, and not under `_routines` -- nufi-cron's own output folder, which
    must never be watched back into a run."""
    if not value or value.startswith("/") or value.startswith("."):
        return True
    parts = pathlib.PurePosixPath(value).parts
    if ".." in parts:
        return True
    return parts[0] == OUTPUT_DIR


def load_schedules(path):
    """Read `schedules.ini`. Returns (schedules, problems).

    A section that cannot be understood is reported and dropped rather than
    raised: one typo must not stop the box's other reports, and a daemon that
    refuses to start is a worse failure than a schedule that is visibly absent
    from `nufi-box schedule list`.
    """
    path = pathlib.Path(path)
    if not path.exists():
        return [], []
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error as exc:
        return [], [f"{path}: {exc}"]

    schedules, problems = [], []
    for name in parser.sections():
        section = parser[name]
        missing = [k for k in REQUIRED if not (section.get(k) or "").strip()]
        if missing:
            problems.append(f"[{name}]: missing {', '.join(missing)}")
            continue
        out = section["out"].strip()
        # `out` is a name, not a path: it comes from a file a person edits, and
        # it is joined onto a drive directory.
        if "/" in out or "\\" in out or out.startswith("."):
            problems.append(f"[{name}]: out must be a bare file name, got {out!r}")
            continue
        cron_text = (section.get("cron") or "").strip()
        watch_text = (section.get("watch") or "").strip()
        if bool(cron_text) == bool(watch_text):
            problems.append(
                f"[{name}]: exactly one of cron or watch is required, "
                f"got {'both' if cron_text else 'neither'}")
            continue
        cron = watch = None
        if cron_text:
            try:
                cron = Cron.parse(cron_text)
            except ValueError as exc:
                problems.append(f"[{name}]: {exc}")
                continue
        else:
            watch = watch_text.rstrip("/")
            if _bad_watch(watch):
                problems.append(
                    f"[{name}]: watch must be a folder relative to the drive, "
                    f"got {watch_text!r}")
                continue
        schedules.append(Schedule(
            name=name,
            flow=section["flow"].strip(),
            drive=section["drive"].strip(),
            ask=section["ask"].strip(),
            out=out,
            cron=cron,
            watch=watch,
        ))
    return schedules, problems


# The two nodes a routine's drive lives on, as `build_flows.py` names them.
# Kept in step with that file: if the ids drift, a scheduled run answers out of
# whichever drive the flow happened to be saved with and the report still looks
# right, which is the worst shape a bug can take here.
DRIVE_NODE = "Directory-drive"
INDEX_NODE = "LocalDB-index"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")


@dataclasses.dataclass
class Config:
    studio_url: str
    api_key: str
    drives_dir: pathlib.Path
    state_dir: pathlib.Path
    run_timeout: float = 900.0
    poll_interval: float = 2.0
    schedules_path: pathlib.Path | None = None
    tick_interval: float = 20.0


class StudioError(RuntimeError):
    pass


def _unzip(body):
    """Studio gzips its responses, and urllib does not ask it not to.

    Found by pointing this daemon at the real box: every tick failed with
    "'utf-8' codec can't decode byte 0x8b in position 1" -- 1f 8b is a gzip
    header. `run_flows.py` carries the same two lines for the same reason. A
    fake server that answers in plain JSON cannot catch this, which is why the
    test below makes one response gzipped.
    """
    if body[:2] == b"\x1f\x8b":
        return gzip.decompress(body)
    return body


class Runner:
    """Starts one routine, waits for it, and writes what it said to the drive."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    # --- transport -------------------------------------------------------
    def _call(self, method, path, body=None, timeout=60):
        url = f"{self.cfg.studio_url.rstrip('/')}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("x-api-key", self.cfg.api_key)
        req.add_header("User-Agent", UA)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, _unzip(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _unzip(exc.read())

    def _json(self, method, path, body=None, timeout=60):
        code, raw = self._call(method, path, body, timeout)
        if code >= 400:
            raise StudioError(f"{method} {path} -> {code}: {raw[:200].decode('utf-8', 'replace')}")
        return json.loads(raw or b"null")

    # --- the pieces of a run ---------------------------------------------
    def flow_id_for(self, name):
        """The superuser's routine of that name.

        Deliberately not a member's copy: members each own a copy of every
        routine, and a department's report belongs to the department.  This
        credential is the superuser's, so the listing it gets back is the
        canonical set.
        """
        flows = self._json("GET", "/api/v1/flows/?get_all=true&header_flows=true")
        for flow in flows or []:
            if flow.get("name") == name and ROUTINE_TAG in (flow.get("tags") or []):
                return flow["id"]
        raise StudioError(f"no routine named {name!r} on this box")

    def graph_for(self, flow_id, drive):
        """The flow's graph, pointed at `drive`.

        The build endpoint takes no `tweaks` -- that is the simple /run call's
        parameter -- so retargeting is a patched graph rather than an override.
        The vector collection moves with the path, or the report is written from
        one department's files and another's index.
        """
        flow = self._json("GET", f"/api/v1/flows/{flow_id}")
        data = flow.get("data") or {}
        wanted = {
            DRIVE_NODE: ("path", f"/drives/{drive}"),
            INDEX_NODE: ("collection_name", f"nufi-{drive}"),
        }
        for node in data.get("nodes") or []:
            field = wanted.get(node.get("id"))
            if not field:
                continue
            key, value = field
            template = node.setdefault("data", {}).setdefault("node", {}).setdefault("template", {})
            template.setdefault(key, {})["value"] = value
        return data

    def start(self, flow_id, graph, ask):
        body = {"inputs": {"input_value": ask, "type": "chat"}, "data": graph}
        out = self._json(
            "POST", f"/api/v1/build/{flow_id}/flow?event_delivery=polling", body)
        job_id = (out or {}).get("job_id")
        if not job_id:
            raise StudioError(f"the build returned no job_id: {str(out)[:160]}")
        return job_id

    def cancel(self, job_id):
        """Stop the run on the box, not merely stop listening to it.

        Abandoning the socket leaves the run generating with nobody waiting --
        holding the one model on the box against every other question. This is
        the call that makes the deadline mean something.
        """
        try:
            self._json("POST", f"/api/v1/build/{job_id}/cancel", {})
        except (StudioError, urllib.error.URLError, OSError) as exc:
            LOG.error("could not cancel %s: %s", job_id, exc)

    def collect(self, job_id, deadline):
        """Poll until the run ends. Returns the text, or None if it timed out."""
        said = []
        while time.monotonic() < deadline:
            code, raw = self._call(
                "GET", f"/api/v1/build/{job_id}/events", timeout=30)
            if code >= 400:
                raise StudioError(f"events -> {code}: {raw[:160].decode('utf-8', 'replace')}")
            for line in (raw or b"").decode("utf-8", "replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = event.get("event")
                data = event.get("data") or {}
                if kind == "add_message":
                    text = data.get("text")
                    if text and data.get("sender") != "User":
                        said.append(text)
                elif kind == "error":
                    raise StudioError(f"the run reported an error: {str(data)[:200]}")
                elif kind == "end":
                    return "\n".join(said).strip()
            time.sleep(self.cfg.poll_interval)
        return None

    def write(self, schedule, when, text, file=None):
        folder = pathlib.Path(self.cfg.drives_dir) / schedule.drive / OUTPUT_DIR
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / schedule.filename(when, file)
        path.write_text(text + "\n", encoding="utf-8")
        return path

    def run_once(self, schedule, when, file=None) -> bool:
        """One run, start to file. Never raises; returns success.

        `file` is the relative path (inside `schedule.watch`) of the file
        that triggered this run, or None for a plain cron schedule. Log lines
        name it, so `nufi-box logs nufi-cron` says which résumé the box was
        answering rather than only which section fired.
        """
        job_id = None
        subject = schedule.name if file is None else f"{schedule.name}: {schedule.watch}/{file}"
        try:
            flow_id = self.flow_id_for(schedule.flow)
            graph = self.graph_for(flow_id, schedule.drive)
            job_id = self.start(flow_id, graph, schedule.ask_for(file))
            deadline = time.monotonic() + self.cfg.run_timeout
            text = self.collect(job_id, deadline)
            if text is None:
                LOG.error("%s: no answer in %ss -- cancelling the run",
                          subject, self.cfg.run_timeout)
                self.cancel(job_id)
                return False
            if not text:
                LOG.error("%s: the run ended without saying anything", subject)
                return False
            path = self.write(schedule, when, text, file)
            if file is None:
                LOG.info("%s: wrote %s (%d chars)", subject, path, len(text))
            else:
                LOG.info("%s -> wrote %s (%d chars)", subject, path, len(text))
            return True
        except (StudioError, urllib.error.URLError, OSError, ValueError) as exc:
            LOG.error("%s: %s", subject, exc)
            if job_id:
                self.cancel(job_id)
            return False


# A file must look identical -- same size, same mtime -- across this many
# consecutive ticks before it is considered done landing. Mirrors
# nufi-ingest's `settle_scans`, for the same reason: a copy in progress, or a
# Samba write still in flight, must not trigger a run on a half-written file.
WATCH_SETTLE_TICKS = 2

# A leading "." catches both dotfiles and Samba/Office lock files
# (".~lock.foo.docx#"); "~$" catches Word/Excel's own temp files
# ("~$foo.docx"), which do not start with a dot.
WATCH_IGNORED_PREFIXES = (".", "~$")


class Daemon(Runner):
    """The loop: which schedules are due this minute, and which are busy."""

    def __init__(self, cfg: Config):
        super().__init__(cfg)
        self._lock = threading.Lock()
        self._inflight = set()
        self._fired = {}
        self._state = pathlib.Path(cfg.state_dir) / "fired.json"
        if self._state.exists():
            try:
                self._fired = json.loads(self._state.read_text())
            except (OSError, json.JSONDecodeError):
                self._fired = {}
        # {schedule_name: {relative_path: mtime}} -- one entry per file a
        # `watch` section has ever fired for (or recorded on its first scan).
        # Persisted, unlike `_pending` below, so a restart does not treat
        # every file already on the drive as new again.
        self._seen = {}
        self._seen_state = pathlib.Path(cfg.state_dir) / "seen.json"
        if self._seen_state.exists():
            try:
                self._seen = json.loads(self._seen_state.read_text())
            except (OSError, json.JSONDecodeError):
                self._seen = {}
        # {(schedule_name, relative_path): (size, mtime, consecutive ticks
        # seen unchanged)} -- in-memory only. A file mid-settle when the
        # daemon restarts simply starts its count over, which is fine: it is
        # not yet `_seen`, so nothing has fired for it either way.
        self._pending = {}
        # Schedule names whose watch folder was missing on the last tick that
        # noticed, so the "does not exist yet" line is logged once rather
        # than once per tick_interval until someone creates the folder.
        self._missing_watch = set()

    def _remember(self, name, stamp):
        self._fired[name] = stamp
        try:
            self._state.write_text(json.dumps(self._fired))
        except OSError as exc:
            LOG.warning("could not record the last run: %s", exc)

    def _remember_seen(self):
        try:
            self._seen_state.write_text(json.dumps(self._seen))
        except OSError as exc:
            LOG.warning("could not record the watched files: %s", exc)

    def tick(self, schedules, now):
        """Fire whatever is due at `now`: cron sections on their minute,
        watch sections when a file in their folder has settled."""
        for schedule in schedules:
            if schedule.cron is not None:
                self._tick_cron(schedule, now)
            else:
                self._tick_watch(schedule, now)

    def _tick_cron(self, schedule, now):
        """A minute already fired is remembered, because the loop polls many
        times a minute and a report is not wanted once per poll. A schedule
        already running is skipped, because the box answers one question at a
        time and piling runs on it is how a weekly report that overruns its
        own period takes the model down.

        Nothing is caught up. A box that was off over a scheduled minute has
        missed that report, and firing five hours of them at boot is worse
        than the gap.
        """
        if not schedule.cron.matches(now):
            return
        stamp = now.strftime("%Y-%m-%dT%H:%M")
        with self._lock:
            if self._fired.get(schedule.name) == stamp:
                return
            if schedule.name in self._inflight:
                LOG.warning("%s is still running; skipping %s", schedule.name, stamp)
                return
            self._inflight.add(schedule.name)
            self._remember(schedule.name, stamp)
        try:
            self.run_once(schedule, now)
        finally:
            with self._lock:
                self._inflight.discard(schedule.name)

    def _watch_listing(self, schedule):
        """Every non-ignored file currently in `schedule`'s watched folder, as
        {relative_path: (path, size, mtime)}. None if the folder does not
        exist yet -- a box freshly installed has no `onboarding/new` until
        someone creates it on the share, and that is not an error."""
        folder = pathlib.Path(self.cfg.drives_dir) / schedule.drive / schedule.watch
        if not folder.is_dir():
            if schedule.name not in self._missing_watch:
                LOG.error("%s: watch folder %s does not exist yet", schedule.name, folder)
                self._missing_watch.add(schedule.name)
            return None
        self._missing_watch.discard(schedule.name)
        out = {}
        for p in sorted(folder.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(folder).as_posix()
            parts = pathlib.PurePosixPath(rel).parts
            if any(part.startswith(WATCH_IGNORED_PREFIXES) for part in parts):
                continue
            if OUTPUT_DIR in parts:
                continue
            st = p.stat()
            out[rel] = (p, int(st.st_size), int(st.st_mtime))
        return out

    def _tick_watch(self, schedule, now):
        """The first scan of a watch folder records everything already there
        and fires nothing -- the same "nothing is caught up" rule cron
        follows: a folder with forty résumés in it at boot must not launch
        forty runs. After that, a file not matching its last-seen mtime is
        new or edited, and has to hold still (same size and mtime) for
        `WATCH_SETTLE_TICKS` in a row before it fires. Single-flight per
        section, exactly as cron: `_inflight` is the same set.
        """
        listing = self._watch_listing(schedule)
        if listing is None:
            return
        seen = self._seen.get(schedule.name)
        if seen is None:
            self._seen[schedule.name] = {rel: mtime for rel, (_, _, mtime) in listing.items()}
            self._remember_seen()
            return
        fire = None
        for rel in sorted(listing):
            _, size, mtime = listing[rel]
            if seen.get(rel) == mtime:
                self._pending.pop((schedule.name, rel), None)
                continue
            key = (schedule.name, rel)
            prev = self._pending.get(key)
            streak = prev[2] + 1 if prev and prev[0] == size and prev[1] == mtime else 1
            self._pending[key] = (size, mtime, streak)
            if fire is None and streak >= WATCH_SETTLE_TICKS:
                fire = (rel, mtime)
        if fire is None:
            return
        rel, mtime = fire
        with self._lock:
            if schedule.name in self._inflight:
                return
            self._inflight.add(schedule.name)
        try:
            self.run_once(schedule, now, file=rel)
        finally:
            with self._lock:
                self._inflight.discard(schedule.name)
            # Marked seen whether the run succeeded or not: a broken flow
            # must not re-run every tick, and editing the file afterwards (a
            # new mtime) is what makes it eligible again.
            self._pending.pop((schedule.name, rel), None)
            self._seen[schedule.name][rel] = mtime
            self._remember_seen()


def _env_config():
    state = pathlib.Path(os.environ.get("NUFI_STATE_DIR", "/state"))
    return Config(
        studio_url=os.environ.get("NUFI_STUDIO_URL", "http://studio:7860"),
        api_key=os.environ.get("STUDIO_API_KEY", ""),
        drives_dir=pathlib.Path(os.environ.get("NUFI_DRIVES_DIR", "/drives")),
        state_dir=state,
        run_timeout=float(os.environ.get("NUFI_CRON_RUN_TIMEOUT", "900")),
        poll_interval=float(os.environ.get("NUFI_CRON_POLL_INTERVAL", "2")),
        schedules_path=pathlib.Path(
            os.environ.get("NUFI_SCHEDULES", "/config/schedules.ini")),
        tick_interval=float(os.environ.get("NUFI_CRON_TICK_INTERVAL", "20")),
    )


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = _env_config()
    if not cfg.api_key:
        LOG.error("STUDIO_API_KEY is empty; nothing can be run without it")
        return 2
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    daemon = Daemon(cfg)

    # The config is re-read every tick rather than at boot, so editing
    # schedules.ini does not need a restart -- the box has no UI for this and
    # `nufi-box restart` to add a report would be a poor answer.
    seen_problems = set()
    LOG.info("watching %s, every %ss", cfg.schedules_path, cfg.tick_interval)
    while True:
        schedules, problems = load_schedules(cfg.schedules_path)
        for problem in problems:
            if problem not in seen_problems:
                seen_problems.add(problem)
                LOG.error("%s", problem)
        try:
            daemon.tick(schedules, datetime.datetime.now())
        except Exception:  # noqa: BLE001 -- a daemon that dies stops every report
            LOG.exception("tick failed")
        # The heartbeat is written after the tick, so the Docker healthcheck
        # reports a daemon that is looping rather than one that is merely up.
        (cfg.state_dir / "heartbeat").write_text(str(time.time()))
        time.sleep(cfg.tick_interval)


if __name__ == "__main__":
    sys.exit(main() or 0)
