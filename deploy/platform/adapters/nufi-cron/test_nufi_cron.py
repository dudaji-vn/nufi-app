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
import pathlib
import sys
import tempfile
import threading
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


class ConfigParsing(unittest.TestCase):
    def _write(self, text):
        d = pathlib.Path(tempfile.mkdtemp())
        p = d / "schedules.ini"
        p.write_text(text, encoding="utf-8")
        return p

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
        written = self.root / "drives" / "legal" / nufi_cron.OUTPUT_DIR / "weekly-report-2026-09-18.md"
        self.assertTrue(written.exists(), sorted(p.name for p in (self.root / "drives" / "legal").rglob("*")))
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
