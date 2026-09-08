#!/usr/bin/env python3
"""Stdlib unit test for run_box.py (no Docker, no deps, no live box).

Stands up a fake nufi-app: /api/auth/login, /api/agents, /api/files/agent/<id>,
and the real two-hop chat transport --
    POST /api/agents/chat/agents        -> {streamId, conversationId, status}
    GET  /api/agents/chat/stream/<id>   -> text/event-stream, ends with the
                                            `final` event carrying responseMessage
-- then drives run_box.py's own main() against it exactly as a live run would,
using the "legal" department from departments.json so the real judge() (imported
from run.py, not reimplemented here) grades a real extract/refuse pair.

One of the three extract questions is answered wrong on purpose. That is the
regression this test exists to catch: an earlier draft of run_box.py did
`verdict = judge(...)` and treated the returned (ok, why) tuple itself as the
pass/fail flag -- a 2-tuple is always truthy, so every question "passed" no
matter what judge() actually decided.

A second question gets a 400 from the fake's chat POST instead of a normal
answer, catching a second regression: an earlier draft of Chat.call let
urllib.error.HTTPError propagate as a bare traceback (no status, no body),
which would kill the whole run instead of recording one failed question and
moving on. Assert failures == 2 (one wrong answer, one HTTP error), not 0.

Run:  python3 test_run_box.py     (exit 0 = PASS)
"""
import json
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_box  # noqa: E402
from run import REFUSAL_MARKERS  # noqa: E402  (same markers the fake uses)

DEPARTMENTS = json.loads((HERE / "departments.json").read_text())["departments"]
LEGAL = next(d for d in DEPARTMENTS if d["id"] == "legal")
DOC_NAME = LEGAL["documents"][0]["name"]
AGENT_ID = "agent_legal_test"
TOKEN = "fake-jwt-token"

# Wrong on purpose for the second extract question (expects "3", answered "2")
# so one check must FAIL -- see module docstring.
WRONG_ANSWER_INDEX = 1

# This one gets HTTP 400 from the chat POST instead of ever reaching the SSE
# stream -- see module docstring and do_POST below.
ERROR_INDEX = 2
ERROR_BODY = {"error": "Bad Request", "message": "text failed moderation"}

ANSWERS = []
for i, q in enumerate(LEGAL["questions"]):
    if i == ERROR_INDEX:
        continue  # do_POST returns 400 before this question ever streams
    if q["kind"] == "refuse":
        text = f"죄송합니다, 문의하신 내용은 문서에 {REFUSAL_MARKERS[2]}."
        sources = []
    elif i == WRONG_ANSWER_INDEX:
        text = "비밀유지 의무는 계약 종료 후 2년간 존속합니다."  # wrong: doc says 3
        sources = [DOC_NAME]
    else:
        text = f"문서에 따르면 답은 {q['expect']}입니다."
        sources = [DOC_NAME]
    ANSWERS.append({"ask": q["ask"], "text": text, "sources": sources})


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class _FakeApp(BaseHTTPRequestHandler):
    """Minimal stand-in for the app's own /api surface.

    files_calls counts GET /api/files/agent/<id> hits per agent so the test can
    prove run_box.py actually polls: the first two calls report the drive as
    still empty, the third onward reports the ingested file.
    """

    files_calls = 0
    jobs = {}  # streamId -> chat request body

    def log_message(self, *a):
        pass

    # ---- helpers ----------------------------------------------------------
    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(n) or "{}")

    def _require_chrome_ua(self):
        """Mirrors the real /api/agents and /api/files gate: no bare-UA calls."""
        ua = self.headers.get("User-Agent", "")
        if "Chrome" not in ua:
            self._json(403, {"error": "banned: missing browser User-Agent"})
            return False
        return True

    def _require_bearer(self):
        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {TOKEN}":
            self._json(401, {"error": "unauthorized"})
            return False
        return True

    # ---- routes -------------------------------------------------------------
    def do_GET(self):
        if self.path.startswith("/api/agents?"):
            if not (self._require_chrome_ua() and self._require_bearer()):
                return
            return self._json(200, {"data": [{"id": AGENT_ID, "name": "Legal assistant"}]})

        if self.path.startswith("/api/files/agent/"):
            if not (self._require_chrome_ua() and self._require_bearer()):
                return
            _FakeApp.files_calls += 1
            if _FakeApp.files_calls < 3:
                return self._json(200, [])
            return self._json(200, [{"filename": DOC_NAME}])

        if self.path.startswith("/api/agents/chat/stream/"):
            stream_id = self.path.rsplit("/", 1)[-1]
            body = _FakeApp.jobs.pop(stream_id, None)
            return self._stream_answer(body)

        return self._json(404, {"error": "no such route"})

    def do_POST(self):
        if self.path == "/api/auth/login":
            body = self._read_json()
            assert body.get("email") and body.get("password"), body
            return self._json(200, {"token": TOKEN, "user": {"email": body["email"]}})

        if self.path == "/api/agents/chat/agents":
            if not (self._require_chrome_ua() and self._require_bearer()):
                return
            body = self._read_json()
            assert body["endpoint"] == "agents", body
            assert body["agent_id"] == AGENT_ID, body
            assert body["conversationId"] is None, body
            assert body["parentMessageId"] == run_box.NIL, body
            assert body["isCreatedByUser"] is True, body
            assert body["isTemporary"] is True, body
            assert body["isContinued"] is False, body
            assert body["error"] is False, body
            assert "messageId" in body and "text" in body, body
            if body["text"] == LEGAL["questions"][ERROR_INDEX]["ask"]:
                # Real shape of a rejected request: a JSON error body with no
                # streamId at all. Chat.call must turn this into a BoxError
                # carrying the status and this body, not an unhandled
                # urllib.error.HTTPError.
                return self._json(400, ERROR_BODY)
            stream_id = str(uuid.uuid4())
            _FakeApp.jobs[stream_id] = body
            # Real controller: res.json({streamId, conversationId, status})
            # (apps/chat/api/server/controllers/agents/request.js:125-127) --
            # this is NOT the SSE stream itself.
            return self._json(200, {
                "streamId": stream_id,
                "conversationId": stream_id,
                "status": "started",
            })

        return self._json(404, {"error": "no such route"})

    def _stream_answer(self, body):
        """The real SSE shape (routes/agents/index.js:88-100):
        `event: message\\ndata: <json>\\n\\n`, ending with the `final` event.
        """
        ask = (body or {}).get("text", "")
        match = next((a for a in ANSWERS if a["ask"] == ask), None)
        text = match["text"] if match else "(unexpected question)"
        sources = match["sources"] if match else []

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def write(event):
            self.wfile.write(f"event: message\ndata: {json.dumps(event)}\n\n".encode())
            self.wfile.flush()

        # Two incremental chunks, as the brief's fake app must produce.
        write({"text": text[: len(text) // 2]})
        write({"text": text})
        write({
            "final": True,
            "responseMessage": {
                "text": text,
                "attachments": [{"sources": [{"fileName": s} for s in sources]}] if sources else [],
            },
        })


def _serve(handler=_FakeApp):
    port = _free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


_STOP_HANG = threading.Event()


class _HalfStreamApp(BaseHTTPRequestHandler):
    """Answers the chat POST normally, opens the SSE stream, sends one partial
    chunk -- and then never sends the rest.

    That is what a generation that dies halfway looks like from the client
    side (the app restarted, the model host dropped, the job wedged), and it
    happens *after* the 200 and after the body has started, so Chat.call's
    HTTPError/URLError handling is already behind us. Without the guard inside
    Chat.ask the resulting socket error escapes and takes the whole run down
    on one bad question.

    A hang rather than a hard close, because that is deterministic: a close
    mid-body is read as a clean end of stream by readline(), so it produces a
    truncated answer rather than an error, whereas a stall reliably trips the
    read timeout no matter how the OS schedules the two ends.
    """

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        self.rfile.read(n)
        raw = json.dumps({"streamId": "s1", "conversationId": "s1", "status": "started"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(b'event: message\ndata: {"text": "\xea\xb3\x84\xec\x95\xbd"}\n\n')
        self.wfile.flush()
        _STOP_HANG.wait(30)  # never sends the `final` event


def test_a_broken_stream_becomes_a_recorded_failure():
    _STOP_HANG.clear()
    httpd, port = _serve(_HalfStreamApp)
    old = run_box.STREAM_TIMEOUT
    run_box.STREAM_TIMEOUT = 1.0
    chat = run_box.Chat(f"http://127.0.0.1:{port}")
    try:
        try:
            answer, sources = chat.ask("agent_x", "질문")
        except run_box.BoxError as exc:
            assert "stream broke" in str(exc), exc
            # names the facts someone debugging this needs: which stream, and
            # how much of the answer had arrived before it stopped.
            assert "/api/agents/chat/stream/s1" in str(exc), exc
            assert "chars" in str(exc), exc
            print("PASS: a stream that dies mid-answer raises BoxError, not a "
                  "socket traceback that kills the run")
            return
        except Exception as exc:  # noqa: BLE001 - this is the regression
            raise AssertionError(
                f"stream break escaped as {type(exc).__name__}: {exc} — "
                "main() would have aborted the whole run on one question") from exc
        raise AssertionError(f"expected a BoxError, got a clean answer: {answer!r} {sources}")
    finally:
        run_box.STREAM_TIMEOUT = old
        _STOP_HANG.set()
        httpd.shutdown()


class _HostEchoApp(BaseHTTPRequestHandler):
    """Records the Host header of every request it receives."""

    seen = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        _HostEchoApp.seen.append(self.headers.get("Host"))
        raw = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def test_connect_to_moves_the_socket_and_leaves_the_url_alone():
    """The whole point of --connect-to over rewriting --base: the box is
    reached on another host port, but the request must still *be* a request to
    nufi.local:3080 as far as the Host header (and, over TLS, SNI and
    certificate verification) are concerned."""
    rules = run_box.parse_connect_to(["nufi.local:3080:127.0.0.1:19999"])
    assert rules == {("nufi.local", 3080): ("127.0.0.1", 19999)}, rules
    short = run_box.parse_connect_to(["nufi.local:3080:19999"])
    assert short == {("nufi.local", 3080): ("127.0.0.1", 19999)}, short
    for bad in ("nufi.local:3080", "a:b:c:d"):
        try:
            run_box.parse_connect_to([bad])
        except SystemExit:
            pass
        else:
            raise AssertionError(f"{bad!r} should have been rejected")

    _HostEchoApp.seen = []
    httpd, port = _serve(_HostEchoApp)
    try:
        chat = run_box.Chat("http://nufi.local:3080",
                            connect_to={("nufi.local", 3080): ("127.0.0.1", port)})
        with chat.call("GET", "/health") as r:
            assert json.load(r) == {"ok": True}
    finally:
        httpd.shutdown()
    # It reached a server on 127.0.0.1:<port> ...
    assert len(_HostEchoApp.seen) == 1, _HostEchoApp.seen
    # ... but the request still says it is for nufi.local:3080.
    assert _HostEchoApp.seen[0] == "nufi.local:3080", _HostEchoApp.seen
    print("PASS: --connect-to dials the mapped address while Host stays on the "
          "URL's own host:port")


def main():
    httpd, port = _serve()
    drives = Path(tempfile.mkdtemp(prefix="run_box_test_drives_"))
    out = Path(tempfile.mkdtemp(prefix="run_box_test_evidence_"))
    old_poll = run_box.POLL_INTERVAL
    run_box.POLL_INTERVAL = 0.05  # keep the (real) 3-call poll loop fast
    argv = [
        "run_box.py",
        "--base", f"http://127.0.0.1:{port}",
        "--email", "sun@dudaji.com",
        "--password", "x",
        "--drives", str(drives),
        "--out", str(out),
        "--only", "legal",
        "--timeout", "10",
    ]
    old_argv = sys.argv
    sys.argv = argv
    try:
        try:
            run_box.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
    finally:
        sys.argv = old_argv
        run_box.POLL_INTERVAL = old_poll
        httpd.shutdown()

    # 1) exit code reflects the two deliberate failures (wrong answer + HTTP
    #    error), not a false PASS.
    assert code == 1, f"expected exit 1 (failures present), got {code}"

    # 2) the department document was actually written to the drives dir.
    doc_path = drives / LEGAL["drive"] / DOC_NAME
    assert doc_path.is_file(), f"missing {doc_path}"
    assert doc_path.read_text() == LEGAL["documents"][0]["text"]

    # 3) the runner really polled: files_of was called 3 times (empty, empty,
    #    then the ingested file) before it moved on to questions.
    assert _FakeApp.files_calls >= 3, _FakeApp.files_calls

    # 4) evidence/box.json has the right shape and the right verdicts.
    data = json.loads((out / "box.json").read_text())
    assert data["failures"] == 2, data
    dept = data["departments"][0]
    assert dept["id"] == "legal"
    assert dept["agent"] == AGENT_ID
    assert dept["ingest_complete"] is True, dept
    questions = dept["questions"]
    assert len(questions) == 4, questions
    for i, q in enumerate(questions):
        expect_pass = i not in (WRONG_ANSWER_INDEX, ERROR_INDEX)
        assert q["pass"] is expect_pass, (i, q)
    assert questions[0]["pass"] is True and DOC_NAME in questions[0]["sources"]
    assert questions[WRONG_ANSWER_INDEX]["pass"] is False
    assert questions[3]["kind"] == "refuse" and questions[3]["pass"] is True

    # 4b) the HTTP-error question is recorded with the status and body excerpt,
    #     not a bare traceback -- and the run kept going past it.
    error_q = questions[ERROR_INDEX]
    assert error_q["answer"] == "", error_q
    assert error_q["pass"] is False, error_q
    assert "error" in error_q, error_q
    assert "400" in error_q["error"], error_q
    assert "moderation" in error_q["error"], error_q  # body excerpt

    # 5) evidence/box.md was written and names both a PASS and the FAIL.
    md = (out / "box.md").read_text()
    assert "legal" in md
    assert "PASS" in md and "FAIL" in md

    # 5b) the md leads with the score, so the file answers "how did it go?"
    #     without anyone counting PASS lines.
    assert "2/4 checks passed" in md, md.splitlines()[:4]

    # 5c) the failed question shows WHY it failed, not just an empty bullet:
    #     the HTTP-error one shows its error text, the wrong-answer one shows
    #     the judge's verdict. Without this, evidence/box.md rendered a failed
    #     question as a blank line and the reader had to open box.json.
    assert "error: " in md and "400" in md and "moderation" in md, md
    assert "verdict: " in md and "does not state '3'" in md, md

    shutil.rmtree(drives, ignore_errors=True)
    shutil.rmtree(out, ignore_errors=True)
    print("PASS: run_box.py writes documents, polls for ingest, drives the real "
          "two-hop SSE chat, judges extract/refuse questions, and turns an HTTP "
          "error into a recorded failure instead of a crash")


class _NeverIngestsApp(_FakeApp):
    """The agent exists, but its file list stays empty forever.

    This is the live failure that produced the worst evidence file: with no
    document behind it the agent answers every question with a polite "the
    document does not mention that", so the md filled up with identical
    extract failures and one accidental refuse PASS, and nothing on the page
    said the daemon had never embedded anything.
    """

    def do_GET(self):
        if self.path.startswith("/api/files/agent/"):
            if not (self._require_chrome_ua() and self._require_bearer()):
                return
            return self._json(200, [])
        return super().do_GET()


def test_the_markdown_names_an_ingest_gap():
    _NeverIngestsApp.jobs = {}
    httpd, port = _serve(_NeverIngestsApp)
    drives = Path(tempfile.mkdtemp(prefix="run_box_test_gap_drives_"))
    out = Path(tempfile.mkdtemp(prefix="run_box_test_gap_"))
    old_poll, old_argv = run_box.POLL_INTERVAL, sys.argv
    run_box.POLL_INTERVAL = 0.05
    sys.argv = ["run_box.py", "--base", f"http://127.0.0.1:{port}",
                "--email", "sun@dudaji.com", "--password", "x",
                "--drives", str(drives), "--out", str(out),
                "--only", "legal", "--timeout", "0.5"]
    try:
        try:
            run_box.main()
        except SystemExit:
            pass
    finally:
        sys.argv, run_box.POLL_INTERVAL = old_argv, old_poll
        httpd.shutdown()

    data = json.loads((out / "box.json").read_text())
    dept = data["departments"][0]
    assert dept["ingest_complete"] is False, dept
    assert dept["missing"] == [DOC_NAME], dept

    md = (out / "box.md").read_text()
    # The reason has to be on the page, once, above the questions -- otherwise
    # the reader debugs the model instead of the daemon.
    assert "ingest_complete: false" in md, md
    assert DOC_NAME in md, md
    assert md.index("ingest_complete: false") < md.index("- **" + LEGAL["questions"][0]["ask"]), md

    shutil.rmtree(drives, ignore_errors=True)
    shutil.rmtree(out, ignore_errors=True)
    print("PASS: evidence/box.md names the ingest gap and the missing document "
          "above the department's questions, not only in box.json")


if __name__ == "__main__":
    main()
    test_a_broken_stream_becomes_a_recorded_failure()
    test_connect_to_moves_the_socket_and_leaves_the_url_alone()
    test_the_markdown_names_an_ingest_gap()
