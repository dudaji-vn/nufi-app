#!/usr/bin/env python3
"""Stdlib unit test for nufi_cron.py (no Docker, no deps, no live box).

Two halves. The first is pure logic — parsing `schedules.ini` and deciding
whether a minute matches a cron expression — and needs nothing but a clock the
test controls. The second stands up a fake Studio over ThreadingHTTPServer and
drives the real build/poll/cancel path against it, so what is exercised is the
sequence of calls the daemon will actually make rather than a mock of it.

Run:  python3 test_nufi_cron.py     (exit 0 = PASS)
"""
import datetime
import gzip
import http.server
import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import nufi_cron  # noqa: E402


def at(y, mo, d, h, mi):
    return datetime.datetime(y, mo, d, h, mi)


class CronMatching(unittest.TestCase):
    def test_a_star_field_matches_every_value(self):
        every = nufi_cron.Cron.parse("* * * * *")
        self.assertTrue(every.matches(at(2026, 9, 14, 0, 0)))
        self.assertTrue(every.matches(at(2026, 9, 14, 13, 37)))

    def test_a_number_matches_only_itself(self):
        five_pm = nufi_cron.Cron.parse("0 17 * * *")
        self.assertTrue(five_pm.matches(at(2026, 9, 14, 17, 0)))
        self.assertFalse(five_pm.matches(at(2026, 9, 14, 17, 1)))
        self.assertFalse(five_pm.matches(at(2026, 9, 14, 16, 0)))

    def test_ranges_lists_and_steps(self):
        c = nufi_cron.Cron.parse("*/15 9-17 * * 1,3,5")
        # 2026-09-14 is a Monday.
        self.assertTrue(c.matches(at(2026, 9, 14, 9, 0)))
        self.assertTrue(c.matches(at(2026, 9, 14, 17, 45)))
        self.assertFalse(c.matches(at(2026, 9, 14, 9, 7)), "*/15 should not match :07")
        self.assertFalse(c.matches(at(2026, 9, 14, 8, 0)), "9-17 should not match 08:00")
        # Tuesday is not in 1,3,5.
        self.assertFalse(c.matches(at(2026, 9, 15, 9, 0)))

    def test_sunday_is_both_zero_and_seven(self):
        """crontab(5) allows either, and a table indexed 0-6 silently drops 7."""
        # 2026-09-20 is a Sunday.
        for expr in ("0 9 * * 0", "0 9 * * 7"):
            with self.subTest(expr=expr):
                self.assertTrue(nufi_cron.Cron.parse(expr).matches(at(2026, 9, 20, 9, 0)))

    def test_day_of_month_and_day_of_week_are_an_or_not_an_and(self):
        """The rule everyone gets wrong, and crontab(5) is explicit about it.

        When BOTH day fields are restricted, a day matching either one fires.
        Treating them as an `and` makes "the 1st, and every Monday" mean "a
        Monday that is also the 1st" — a schedule that fires a few times a year
        instead of weekly, and looks fine in every test that uses `*`.
        """
        c = nufi_cron.Cron.parse("0 9 1 * 1")
        self.assertTrue(c.matches(at(2026, 9, 1, 9, 0)), "the 1st (a Tuesday) should fire")
        self.assertTrue(c.matches(at(2026, 9, 14, 9, 0)), "a Monday should fire")
        self.assertFalse(c.matches(at(2026, 9, 15, 9, 0)), "neither the 1st nor a Monday")

        # ...and when only one of them is restricted it is a plain and.
        only_dom = nufi_cron.Cron.parse("0 9 1 * *")
        self.assertFalse(only_dom.matches(at(2026, 9, 14, 9, 0)))

    def test_a_malformed_expression_is_rejected_with_the_text_in_the_message(self):
        for bad in ("* * * *", "* * * * * *", "61 * * * *", "* 25 * * *", "a * * * *"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError) as caught:
                    nufi_cron.Cron.parse(bad)
                self.assertIn(bad, str(caught.exception))


def _write_ini(text):
    d = pathlib.Path(tempfile.mkdtemp())
    p = d / "schedules.ini"
    p.write_text(text, encoding="utf-8")
    return p


class ConfigParsing(unittest.TestCase):
    def _write(self, text):
        return _write_ini(text)

    def test_a_section_becomes_a_schedule(self):
        p = self._write(
            "[legal-weekly]\n"
            "cron  = 0 17 * * 5\n"
            "flow  = Routine · weekly report from the drive\n"
            "drive = legal\n"
            "ask   = 이번 주 주간보고 초안을 써줘.\n"
            "out   = weekly-report-{date}.md\n"
        )
        schedules, problems = nufi_cron.load_schedules(p)
        self.assertEqual(problems, [])
        self.assertEqual(len(schedules), 1)
        s = schedules[0]
        self.assertEqual(s.name, "legal-weekly")
        self.assertEqual(s.flow, "Routine · weekly report from the drive")
        self.assertEqual(s.drive, "legal")
        self.assertEqual(s.ask, "이번 주 주간보고 초안을 써줘.")
        self.assertEqual(s.out, "weekly-report-{date}.md")
        self.assertTrue(s.cron.matches(at(2026, 9, 18, 17, 0)), "2026-09-18 is a Friday")

    def test_one_bad_section_is_reported_and_the_others_still_load(self):
        """A typo in one schedule must not take the box's other reports down."""
        p = self._write(
            "[good]\ncron = 0 9 * * *\nflow = A\ndrive = legal\nask = q\nout = a.md\n"
            "\n[bad-cron]\ncron = 0 99 * * *\nflow = A\ndrive = legal\nask = q\nout = b.md\n"
            "\n[no-flow]\ncron = 0 9 * * *\ndrive = legal\nask = q\nout = c.md\n"
        )
        schedules, problems = nufi_cron.load_schedules(p)
        self.assertEqual([s.name for s in schedules], ["good"])
        self.assertEqual(len(problems), 2, problems)
        joined = " ".join(problems)
        self.assertIn("bad-cron", joined)
        self.assertIn("no-flow", joined)

    def test_a_missing_file_is_an_empty_schedule_not_a_crash(self):
        """The sidecar ships inert: a box with no schedules.ini behaves as before."""
        schedules, problems = nufi_cron.load_schedules(pathlib.Path("/nonexistent/schedules.ini"))
        self.assertEqual(schedules, [])
        self.assertEqual(problems, [])

    def test_the_output_name_takes_the_run_date(self):
        p = self._write(
            "[s]\ncron = 0 9 * * *\nflow = A\ndrive = legal\nask = q\n"
            "out = weekly-report-{date}.md\n"
        )
        s = nufi_cron.load_schedules(p)[0][0]
        self.assertEqual(s.filename(at(2026, 9, 14, 9, 0)), "weekly-report-2026-09-14.md")

    def test_an_output_name_without_a_placeholder_is_left_alone(self):
        p = self._write("[s]\ncron = 0 9 * * *\nflow = A\ndrive = legal\nask = q\nout = now.md\n")
        s = nufi_cron.load_schedules(p)[0][0]
        self.assertEqual(s.filename(at(2026, 9, 14, 9, 0)), "now.md")

    def test_an_output_name_cannot_climb_out_of_the_drive(self):
        """`out` comes from a file a person edits; it is a name, not a path."""
        for bad in ("../escape.md", "/etc/passwd", "sub/dir.md"):
            with self.subTest(bad=bad):
                p = self._write(
                    f"[s]\ncron = 0 9 * * *\nflow = A\ndrive = legal\nask = q\nout = {bad}\n")
                schedules, problems = nufi_cron.load_schedules(p)
                self.assertEqual(schedules, [], f"{bad} should not have loaded")
                self.assertTrue(problems)


class WatchSections(unittest.TestCase):
    """`watch` is the other half of a section's trigger: exactly one of
    `cron` or `watch`, and `watch` is a folder relative to the drive."""

    def test_a_watch_section_becomes_a_schedule(self):
        p = _write_ini(
            "[hr-onboarding]\n"
            "watch = onboarding/new\n"
            "flow  = HR · leave entitlement\n"
            "drive = hr\n"
            "ask   = onboarding/new/{file} 에 새 입사자의 서류가 들어왔습니다.\n"
            "out   = onboarding-{file}-{date}.md\n"
        )
        schedules, problems = nufi_cron.load_schedules(p)
        self.assertEqual(problems, [])
        self.assertEqual(len(schedules), 1)
        s = schedules[0]
        self.assertIsNone(s.cron)
        self.assertEqual(s.watch, "onboarding/new")
        self.assertEqual(s.flow, "HR · leave entitlement")

    def test_a_watch_folder_with_a_trailing_slash_is_stripped(self):
        p = _write_ini(
            "[s]\nwatch = onboarding/new/\nflow = A\ndrive = hr\nask = q\nout = o.md\n")
        s = nufi_cron.load_schedules(p)[0][0]
        self.assertEqual(s.watch, "onboarding/new")

    def test_both_cron_and_watch_in_one_section_is_a_problem(self):
        """A section names exactly one trigger; naming both is ambiguous
        about which one wins, so neither does."""
        p = _write_ini(
            "[s]\ncron = 0 9 * * *\nwatch = onboarding/new\n"
            "flow = A\ndrive = hr\nask = q\nout = o.md\n"
        )
        schedules, problems = nufi_cron.load_schedules(p)
        self.assertEqual(schedules, [])
        self.assertTrue(problems)

    def test_neither_cron_nor_watch_is_a_problem(self):
        p = _write_ini("[s]\nflow = A\ndrive = hr\nask = q\nout = o.md\n")
        schedules, problems = nufi_cron.load_schedules(p)
        self.assertEqual(schedules, [])
        self.assertTrue(problems)

    def test_a_watch_folder_cannot_climb_out_of_the_drive(self):
        """Validated like `out`: relative, no `..`, no leading `/` or `.`,
        and not under `_routines` (nufi-cron's own output folder)."""
        for bad in ("../x", "/x", "_routines/x"):
            with self.subTest(bad=bad):
                p = _write_ini(
                    f"[s]\nwatch = {bad}\nflow = A\ndrive = hr\nask = q\nout = o.md\n")
                schedules, problems = nufi_cron.load_schedules(p)
                self.assertEqual(schedules, [], f"{bad} should not have loaded")
                self.assertTrue(problems)


# --- the fake Studio ------------------------------------------------------
#
# The daemon's whole argument for using the build/job path instead of the
# simple /run call is that a job can be cancelled. A test that mocked the
# client would prove nothing about that, so this stands up the three real
# endpoints and asserts on the sequence of calls that arrives.

FLOW_ID = "11111111-2222-3333-4444-555555555555"
JOB_ID = "job-abc"
ROUTINE_NAME = "Routine · weekly report from the drive"


class FakeStudio(http.server.BaseHTTPRequestHandler):
    calls = []
    posted_graphs = []
    hang = False          # never finish the run, so the deadline has to bite
    cancelled = []

    def log_message(self, *a):
        pass

    def _json(self, code, obj, gzipped=False):
        body = json.dumps(obj).encode()
        headers = [("Content-Type", "application/json")]
        if gzipped:
            body = gzip.compress(body)
            headers.append(("Content-Encoding", "gzip"))
        self.send_response(code)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ndjson(self, lines):
        body = "\n".join(json.dumps(x) for x in lines).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _gate(self):
        """Studio takes the superuser's key in a header; so must the daemon."""
        if self.headers.get("x-api-key") != "test-key":
            self._json(403, {"detail": "no api key"})
            return False
        return True

    def do_GET(self):
        if not self._gate():
            return
        FakeStudio.calls.append(("GET", self.path.split("?")[0]))
        if self.path.startswith("/api/v1/flows/?"):
            # Gzipped on purpose: the real Studio compresses its responses and
            # urllib does not ask it not to, so the daemon's first live tick
            # died on "'utf-8' codec can't decode byte 0x8b in position 1".
            # A fake that only ever answers in plain JSON is a fake that lets
            # that ship twice.
            return self._json(200, [
                {"id": FLOW_ID, "name": ROUTINE_NAME, "tags": ["nufi-routine"],
                 "is_component": False, "folder_id": "f1"},
                {"id": "other", "name": "Legal · risky clause review", "tags": [],
                 "is_component": False, "folder_id": "f1"},
            ], gzipped=True)
        if self.path.startswith(f"/api/v1/flows/{FLOW_ID}"):
            return self._json(200, {"id": FLOW_ID, "name": ROUTINE_NAME, "data": {
                "nodes": [
                    {"id": nufi_cron.DRIVE_NODE,
                     "data": {"node": {"template": {"path": {"value": "/drives/legal"}}}}},
                    {"id": nufi_cron.INDEX_NODE,
                     "data": {"node": {"template": {"collection_name": {"value": "nufi-legal"}}}}},
                ],
                "edges": [], "viewport": {},
            }})
        if self.path.startswith(f"/api/v1/build/{JOB_ID}/events"):
            if FakeStudio.hang:
                return self._ndjson([])       # still working, nothing to report
            return self._ndjson([
                {"event": "add_message",
                 "data": {"sender": "Machine", "text": "이번 주 한 일: ... (근거: a.txt)"}},
                {"event": "end", "data": {}},
            ])
        return self._json(404, {"detail": "no such route"})

    def do_POST(self):
        if not self._gate():
            return
        path = self.path.split("?")[0]
        FakeStudio.calls.append(("POST", path))
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if path == f"/api/v1/build/{FLOW_ID}/flow":
            FakeStudio.posted_graphs.append(body)
            return self._json(200, {"job_id": JOB_ID})
        if path == f"/api/v1/build/{JOB_ID}/cancel":
            FakeStudio.cancelled.append(JOB_ID)
            return self._json(200, {"cancelled": True})
        return self._json(404, {"detail": "no such route"})


class Running(unittest.TestCase):
    def setUp(self):
        FakeStudio.calls = []
        FakeStudio.posted_graphs = []
        FakeStudio.cancelled = []
        FakeStudio.hang = False
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeStudio)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.root = pathlib.Path(tempfile.mkdtemp())
        (self.root / "drives" / "legal").mkdir(parents=True)
        (self.root / "state").mkdir()
        self.addCleanup(self.server.shutdown)

    def _runner(self, **kw):
        return nufi_cron.Runner(nufi_cron.Config(
            studio_url=self.base,
            api_key="test-key",
            drives_dir=self.root / "drives",
            state_dir=self.root / "state",
            run_timeout=kw.pop("run_timeout", 30),
            poll_interval=kw.pop("poll_interval", 0.01),
            **kw))

    def _schedule(self, out="weekly-report-{date}.md"):
        return nufi_cron.Schedule(
            name="legal-weekly", cron=nufi_cron.Cron.parse("0 17 * * 5"),
            flow=ROUTINE_NAME, drive="legal", ask="주간보고 초안", out=out)

    def test_a_run_writes_the_answer_into_the_drives_routines_folder(self):
        runner = self._runner()
        ok = runner.run_once(self._schedule(), at(2026, 9, 18, 17, 0))
        self.assertTrue(ok, "the run should have succeeded")
        legal = self.root / "drives" / "legal"
        written = legal / nufi_cron.OUTPUT_DIR / "weekly-report-2026-09-18.md"
        self.assertTrue(written.exists(), sorted(p.name for p in legal.rglob("*")))
        self.assertIn("근거: a.txt", written.read_text(encoding="utf-8"))

    def test_the_graph_it_posts_is_pointed_at_the_schedules_own_drive(self):
        """The routines are department-agnostic; the schedule says which drive.

        The build endpoint takes no `tweaks` (that is the /run call's parameter),
        so the retarget has to be a patched graph. A daemon that posted the flow
        unchanged would answer every department's report out of whichever drive
        the flow was saved with, and the file name would still look right.
        """
        runner = self._runner()
        schedule = self._schedule()
        schedule.drive = "hr"
        (self.root / "drives" / "hr").mkdir()
        runner.run_once(schedule, at(2026, 9, 18, 17, 0))
        self.assertEqual(len(FakeStudio.posted_graphs), 1)
        nodes = FakeStudio.posted_graphs[0]["data"]["nodes"]
        by_id = {n["id"]: n for n in nodes}
        self.assertEqual(
            by_id[nufi_cron.DRIVE_NODE]["data"]["node"]["template"]["path"]["value"],
            "/drives/hr")
        self.assertEqual(
            by_id[nufi_cron.INDEX_NODE]["data"]["node"]["template"]["collection_name"]["value"],
            "nufi-hr")

    def test_a_run_that_outstays_its_deadline_is_cancelled_at_studio(self):
        """Not merely abandoned.

        run_flows.py says it in its own comment: giving up on the socket does
        not stop the run on the box, which goes on generating with nobody
        listening and holds the model against every other question. A test that
        only asserted the daemon stopped waiting would pass against exactly that
        bug, so it asserts the cancel call arrived.
        """
        FakeStudio.hang = True
        runner = self._runner(run_timeout=0.3)
        ok = runner.run_once(self._schedule(), at(2026, 9, 18, 17, 0))
        self.assertFalse(ok)
        self.assertEqual(FakeStudio.cancelled, [JOB_ID], "the job was never cancelled")
        self.assertIn(("POST", f"/api/v1/build/{JOB_ID}/cancel"), FakeStudio.calls)

    def test_a_schedule_naming_a_flow_the_box_does_not_have_fails_without_raising(self):
        runner = self._runner()
        schedule = self._schedule()
        schedule.flow = "Routine · one that was never built"
        self.assertFalse(runner.run_once(schedule, at(2026, 9, 18, 17, 0)))
        self.assertEqual(FakeStudio.posted_graphs, [], "nothing should have been started")


class Ticking(unittest.TestCase):
    """The loop around the runner: what fires, what is skipped."""

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        (self.root / "state").mkdir()
        self.fired = []

    def _daemon(self):
        d = nufi_cron.Daemon(nufi_cron.Config(
            studio_url="http://unused", api_key="k",
            drives_dir=self.root / "drives", state_dir=self.root / "state",
            run_timeout=1, poll_interval=0.01))
        d.run_once = lambda schedule, when: (self.fired.append((schedule.name, when)) or True)
        return d

    def test_a_matching_minute_fires_once_even_if_the_loop_ticks_many_times(self):
        """The loop polls far more often than once a minute."""
        d = self._daemon()
        s = nufi_cron.Schedule(name="s", cron=nufi_cron.Cron.parse("0 17 * * *"),
                               flow="F", drive="legal", ask="q", out="o.md")
        for second in (0, 5, 30, 59):
            d.tick([s], at(2026, 9, 18, 17, 0).replace(second=second))
        self.assertEqual(len(self.fired), 1, self.fired)

    def test_a_box_that_was_off_across_several_scheduled_minutes_fires_once(self):
        """A report is not a transaction; catching up would be a burst of them."""
        d = self._daemon()
        s = nufi_cron.Schedule(name="s", cron=nufi_cron.Cron.parse("0 * * * *"),
                               flow="F", drive="legal", ask="q", out="o.md")
        d.tick([s], at(2026, 9, 18, 9, 0))
        # ...the box is off for five hours, and comes back on a matching minute.
        d.tick([s], at(2026, 9, 18, 14, 0))
        self.assertEqual(len(self.fired), 2, "the hours in between must not be replayed")
        self.assertEqual([w.hour for _, w in self.fired], [9, 14])

    def test_a_tick_while_the_previous_run_is_still_going_is_skipped(self):
        """Single flight, per schedule.

        A weekly report that takes longer than its own period would otherwise
        pile runs onto a box whose whole problem is that one model answers one
        question at a time.
        """
        d = self._daemon()
        started = threading.Event()
        release = threading.Event()

        def slow(schedule, when):
            started.set()
            release.wait(5)
            self.fired.append((schedule.name, when))
            return True

        d.run_once = slow
        s = nufi_cron.Schedule(name="s", cron=nufi_cron.Cron.parse("* * * * *"),
                               flow="F", drive="legal", ask="q", out="o.md")
        first = threading.Thread(target=d.tick, args=([s], at(2026, 9, 18, 9, 0)))
        first.start()
        self.assertTrue(started.wait(5), "the first run never started")
        d.tick([s], at(2026, 9, 18, 9, 1))     # would fire, but one is in flight
        release.set()
        first.join(5)
        self.assertEqual(len(self.fired), 1, self.fired)


class Watching(unittest.TestCase):
    """Event-triggered routines, through the real Runner path -- fake Studio
    included, so what is exercised is the actual ask sent and the actual file
    written, not a stub of either."""

    def setUp(self):
        FakeStudio.calls = []
        FakeStudio.posted_graphs = []
        FakeStudio.cancelled = []
        FakeStudio.hang = False
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeStudio)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.watched = self.root / "drives" / "hr" / "onboarding" / "new"
        self.watched.mkdir(parents=True)
        (self.root / "state").mkdir()
        self.addCleanup(self.server.shutdown)

    def _daemon(self):
        return nufi_cron.Daemon(nufi_cron.Config(
            studio_url=self.base, api_key="test-key",
            drives_dir=self.root / "drives", state_dir=self.root / "state",
            run_timeout=30, poll_interval=0.01))

    def _schedule(self):
        return nufi_cron.Schedule(
            name="hr-onboarding", watch="onboarding/new", flow=ROUTINE_NAME,
            drive="hr", ask="onboarding/new/{file} 에 새 입사자의 서류가 들어왔습니다.",
            out="onboarding-{file}-{date}.md")

    def test_a_new_file_fires_after_two_stable_ticks_and_writes_the_answer(self):
        d = self._daemon()
        s = self._schedule()
        d.tick([s], at(2026, 9, 18, 9, 0))       # first scan of an empty folder
        (self.watched / "kim-minsu.pdf").write_bytes(b"resume")
        d.tick([s], at(2026, 9, 18, 9, 1))       # seen once, not stable yet
        self.assertEqual(FakeStudio.posted_graphs, [], "must not fire on the first sighting")
        d.tick([s], at(2026, 9, 18, 9, 2))       # stable across two ticks -> fires
        self.assertEqual(len(FakeStudio.posted_graphs), 1)
        ask = FakeStudio.posted_graphs[0]["inputs"]["input_value"]
        self.assertIn("kim-minsu.pdf", ask, "the ask must name the triggering file")
        written = (self.root / "drives" / "hr" / nufi_cron.OUTPUT_DIR
                   / "onboarding-kim-minsu-2026-09-18.md")
        self.assertTrue(written.exists(), sorted(p.name for p in self.watched.parent.rglob("*")))


class WatchTicking(unittest.TestCase):
    """The scanning/settling mechanics around a `watch` section -- run_once
    stubbed out, same as `Ticking` does for cron, since these tests are about
    what fires and when, not about the run itself."""

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        (self.root / "state").mkdir()
        self.fired = []

    def _daemon(self):
        d = nufi_cron.Daemon(nufi_cron.Config(
            studio_url="http://unused", api_key="k",
            drives_dir=self.root / "drives", state_dir=self.root / "state",
            run_timeout=1, poll_interval=0.01))
        d.run_once = lambda schedule, when, file=None: (
            self.fired.append((schedule.name, file)) or True)
        return d

    def _schedule(self, watch="onboarding/new", **kw):
        kw.setdefault("name", "hr-onboarding")
        kw.setdefault("flow", "F")
        kw.setdefault("drive", "hr")
        kw.setdefault("ask", "q {file}")
        kw.setdefault("out", "o-{file}-{date}.md")
        return nufi_cron.Schedule(watch=watch, **kw)

    def _mkwatch(self):
        d = self.root / "drives" / "hr" / "onboarding" / "new"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _touch(self, rel, content=b"x"):
        path = self._mkwatch() / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_the_first_scan_of_a_watch_folder_fires_nothing(self):
        """A folder with forty résumés in it at boot must not launch forty
        runs -- the same 'nothing is caught up' rule cron follows."""
        self._touch("kim-minsu.pdf")
        self._touch("someone-else.pdf")
        d = self._daemon()
        s = self._schedule()
        d.tick([s], at(2026, 9, 18, 9, 0))
        self.assertEqual(self.fired, [], "files already present at boot must not fire")
        for m in range(1, 4):
            d.tick([s], at(2026, 9, 18, 9, m))
        self.assertEqual(self.fired, [], "and must stay quiet on later ticks too")

    def test_a_new_file_fires_after_two_stable_ticks(self):
        d = self._daemon()
        s = self._schedule()
        self._mkwatch()
        d.tick([s], at(2026, 9, 18, 9, 0))       # first scan: empty
        self._touch("kim-minsu.pdf")
        d.tick([s], at(2026, 9, 18, 9, 1))       # seen once
        self.assertEqual(self.fired, [], "must not fire on the first sighting")
        d.tick([s], at(2026, 9, 18, 9, 2))       # stable twice
        self.assertEqual(self.fired, [("hr-onboarding", "kim-minsu.pdf")])

    def test_a_growing_file_does_not_fire_until_it_stops_changing(self):
        d = self._daemon()
        s = self._schedule()
        self._mkwatch()
        d.tick([s], at(2026, 9, 18, 9, 0))
        path = self._touch("kim-minsu.pdf", b"a")
        base = time.time()
        os.utime(path, (base, base))
        d.tick([s], at(2026, 9, 18, 9, 1))
        self.assertEqual(self.fired, [])
        path.write_bytes(b"a longer copy still landing")
        os.utime(path, (base + 5, base + 5))     # a copy still in progress
        d.tick([s], at(2026, 9, 18, 9, 2))
        self.assertEqual(self.fired, [], "a growing file must not fire mid-copy")
        d.tick([s], at(2026, 9, 18, 9, 3))       # unchanged since -> stable
        self.assertEqual(self.fired, [("hr-onboarding", "kim-minsu.pdf")])

    def test_a_fired_file_does_not_fire_again(self):
        d = self._daemon()
        s = self._schedule()
        self._mkwatch()
        d.tick([s], at(2026, 9, 18, 9, 0))
        self._touch("kim-minsu.pdf")
        d.tick([s], at(2026, 9, 18, 9, 1))
        d.tick([s], at(2026, 9, 18, 9, 2))
        self.assertEqual(len(self.fired), 1)
        for m in range(3, 8):
            d.tick([s], at(2026, 9, 18, 9, m))
        self.assertEqual(len(self.fired), 1, "a file already run must not fire again")

    def test_a_restart_does_not_refire_what_was_already_seen(self):
        d = self._daemon()
        s = self._schedule()
        self._mkwatch()
        d.tick([s], at(2026, 9, 18, 9, 0))
        self._touch("kim-minsu.pdf")
        d.tick([s], at(2026, 9, 18, 9, 1))
        d.tick([s], at(2026, 9, 18, 9, 2))
        self.assertEqual(len(self.fired), 1)
        d2 = self._daemon()                      # a fresh Daemon, same state dir
        for m in range(3, 6):
            d2.tick([s], at(2026, 9, 18, 9, m))
        self.assertEqual(len(self.fired), 1, "a restart must not replay an already-fired file")

    def test_hidden_and_office_lock_files_are_ignored(self):
        d = self._daemon()
        s = self._schedule()
        self._mkwatch()
        d.tick([s], at(2026, 9, 18, 9, 0))
        self._touch(".DS_Store")
        self._touch("~$kim-minsu.pdf")
        self._touch(".~lock.kim-minsu.pdf#")
        for m in range(1, 5):
            d.tick([s], at(2026, 9, 18, 9, m))
        self.assertEqual(self.fired, [], "hidden and office-lock files must never fire")

    def test_a_missing_watch_folder_logs_once_and_fires_nothing(self):
        """WARNING, not ERROR: the docs are explicit that a folder appearing
        later is the expected shape, not a failure."""
        d = self._daemon()
        s = self._schedule(watch="onboarding/does-not-exist")
        with self.assertLogs(nufi_cron.LOG, level="WARNING") as cm:
            for m in range(3):
                d.tick([s], at(2026, 9, 18, 9, m))
        self.assertEqual(self.fired, [])
        missing = [line for line in cm.output if "does not exist yet" in line]
        self.assertEqual(len(missing), 1, cm.output)
        self.assertTrue(all(line.startswith("WARNING:") for line in missing), missing)

    def test_a_cron_section_and_a_watch_section_coexist(self):
        d = self._daemon()
        cron_s = nufi_cron.Schedule(name="legal-weekly", cron=nufi_cron.Cron.parse("0 17 * * 5"),
                                    flow="F", drive="legal", ask="q", out="o.md")
        watch_s = self._schedule()
        self._mkwatch()
        d.tick([cron_s, watch_s], at(2026, 9, 18, 17, 0))
        self.assertEqual(self.fired, [("legal-weekly", None)])
        self._touch("kim-minsu.pdf")
        d.tick([cron_s, watch_s], at(2026, 9, 18, 17, 1))
        d.tick([cron_s, watch_s], at(2026, 9, 18, 17, 2))
        self.assertIn(("hr-onboarding", "kim-minsu.pdf"), self.fired)

    def test_one_sections_exception_does_not_starve_the_others(self):
        """A cron section next to a watch section whose scan blows up for
        some unforeseen reason -- the cron section must still fire this
        tick, and the watch section's exception must not take the whole
        tick down (nor the daemon: `LOG.exception` names which section)."""
        d = self._daemon()
        cron_s = nufi_cron.Schedule(name="legal-weekly", cron=nufi_cron.Cron.parse("* * * * *"),
                                    flow="F", drive="legal", ask="q", out="o.md")
        watch_s = self._schedule()

        def boom(schedule):
            raise RuntimeError("boom")

        d._watch_listing = boom
        with self.assertLogs(nufi_cron.LOG, level="ERROR") as cm:
            d.tick([cron_s, watch_s], at(2026, 9, 18, 9, 0))
        self.assertEqual(self.fired, [("legal-weekly", None)],
                         "the cron section must still have fired")
        self.assertTrue(
            any("hr-onboarding" in line and "tick failed" in line for line in cm.output),
            cm.output)

    # --- retargeting a section (item 3) -------------------------------------

    def test_retargeting_a_section_is_treated_as_a_first_scan_not_a_storm(self):
        """Changing `watch` (or `drive`) under an unchanged section name must
        not compare the new folder's files against the old folder's history
        -- every file already in the new folder is recorded and NONE of them
        fire, exactly like a section seen for the first time."""
        d = self._daemon()
        s = self._schedule()
        self._mkwatch()
        d.tick([s], at(2026, 9, 18, 9, 0))          # first scan of onboarding/new: empty

        policies = self.root / "drives" / "hr" / "policies"
        for i in range(5):
            self._touch2(policies, f"p{i}.pdf")
        retargeted = self._schedule(watch="policies")
        for m in range(1, 5):
            d.tick([retargeted], at(2026, 9, 18, 9, m))
        self.assertEqual(self.fired, [], "no file already in the new folder should fire")
        seen = json.loads((self.root / "state" / "seen.json").read_text())
        record = seen["hr-onboarding"]
        self.assertEqual(record["folder"], "hr/policies")
        self.assertEqual(set(record["files"]), {f"p{i}.pdf" for i in range(5)})

        # ...and a genuinely new file dropped into the (now current) folder
        # afterwards still fires normally.
        self._touch2(policies, "p5.pdf")
        for m in range(5, 8):
            d.tick([retargeted], at(2026, 9, 18, 9, m))
        self.assertEqual(self.fired, [("hr-onboarding", "p5.pdf")])

    def test_an_old_shape_seen_json_is_treated_as_a_mismatch_not_a_crash(self):
        """A state file written by a release before `folder` was tracked is a
        bare {relative_path: mtime} dict -- migrated by treating it exactly
        like a retarget: a fresh first scan, not a crash and not a storm."""
        s = self._schedule()
        self._touch("kim-minsu.pdf")
        (self.root / "state" / "seen.json").write_text(
            json.dumps({"hr-onboarding": {"kim-minsu.pdf": 1}}))
        d = self._daemon()
        for m in range(3):
            d.tick([s], at(2026, 9, 18, 9, m))
        self.assertEqual(self.fired, [], "an old-shape record must not be read as already-seen")

    def test_a_seen_json_that_is_not_a_dict_is_treated_as_empty(self):
        """`null` (valid JSON, not a mapping) must not crash the daemon on
        every single tick -- an `isinstance` guard, exactly like a corrupt
        (unparseable) file, not merely a `try/except json.JSONDecodeError`
        that a syntactically-valid non-object slips straight past."""
        s = self._schedule()
        self._touch("kim-minsu.pdf")
        (self.root / "state" / "seen.json").write_text("null")
        d = self._daemon()
        for m in range(3):
            d.tick([s], at(2026, 9, 18, 9, m))  # must not raise
        self.assertEqual(self.fired, [], "a null seen.json is a fresh first scan, not a crash")

    # --- a folder that appears mid-flight (item 4) --------------------------

    def test_a_file_dropped_the_moment_the_folder_appears_still_fires(self):
        """Docs promise: a watch folder that does not exist yet is picked up
        as soon as someone creates it. A file created in the very same
        window as the folder itself must not be swallowed by what would
        otherwise look like the folder's first scan."""
        d = self._daemon()
        s = self._schedule()
        d.tick([s], at(2026, 9, 18, 9, 0))          # folder absent
        d.tick([s], at(2026, 9, 18, 9, 1))          # still absent
        self._touch("kim-minsu.pdf")                # folder + file appear together
        d.tick([s], at(2026, 9, 18, 9, 2))
        self.assertEqual(self.fired, [], "must not fire on the first sighting")
        d.tick([s], at(2026, 9, 18, 9, 3))
        self.assertEqual(self.fired, [("hr-onboarding", "kim-minsu.pdf")])

    # --- rules that a mutation to "mark seen only on success" leaves green
    # unless tested directly (item 5) ----------------------------------------

    def test_a_failed_run_still_marks_the_file_seen_and_is_not_retried(self):
        d = self._daemon()
        d.run_once = lambda schedule, when, file=None: (
            self.fired.append((schedule.name, file)) or False)
        s = self._schedule()
        self._mkwatch()
        d.tick([s], at(2026, 9, 18, 9, 0))
        self._touch("kim-minsu.pdf")
        d.tick([s], at(2026, 9, 18, 9, 1))
        d.tick([s], at(2026, 9, 18, 9, 2))
        self.assertEqual(len(self.fired), 1, "a failing run still counts as fired once")
        seen = json.loads((self.root / "state" / "seen.json").read_text())
        self.assertIn("kim-minsu.pdf", seen["hr-onboarding"]["files"],
                      "a failed run must still be marked seen")
        for m in range(3, 8):
            d.tick([s], at(2026, 9, 18, 9, m))
        self.assertEqual(len(self.fired), 1, "a failure must not be retried on its own")

    def test_a_tick_while_the_previous_watch_run_is_still_going_is_skipped(self):
        d = self._daemon()
        s = self._schedule()
        self._mkwatch()
        d.tick([s], at(2026, 9, 18, 9, 0))
        self._touch("kim-minsu.pdf")
        d.tick([s], at(2026, 9, 18, 9, 1))          # streak 1, not fired

        started = threading.Event()
        release = threading.Event()

        def slow(schedule, when, file=None):
            started.set()
            release.wait(5)
            self.fired.append((schedule.name, file))
            return True

        d.run_once = slow
        first = threading.Thread(target=d.tick, args=([s], at(2026, 9, 18, 9, 2)))
        first.start()
        self.assertTrue(started.wait(5), "the first run never started")
        d.tick([s], at(2026, 9, 18, 9, 3))          # would also be ready; one is in flight
        release.set()
        first.join(5)
        self.assertEqual(len(self.fired), 1, self.fired)

    # --- flat, not recursive (item 6) ---------------------------------------

    def test_a_file_in_a_subfolder_of_the_watched_folder_does_not_fire(self):
        """`watch` names one folder a file lands in, not a tree: two files
        named alike in different subfolders would otherwise collide on the
        same `{file}` and the second overwrite the first's `out`."""
        d = self._daemon()
        s = self._schedule()
        self._mkwatch()
        d.tick([s], at(2026, 9, 18, 9, 0))
        self._touch("2025/kim.pdf")
        self._touch("2026/kim.pdf")
        for m in range(1, 5):
            d.tick([s], at(2026, 9, 18, 9, m))
        self.assertEqual(self.fired, [], "a file inside a subfolder must never fire")

    def test_bare_name_strips_directories_and_leading_dots(self):
        """`_bare_name` is load-bearing for `{file}` in `ask`/`out`: it must
        never let a directory component or a leading dot reach either."""
        cases = {
            "../../x.md": "x.md",
            ".hidden": "hidden",
            "a/b": "b",
            "kim-minsu.pdf": "kim-minsu.pdf",
        }
        for given, want in cases.items():
            with self.subTest(given=given):
                self.assertEqual(nufi_cron._bare_name(given), want)

    # --- the full ignored-name list (item 7) --------------------------------

    def test_the_full_ignored_name_list(self):
        d = self._daemon()
        s = self._schedule()
        self._mkwatch()
        d.tick([s], at(2026, 9, 18, 9, 0))
        ignored = [
            ".DS_Store", "~$kim-minsu.pdf", ".~lock.kim-minsu.pdf#",
            "~WRD0001.tmp", "report.tmp", "report.part", "report.crdownload",
            "report.partial", "Thumbs.db", "desktop.ini",
        ]
        for name in ignored:
            self._touch(name)
        for m in range(1, 6):
            d.tick([s], at(2026, 9, 18, 9, m))
        self.assertEqual(self.fired, [], "none of the ignored names may ever fire")

    def _touch2(self, folder, name, content=b"x"):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(content)
        return folder / name


if __name__ == "__main__":
    unittest.main(verbosity=2)
