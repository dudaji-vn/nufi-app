#!/usr/bin/env python3
"""Acceptance for the box: drop the department documents into the drives, wait
for nufi-ingest, then ask each department's agent its questions through the
app's own agents endpoint and judge the answers exactly as run.py does.

    python3 run_box.py --base https://nufi.local:3080 --email admin@nufi.local \
        --password ... --drives ../../box/data/drives [--only legal] [--insecure]

Exit 0 = every check passed. Evidence lands in evidence/box.md and box.json.

Chat transport, verified against the app's own source (not the brief's first
draft, which assumed the chat POST returns the SSE stream directly):

  1. POST /api/agents/chat/agents starts a background generation job and
     returns JSON immediately -- {streamId, conversationId, status:"started"}.
     apps/chat/api/server/controllers/agents/request.js:125-127 --
         res.json({ streamId, conversationId, status: 'started' });
     ...the whole rest of that function runs the model *after* this response
     has already gone out, so there is no SSE to read on this connection.

  2. The actual answer streams from a second call, keyed by that streamId:
     GET /api/agents/chat/stream/<streamId>
     apps/chat/api/server/routes/agents/index.js:88-100 --
         const writeEvent = (event) => {
           res.write(`event: message\ndata: ${JSON.stringify(event)}\n\n`);
           ...
         };
         const onDone = (event) => { writeEvent(event); res.end(); };
     `onDone` is fed the same `finalEvent` request.js builds at
     request.js:364-371 -- `{ final: true, ..., responseMessage: {...} }` --
     which is where the answer text and file-search sources live.

Required request-body fields, matched against the app's own validators:
  - `endpoint` must be present -- parsers.ts:343-345 throws `undefined
    endpoint` from parseCompactConvo() otherwise.
  - `endpoint` must equal "agents" for `agent_id` to route as a real
    (non-ephemeral) agent -- schemas.ts:141-145 `isAgentsEndpoint`.
  - `agent_id` is required in the body -- canAccessAgentFromBody.js:167-172:
        if (!agentId) {
          return res.status(400).json({ error: 'Bad Request',
            message: 'agent_id is required in request body' });
        }
  - `conversationId` may be null/omitted: convoAccess.js:38-40 treats a
    missing conversationId (or Constants.NEW_CONVO) as "no check needed" and
    calls next() immediately.
  - `parentMessageId` for a first turn is Constants.NO_PARENT, the literal
    nil UUID (config.ts:2179) -- reproduced here as NIL rather than imported,
    since data-provider is TypeScript and this script is stdlib-only.
"""
import argparse
import http.client
import json
import pathlib
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid

from run import drifted, judge  # same judge, same markers

HERE = pathlib.Path(__file__).resolve().parent
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
NIL = "00000000-0000-0000-0000-000000000000"

# How long to sleep between ingest-poll attempts. A module-level constant
# (rather than a literal inside the loop) so a test can shrink it instead of
# waiting out a real --timeout.
POLL_INTERVAL = 5.0

# Cap on how long one answer may take to stream. Generous, because a cold
# model load plus retrieval plus a long Korean answer is genuinely slow -- but
# finite, so a generation that hangs fails that one question instead of the
# run. Module-level so a test can shrink it.
STREAM_TIMEOUT = 600.0


class BoxError(Exception):
    """The app API returned an HTTP error, was unreachable, or cut the answer
    off mid-stream.

    Mirrors run.py's Box.call (run.py:63-87): the message always carries the
    method, path, status (or "unreachable"), and the response body -- the
    thing someone debugging the first live run actually needs to see,
    instead of a bare urllib.error.HTTPError traceback with no context.
    """


def connect_to_opener(rules, ctx):
    """An opener that sends the request to a different socket address while
    leaving the URL alone -- curl's --connect-to, in urllib.

    Needed whenever the box is reachable on a port other than the one it was
    installed with: on a machine that already runs something on 3080, the box
    publishes Caddy on a different host port, but the certificate, the SNI
    name, the Host header, the cookie scope and every redirect Location still
    belong to nufi.local:3080. Rewriting the *URL* to 127.0.0.1:13080 would
    change all five; rewriting only the TCP destination changes none of them.

    `rules` maps (host, port) from the URL to (host, port) to dial.
    """

    class _HTTPS(http.client.HTTPSConnection):
        def connect(self):
            host, port = rules.get((self.host, self.port), (self.host, self.port))
            self.sock = self._create_connection((host, port), self.timeout, self.source_address)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            # server_hostname stays self.host: SNI (and therefore certificate
            # verification) must still name the box, not the loopback address.
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)

    class _HTTP(http.client.HTTPConnection):
        def connect(self):
            host, port = rules.get((self.host, self.port), (self.host, self.port))
            self.sock = self._create_connection((host, port), self.timeout, self.source_address)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    class _HTTPSHandler(urllib.request.HTTPSHandler):
        def https_open(self, req):
            def build(host, **kw):
                kw.pop("context", None)
                kw.pop("check_hostname", None)
                return _HTTPS(host, context=ctx, **kw)
            return self.do_open(build, req)

    class _HTTPHandler(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(_HTTP, req)

    return urllib.request.build_opener(_HTTPSHandler(), _HTTPHandler())


def parse_connect_to(specs):
    """--connect-to HOST:PORT:TOHOST:TOPORT (curl's four-field form), or the
    shorthand HOST:PORT:TOPORT. Returns the {(host, port): (host, port)} map."""
    rules = {}
    for spec in specs:
        parts = spec.split(":")
        if len(parts) == 4:
            host, port, to_host, to_port = parts
        elif len(parts) == 3:
            host, port, to_port = parts
            to_host = "127.0.0.1"
        else:
            raise SystemExit(f"--connect-to wants HOST:PORT:TOHOST:TOPORT, got {spec!r}")
        try:
            rules[(host, int(port))] = (to_host, int(to_port))
        except ValueError as exc:
            raise SystemExit(f"--connect-to ports must be numbers: {spec!r}") from exc
    return rules


def add_transport_args(ap):
    """The three flags any script needs to reach a box: how to trust its TLS,
    and where to actually dial. Shared so run_box.py and the Studio scripts
    take the same flags with the same meanings."""
    tls = ap.add_mutually_exclusive_group()
    tls.add_argument("--insecure", action="store_true",
                     help="skip TLS verification (box CA not in the trust store)")
    tls.add_argument("--cacert", default=None,
                     help="trust this PEM CA file instead of skipping verification")
    ap.add_argument("--connect-to", action="append", default=[], metavar="HOST:PORT:TOHOST:TOPORT",
                    help="dial a different socket address while leaving the URL (and so SNI, "
                         "Host and cookie scope) on HOST:PORT — curl's --connect-to. "
                         "TOHOST may be omitted for 127.0.0.1. Repeatable.")


def transport_from_args(a):
    """(ssl context, opener-or-None) for the parsed --insecure/--cacert/--connect-to."""
    if a.insecure:
        ctx = ssl._create_unverified_context()
    elif a.cacert:
        ctx = ssl.create_default_context(cafile=a.cacert)
    else:
        ctx = ssl.create_default_context()
    rules = parse_connect_to(a.connect_to)
    return ctx, (connect_to_opener(rules, ctx) if rules else None)


def _answer_of(msg):
    """The answer text of a responseMessage.

    An agent run leaves `text` EMPTY and puts the answer in `content`, a list
    of typed parts -- the shape the client renders from
    (`Message.content: TMessageContentParts[]`, data-provider/types.ts). The
    brief's first draft read `text` only, so every live answer came back as ''
    and every question failed with "empty answer" while the box was in fact
    answering fine. Read the parts first, keep `text` as the fallback for a
    non-agent endpoint that does fill it.
    """
    if not isinstance(msg, dict):
        return ""
    parts = []
    for part in msg.get("content") or []:
        if not isinstance(part, dict):
            continue
        if isinstance(part.get("text"), str):
            parts.append(part["text"])
        elif isinstance(part.get("text"), dict) and isinstance(part["text"].get("value"), str):
            parts.append(part["text"]["value"])  # assistants-style {text: {value}}
    return "".join(parts).strip() or (msg.get("text") or "").strip()


def _sources_of(msg):
    """The cited filenames of a responseMessage.

    A file_search citation is attached as
        {type: "file_search", file_search: {sources: [{fileName, relevance, ...}]}}
    -- see Files/Citations/index.js:75-79 building `fileSearchAttachment`, and
    :147 setting `fileName`. The nesting matters: an earlier draft iterated
    `att["file_search"]` directly, which yields the dict's KEYS ("sources"),
    so every citation was silently dropped and a passing answer looked
    uncited.
    """
    out = []
    for att in (msg.get("attachments") if isinstance(msg, dict) else None) or []:
        if not isinstance(att, dict):
            continue
        holder = att.get(att.get("type") or "") or att
        found = holder.get("sources") if isinstance(holder, dict) else None
        if not isinstance(found, list):
            found = att.get("sources") if isinstance(att.get("sources"), list) else []
        for s in found:
            if isinstance(s, dict):
                name = s.get("fileName") or s.get("filename") or s.get("source")
                if name:
                    out.append(name)
    return sorted(set(out))


class Chat:
    """The app's own /api surface, driven exactly as the browser client
    drives it -- every call carries the same User-Agent, so a bare-UA request
    (which the gated /api/agents and /api/files routes ban the account for)
    is not a code path that exists here.
    """

    def __init__(self, base, insecure=False, cacert=None, connect_to=None):
        self.base = base.rstrip("/")
        self.token = None
        if insecure:
            self.ctx = ssl._create_unverified_context()
        elif cacert:
            self.ctx = ssl.create_default_context(cafile=cacert)
        else:
            self.ctx = ssl.create_default_context()
        self.opener = connect_to_opener(connect_to, self.ctx) if connect_to else None

    def call(self, method, path, body=None, stream=False, timeout=600):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("User-Agent", UA)
        req.add_header("Accept", "text/event-stream" if stream else "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        try:
            if self.opener is not None:
                return self.opener.open(req, timeout=timeout)
            return urllib.request.urlopen(req, timeout=timeout, context=self.ctx)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            raise BoxError(f"{method} {path} -> {exc.code}: {raw[:300]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", exc)
            raise BoxError(f"{method} {path} -> unreachable: {reason}") from exc

    def login(self, email, password):
        with self.call("POST", "/api/auth/login", {"email": email, "password": password}) as r:
            self.token = json.load(r)["token"]

    def agent_named(self, name):
        with self.call("GET", "/api/agents?limit=200") as r:
            for a in json.load(r).get("data", []):
                if a.get("name") == name:
                    return a["id"]
        return None

    def files_of(self, agent_id):
        with self.call("GET", f"/api/files/agent/{agent_id}") as r:
            return [f["filename"] for f in json.load(r)]

    def ask(self, agent_id, text):
        body = {"text": text, "endpoint": "agents", "agent_id": agent_id, "conversationId": None,
                "parentMessageId": NIL, "messageId": str(uuid.uuid4()), "isCreatedByUser": True,
                "error": False, "isContinued": False, "isTemporary": True}
        # Hop 1: kick off the job. This is a plain JSON response, not SSE --
        # see the module docstring. A short timeout is enough; the handler
        # sends this response before the model has even started.
        with self.call("POST", "/api/agents/chat/agents", body, timeout=60) as r:
            started = json.load(r)
        stream_id = started.get("streamId") or started.get("conversationId")
        if not stream_id:
            raise RuntimeError(f"chat start returned no streamId: {started}")

        # Hop 2: the real SSE stream, keyed by that streamId. This is the one
        # that can legitimately take a while (a long generation), hence
        # STREAM_TIMEOUT here rather than hop 1's short cap.
        answer, sources, final, deltas = "", [], {}, []
        with self.call("GET", f"/api/agents/chat/stream/{stream_id}", stream=True,
                       timeout=STREAM_TIMEOUT) as r:
            # Everything above has succeeded by now -- the connection is open
            # and the status was 200 -- so Chat.call's except clauses are
            # behind us. A generation that dies halfway (the app restarts,
            # the model host drops, the read times out) surfaces here as a
            # raw socket/SSL error, which without this would abort the whole
            # run on one bad question. Turn it into the same BoxError every
            # other failure raises, so main() records it on the question and
            # carries on to the next one.
            try:
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        ev = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if "responseMessage" in ev:
                        final = ev
                    if isinstance(ev.get("text"), str):
                        answer = ev["text"]
                    # Agent runs stream their answer as on_message_delta events
                    # carrying content parts, not as a top-level `text`. Keep
                    # them: if the run dies before the final event, this is the
                    # only record of how far it got.
                    delta = ev.get("data", {})
                    if isinstance(delta, dict):
                        for part in (delta.get("delta") or {}).get("content") or []:
                            if isinstance(part, dict) and isinstance(part.get("text"), str):
                                deltas.append(part["text"])
            except (OSError, http.client.HTTPException, ssl.SSLError, TimeoutError) as exc:
                got = (_answer_of(final.get("responseMessage", {})) or answer
                       or "".join(deltas)).strip()
                raise BoxError(
                    f"GET /api/agents/chat/stream/{stream_id} -> stream broke after "
                    f"{len(got)} chars: {type(exc).__name__}: {exc}") from exc
        msg = final.get("responseMessage", {})
        answer = _answer_of(msg) or answer or "".join(deltas)
        sources = _sources_of(msg)
        return answer, sources


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--drives", required=True)
    ap.add_argument("--only", default="")
    add_transport_args(ap)
    ap.add_argument("--timeout", type=float, default=180,
                     help="seconds to wait for nufi-ingest to list each department's files")
    ap.add_argument("--out", default=str(HERE / "evidence"),
                     help="directory for box.md / box.json")
    a = ap.parse_args()
    connect_to = parse_connect_to(a.connect_to)

    with open(HERE / "departments.json") as fh:
        depts = json.load(fh)["departments"]
    if a.only:
        depts = [d for d in depts if d["id"] == a.only]
        if not depts:
            raise SystemExit(f"no such department: {a.only}")

    chat = Chat(a.base, insecure=a.insecure, cacert=a.cacert, connect_to=connect_to)
    try:
        chat.login(a.email, a.password)
    except BoxError as exc:
        print(f"login failed: {exc}", file=sys.stderr)
        sys.exit(2)

    drives = pathlib.Path(a.drives)
    out = {"base": a.base, "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "departments": []}
    failures = 0
    for d in depts:
        (drives / d["drive"]).mkdir(parents=True, exist_ok=True)
        for doc in d["documents"]:
            (drives / d["drive"] / doc["name"]).write_text(doc["text"])
        name = f"{d['drive'].capitalize()} assistant"
        want = set(x["name"] for x in d["documents"])
        t0 = time.time()
        agent, ingest_complete, missing = None, False, sorted(want)
        while time.time() - t0 < a.timeout:
            agent = chat.agent_named(name)
            if agent:
                missing = sorted(want - set(chat.files_of(agent)))
                if not missing:
                    ingest_complete = True
                    break
            time.sleep(POLL_INTERVAL)
        rec = {"id": d["id"], "agent": agent, "ingest_seconds": round(time.time() - t0, 1),
               "ingest_complete": ingest_complete, "missing": [] if ingest_complete else missing,
               "questions": []}
        if not agent:
            rec["error"] = "agent never appeared"
            failures += 1
            out["departments"].append(rec)
            continue
        if not ingest_complete:
            print(f"[FAIL] {d['id']}: ingest incomplete after {a.timeout}s, "
                  f"still missing: {', '.join(missing)}")
            failures += 1
        for q in d["questions"]:
            t1 = time.time()
            try:
                answer, sources = chat.ask(agent, q["ask"])
            except BoxError as exc:
                rec["questions"].append({
                    "ask": q["ask"], "kind": q["kind"], "expect": q["expect"],
                    "answer": "", "sources": [], "seconds": round(time.time() - t1, 1),
                    "pass": False, "why": None, "drifted": False, "error": str(exc)})
                failures += 1
                print(f"[FAIL] {d['id']}: {q['ask']} → ERROR {exc}")
                continue
            ok, why = judge(q["kind"], answer, q["expect"])
            rec["questions"].append({
                "ask": q["ask"], "kind": q["kind"], "expect": q["expect"], "answer": answer,
                "sources": sources, "seconds": round(time.time() - t1, 1),
                "pass": ok, "why": why, "drifted": drifted(answer)})
            failures += 0 if ok else 1
            print(f"[{'ok' if ok else 'FAIL'}] {d['id']}: {q['ask']} → {answer[:80]!r} {sources}")
        out["departments"].append(rec)
    out["failures"] = failures

    outdir = pathlib.Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "box.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    asked = sum(len(d["questions"]) for d in out["departments"])
    md = [f"# Box acceptance — {out['started']} — {a.base}", "",
          f"**{asked - failures}/{asked} checks passed** "
          f"({failures} failure{'' if failures == 1 else 's'}).", ""]
    for d in out["departments"]:
        md.append(f"## {d['id']} (agent {d['agent']}, ingested in {d['ingest_seconds']} s)")
        # An ingest gap is the reason a whole department's answers go wrong, so
        # say it here rather than leaving the reader to infer it from four
        # identical "the document does not mention that" failures below.
        if d.get("error"):
            md.append(f"- **ingest: {d['error']}** — no questions were asked")
        elif not d.get("ingest_complete", True):
            md.append(f"- **ingest_complete: false** — never embedded: "
                      f"{', '.join(d.get('missing') or []) or 'unknown'}")
        for q in d["questions"]:
            md += [f"- **{q['ask']}** → {'PASS' if q['pass'] else 'FAIL'} ({q['seconds']} s)"]
            # A question that never got an answer has an `error` instead of one;
            # printing the empty answer alone would hide why it failed.
            if q.get("error"):
                md.append(f"  - error: {q['error']}")
            else:
                md.append(f"  - {q['answer']}")
                if not q["pass"] and q.get("why"):
                    md.append(f"  - verdict: {q['why']}")
            md.append(f"  - sources: {', '.join(q['sources']) or 'none'}")
        md.append("")
    (outdir / "box.md").write_text("\n".join(md))
    print(f"{failures} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
