#!/usr/bin/env python3
"""Stdlib test for nufi-ingest: a fake NuFi app, a temp drives dir, one scan cycle.

Asserts the daemon (1) logs in once and then mints its own JWT, (2) creates a
team and an agent per department folder and shares the agent to the team,
(3) uploads a new file with agent_id + tool_resource=file_search and a browser
User-Agent, (4) deletes-then-reuploads a changed file, (5) deletes a removed
file, (6) never PATCHes file_ids. Run: python3 test_ingest.py  (exit 0 = PASS)
"""
import base64
import hashlib
import hmac
import json
import logging
import pathlib
import socket
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import nufi_ingest as I

# the delete-retry scenarios below deliberately trigger LOG.error() inside the
# daemon; keep that off stderr so the only thing this script prints is PASS.
logging.getLogger("nufi-ingest").addHandler(logging.NullHandler())
logging.getLogger("nufi-ingest").propagate = False

SECRET = "test-secret"
USER_ID = "64b000000000000000000001"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _b64url_decode(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class FakeApp(BaseHTTPRequestHandler):
    seen = []          # (method, path, headers, body-bytes)
    agents = {}        # id -> doc
    teams = {}         # _id -> doc
    files = {}         # file_id -> doc
    counter = 0
    fail_next_delete = False   # set True to make the next DELETE return 500 once
    fail_agent_get = None      # set to an agent id to make its next GET 500 once

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _auth_ok(self):
        tok = (self.headers.get("Authorization") or "").replace("Bearer ", "")
        try:
            h, p, s = tok.split(".")
            expect = hmac.new(SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
            return (hmac.compare_digest(_b64url_decode(s), expect)
                    and json.loads(_b64url_decode(p))["id"] == USER_ID)
        except Exception:
            return False

    def do_POST(self):
        body = self._body()
        FakeApp.seen.append(("POST", self.path, dict(self.headers), body))
        if self.path == "/api/auth/login":
            return self._json(200, {"token": "login-token",
                                    "user": {"id": USER_ID, "role": "ADMIN"}})
        if not self._auth_ok():
            return self._json(401, {"error": "unauthorized"})
        gated = self.path in ("/api/files", "/api/agents")
        if gated and "Chrome/" not in self.headers.get("User-Agent", ""):
            return self._json(403, {"message": "Illegal request"})
        if self.path == "/api/teams":
            FakeApp.counter += 1
            tid = f"t{FakeApp.counter}"
            FakeApp.teams[tid] = {"_id": tid, "name": json.loads(body)["name"]}
            return self._json(201, {"team": FakeApp.teams[tid]})
        if self.path == "/api/agents":
            FakeApp.counter += 1
            aid = f"agent_{FakeApp.counter}"
            doc = {"id": aid, "_id": f"oid{FakeApp.counter}", "tool_resources": {},
                   **json.loads(body)}
            FakeApp.agents[aid] = doc
            return self._json(201, doc)
        if self.path.startswith("/api/teams/") and "/agents/" in self.path:
            return self._json(201, {"success": True})
        if self.path == "/api/files":
            raw = body
            def field(name):
                m = raw.find(b'name="' + name.encode() + b'"')
                j = raw.find(b"\r\n\r\n", m)
                k = raw.find(b"\r\n--", j)
                return raw[j + 4:k].decode() if m >= 0 else None
            FakeApp.counter += 1
            fid = f"srv-{FakeApp.counter}"
            FakeApp.files[fid] = {"file_id": fid, "filepath": "vectordb",
                                  "agent_id": field("agent_id"),
                                  "tool_resource": field("tool_resource"),
                                  "endpoint": field("endpoint")}
            attached = FakeApp.agents[field("agent_id")]["tool_resources"]
            attached.setdefault("file_search", {}).setdefault("file_ids", []).append(fid)
            return self._json(200, {"message": "ok", "file_id": fid,
                                    "filepath": "vectordb", "embedded": True})
        self._json(404, {"error": self.path})

    def do_GET(self):
        FakeApp.seen.append(("GET", self.path, dict(self.headers), b""))
        # The real app authenticates every route, and a GET is the first call
        # any scan makes -- which is where a stale cached identity surfaces.
        if not self._auth_ok():
            return self._json(401, {"error": "unauthorized"})
        if self.path == "/api/teams":
            return self._json(200, {"teams": list(FakeApp.teams.values())})
        if self.path.startswith("/api/agents/"):
            # One agent, the full document. This is where model_parameters can
            # actually be read (see the listing below).
            aid = self.path.split("?")[0].rsplit("/", 1)[-1]
            if aid == FakeApp.fail_agent_get:
                FakeApp.fail_agent_get = None
                return self._json(500, {"error": "boom"})
            doc = FakeApp.agents.get(aid)
            return self._json(200, doc) if doc else self._json(404, {})
        if self.path.startswith("/api/agents"):
            # The real listing is a projection -- id, name, author, category,
            # is_promoted, updatedAt -- and does NOT carry model_parameters.
            # Reproduced here on purpose: a reconcile that reads the pinned
            # settings off the listing would see None for every agent and PATCH
            # on every single scan, and a fake that returned the whole document
            # would let that bug through.
            listed = [{k: v for k, v in a.items()
                       if k in ("id", "_id", "name", "author", "category", "is_promoted")}
                      for a in FakeApp.agents.values()]
            return self._json(200, {"data": listed})
        self._json(404, {})

    def do_DELETE(self):
        body = self._body()
        FakeApp.seen.append(("DELETE", self.path, dict(self.headers), body))
        if FakeApp.fail_next_delete:
            FakeApp.fail_next_delete = False
            return self._json(500, {"error": "boom"})
        for f in json.loads(body)["files"]:
            FakeApp.files.pop(f["file_id"], None)
        return self._json(200, {"message": "Files deleted successfully"})

    def do_PATCH(self):
        body = self._body()
        FakeApp.seen.append(("PATCH", self.path, dict(self.headers), body))
        if "Chrome/" not in self.headers.get("User-Agent", ""):
            return self._json(403, {"message": "Illegal request"})
        aid = self.path.split("?")[0].rsplit("/", 1)[-1]
        doc = FakeApp.agents.get(aid)
        if doc is None:
            return self._json(404, {})
        # A PATCH $sets the keys it is given -- which is exactly why sending
        # tool_resources would replace the whole object and drop the uploaded
        # file_ids. Merging at the top level here reproduces that.
        doc.update(json.loads(body))
        return self._json(200, doc)


def main():
    port = _free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), FakeApp)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        drives = pathlib.Path(tmp) / "drives"
        state = pathlib.Path(tmp) / "state"
        (drives / "legal").mkdir(parents=True)
        (drives / "hr").mkdir()
        (drives / "legal" / "policy.txt").write_text("자동연장 60일")
        (drives / "legal" / ".DS_Store").write_bytes(b"junk")
        (drives / "hr" / "~$draft.docx").write_bytes(b"lock")
        cfg = I.Config(app_url=f"http://127.0.0.1:{port}", email="ingest@box", password="pw",
                       jwt_secret=SECRET, drives_dir=str(drives), state_dir=str(state),
                       model="qwen2.5-7b", provider="NuFi", interval=0, share="team",
                       settle_scans=1)
        d = I.Ingester(cfg)
        d.scan()   # first pass: only records sizes (settle)
        heartbeat = state / "heartbeat"
        assert heartbeat.exists(), "scan() must touch a heartbeat file in the state dir"
        heartbeat_mtime_1 = heartbeat.stat().st_mtime
        time.sleep(0.01)
        d.scan()   # second pass: file is stable → uploads
        heartbeat_mtime_2 = heartbeat.stat().st_mtime
        assert heartbeat_mtime_2 > heartbeat_mtime_1, "heartbeat mtime must advance between scans"
        uploads = [s for s in FakeApp.seen if s[0] == "POST" and s[1] == "/api/files"]
        assert len(uploads) == 1, uploads
        assert b'name="tool_resource"\r\n\r\nfile_search' in uploads[0][3]
        # The app percent-decodes the multipart filename and its parser reads
        # header parameters as latin-1, so a raw UTF-8 name lands as mojibake.
        assert b'filename="policy.txt"' in uploads[0][3]
        assert b'name="endpoint"\r\n\r\nagents' in uploads[0][3]
        assert "Chrome/" in uploads[0][2]["User-Agent"]
        assert len(FakeApp.teams) == 2 and len(FakeApp.agents) == 2
        names = sorted(a["name"] for a in FakeApp.agents.values())
        assert names == ["Hr assistant", "Legal assistant"], names
        # The instruction carries the two rules a live box needs, both measured
        # rather than imagined -- see agent_instructions(). Without the search
        # rule the on-box 7B model answered from nothing while citing a real
        # filename; without the language rule it answered Korean questions in
        # Chinese.
        legal_agent = next(a for a in FakeApp.agents.values() if a["name"] == "Legal assistant")
        instructions = legal_agent["instructions"]
        assert "Legal drive" in instructions, instructions
        assert "Always use the file_search tool" in instructions, instructions
        assert "Never answer from your own knowledge" in instructions, instructions
        assert "same language the question was asked in" in instructions, instructions
        # Must NOT forbid tool-call syntax: a 7B model reads that as "do not
        # emit the tool call", and acceptance citations fell 8/32 -> 1/32 when
        # it did. This assertion is the guard against re-adding it.
        assert "tool-call syntax" not in instructions, instructions
        # Generation is pinned at creation, so an acceptance score is evidence
        # rather than a throw of the dice: temperature fixes the fact, the seed
        # fixes the wording.
        created = [json.loads(s[3]) for s in FakeApp.seen
                   if s[0] == "POST" and s[1] == "/api/agents"]
        assert len(created) == 2, created
        for payload in created:
            assert payload["model_parameters"] == {"temperature": 0, "seed": 7}, payload
        shares = [s for s in FakeApp.seen if s[0] == "POST" and "/agents/" in s[1]]
        assert len(shares) == 2
        st = json.loads((state / "state.json").read_text())
        assert st["files"]["legal/policy.txt"]["file_id"].startswith("srv-")
        # changed file → delete then upload (size must actually change: the
        # daemon's size+mtime fast path only re-hashes on a detectable diff,
        # and mtime is second-granularity, so a same-length rewrite within
        # the same wall-clock second would be invisible to it)
        time.sleep(0.01)
        (drives / "legal" / "policy.txt").write_text("자동연장 90일로 변경")
        d.scan()
        d.scan()
        deletes = [s for s in FakeApp.seen if s[0] == "DELETE"]
        assert len(deletes) == 1 and json.loads(deletes[0][3])["agent_id"].startswith("agent_")
        assert len([s for s in FakeApp.seen if s[0] == "POST" and s[1] == "/api/files"]) == 2
        # removed file → delete
        (drives / "legal" / "policy.txt").unlink()
        d.scan()
        assert len([s for s in FakeApp.seen if s[0] == "DELETE"]) == 2
        assert "legal/policy.txt" not in json.loads((state / "state.json").read_text())["files"]

        # a failed DELETE on the removal path must not drop state (no orphan):
        # the record stays so the next scan retries instead of abandoning the
        # server-side file/embedding.
        (drives / "legal" / "note.txt").write_text("note v1")
        d.scan()
        d.scan()
        st = json.loads((state / "state.json").read_text())
        note_id = st["files"]["legal/note.txt"]["file_id"]
        assert note_id in FakeApp.files

        (drives / "legal" / "note.txt").unlink()
        FakeApp.fail_next_delete = True
        d.scan()
        st = json.loads((state / "state.json").read_text())
        assert st["files"]["legal/note.txt"]["file_id"] == note_id, \
            "state must survive a failed delete"
        assert note_id in FakeApp.files, "server-side file must not be orphaned"
        assert FakeApp.fail_next_delete is False, "the failing attempt must have consumed the flag"

        d.scan()   # retry succeeds now that the flag is clear
        st = json.loads((state / "state.json").read_text())
        assert "legal/note.txt" not in st["files"]
        assert note_id not in FakeApp.files

        # a failed DELETE on the changed-file (delete-before-reupload) path
        # must not upload a fresh copy while the old one still lives server-side
        (drives / "legal" / "note2.txt").write_text("note2 v1")
        d.scan()
        d.scan()
        st = json.loads((state / "state.json").read_text())
        note2_id = st["files"]["legal/note2.txt"]["file_id"]
        uploads_before = len([s for s in FakeApp.seen if s[0] == "POST" and s[1] == "/api/files"])

        time.sleep(0.01)
        (drives / "legal" / "note2.txt").write_text("note2 v2 changed")
        FakeApp.fail_next_delete = True
        d.scan()
        posted = [s for s in FakeApp.seen if s[0] == "POST" and s[1] == "/api/files"]
        assert len(posted) == uploads_before, \
            "must not upload while the old copy's delete failed"
        st = json.loads((state / "state.json").read_text())
        assert st["files"]["legal/note2.txt"]["file_id"] == note2_id, "old file_id must be kept"
        assert note2_id in FakeApp.files, "old server-side copy must still exist"

        d.scan()   # delete succeeds now; re-upload proceeds
        st = json.loads((state / "state.json").read_text())
        assert st["files"]["legal/note2.txt"]["file_id"] != note2_id
        assert note2_id not in FakeApp.files
        posted = [s for s in FakeApp.seen if s[0] == "POST" and s[1] == "/api/files"]
        assert len(posted) == uploads_before + 1

        # a non-ASCII filename must reach the app percent-encoded: the app
        # decodeURIComponent()s the multipart filename (its own web client sends
        # encodeURIComponent(file.name)) and its parser reads header parameters
        # as latin-1, so a raw UTF-8 name lands in the file list and in every
        # citation as mojibake.
        korean = drives / "legal" / "계약검토_표준조항.txt"
        korean.write_text("자동연장 60일")
        d.scan()
        d.scan()
        body = [s for s in FakeApp.seen if s[0] == "POST" and s[1] == "/api/files"][-1][3]
        disposition = [ln for ln in body.split(b"\r\n") if b'name="file"' in ln][0]
        encoded = (b'filename="%EA%B3%84%EC%95%BD%EA%B2%80%ED%86%A0'
                   b'_%ED%91%9C%EC%A4%80%EC%A1%B0%ED%95%AD.txt"')
        assert encoded in disposition, disposition
        assert korean.name.encode() not in disposition, disposition

        # login exactly once; everything else self-minted
        assert len([s for s in FakeApp.seen if s[1] == "/api/auth/login"]) == 1

        # ...and once for the life of the state dir, not once per container
        # start: the id learned above is in state.json, so a restarted daemon
        # (or one whose admin has since changed their password) carries on
        # without ever presenting a password again.
        assert json.loads((state / "state.json").read_text())["user_id"] == USER_ID
        I.Ingester(cfg).scan()
        assert len([s for s in FakeApp.seen if s[1] == "/api/auth/login"]) == 1, \
            "a second daemon on the same state dir must reuse the stored id"
        # Agents created by this daemon are already pinned, so nothing above
        # this line has any reason to PATCH.
        assert not [s for s in FakeApp.seen if s[0] == "PATCH"], \
            "a freshly created agent is pinned at creation; no PATCH should be needed"

        # --- reconcile: an agent that predates MODEL_PARAMETERS -------------
        # A box upgraded in place keeps the agents it already has -- the daemon
        # finds them by name and never re-creates them -- so without a
        # reconcile step every existing department would go on sampling at the
        # default temperature and the evidence would still not reproduce.
        legal_agent_id = next(a["id"] for a in FakeApp.agents.values()
                              if a["name"] == "Legal assistant")
        FakeApp.agents[legal_agent_id].pop("model_parameters", None)
        file_ids_before = set(FakeApp.agents[legal_agent_id]
                              ["tool_resources"]["file_search"]["file_ids"])
        assert file_ids_before, "the agent must already own uploaded files"

        # A fresh state dir makes the daemon walk ensure_department again; the
        # agents already exist server-side, which is exactly the upgrade case.
        state2 = pathlib.Path(tmp) / "state2"
        cfg2 = I.Config(app_url=cfg.app_url, email=cfg.email, password=cfg.password,
                        jwt_secret=SECRET, drives_dir=str(drives), state_dir=str(state2),
                        model="qwen2.5-7b", provider="NuFi", interval=0, share="team",
                        settle_scans=1)
        mark = len(FakeApp.seen)
        I.Ingester(cfg2).scan()
        patches = [s for s in FakeApp.seen[mark:] if s[0] == "PATCH"]

        # exactly one PATCH, and it is for the agent that lost its parameters
        assert len(patches) == 1, [(p[0], p[1], p[3]) for p in patches]
        assert patches[0][1] == f"/api/agents/{legal_agent_id}", patches[0][1]
        # the gated routes ban an account for hours on a bare User-Agent
        assert "Chrome/" in patches[0][2].get("User-Agent", ""), patches[0][2]

        # carrying model_parameters and NOTHING else. tool_resources in a PATCH
        # would $set the whole object and silently detach every uploaded
        # document, leaving an agent that looks configured and retrieves
        # nothing -- so assert the key is absent, not merely that files
        # survived by luck.
        sent = json.loads(patches[0][3])
        assert sent == {"model_parameters": {"temperature": 0, "seed": 7}}, sent
        assert "tool_resources" not in sent, sent
        # (a fresh state dir also makes the daemon re-upload, so file_ids grows;
        # what must never happen is one of the originals disappearing)
        file_ids_after = set(FakeApp.agents[legal_agent_id]
                             ["tool_resources"]["file_search"]["file_ids"])
        assert file_ids_before <= file_ids_after, \
            f"the reconcile PATCH dropped files: {file_ids_before - file_ids_after}"

        # ...and it is idempotent: a second walk over an already-pinned agent
        # sends no PATCH at all. This is what fails if the reconcile reads
        # model_parameters off the listing projection, which never carries it.
        state3 = pathlib.Path(tmp) / "state3"
        cfg3 = I.Config(**{**cfg2.__dict__, "state_dir": str(state3)})
        mark = len(FakeApp.seen)
        I.Ingester(cfg3).scan()
        assert not [s for s in FakeApp.seen[mark:] if s[0] == "PATCH"], \
            "an already-pinned agent must not be PATCHed again on every scan"

        # --- the real upgrade shape: state KEPT, agents unpinned ------------
        # An upgraded box does not lose /state, so every long-lived department
        # takes ensure_department's cached path and never reaches
        # find_or_create_agent. Reconciling only there would leave exactly the
        # agents that need pinning unpinned, forever.
        FakeApp.agents[legal_agent_id].pop("model_parameters", None)
        upgraded = I.Ingester(cfg2)          # state2 already lists both departments
        assert upgraded.state["departments"], "this case is only meaningful with state present"
        mark = len(FakeApp.seen)
        upgraded.scan()
        patches = [s for s in FakeApp.seen[mark:] if s[0] == "PATCH"]
        assert len(patches) == 1, [(p[1], p[3]) for p in patches]
        assert patches[0][1] == f"/api/agents/{legal_agent_id}", patches[0][1]
        assert json.loads(patches[0][3]) == {"model_parameters": {"temperature": 0, "seed": 7}}
        # ...and still only once per process, not once per 20-second scan
        mark = len(FakeApp.seen)
        upgraded.scan()
        upgraded.scan()
        assert not [s for s in FakeApp.seen[mark:] if s[0] == "PATCH"], \
            "the reconcile must be memoised per process, not repeated every scan"

        # --- reconcile: the system prompt drifts too -------------------------
        # Every rule in agent_instructions() is a failure measured on a live
        # box, and each correction was shipped as a new image. An upgraded box
        # keeps its agents, so an agent created by an older image goes on
        # answering from nothing under the old prompt no matter how many times
        # the instruction is fixed -- unless the reconcile carries it.
        FakeApp.agents[legal_agent_id]["instructions"] = "You are helpful."
        stale_prompt = I.Ingester(cfg2)
        mark = len(FakeApp.seen)
        stale_prompt.scan()
        patches = [s for s in FakeApp.seen[mark:] if s[0] == "PATCH"]
        assert len(patches) == 1, [(p[1], p[3]) for p in patches]
        assert patches[0][1] == f"/api/agents/{legal_agent_id}", patches[0][1]
        sent = json.loads(patches[0][3])
        assert sent == {"instructions": I.agent_instructions("Legal")}, sent
        # the same rule as the model_parameters PATCH: tool_resources in a
        # PATCH $sets the whole object and detaches every uploaded document
        assert "tool_resources" not in sent, sent
        assert FakeApp.agents[legal_agent_id]["tool_resources"]["file_search"]["file_ids"]

        # both stale → still ONE PATCH, carrying both keys
        FakeApp.agents[legal_agent_id]["instructions"] = "You are helpful."
        FakeApp.agents[legal_agent_id].pop("model_parameters", None)
        mark = len(FakeApp.seen)
        I.Ingester(cfg2).scan()
        patches = [s for s in FakeApp.seen[mark:] if s[0] == "PATCH"]
        assert len(patches) == 1, [(p[1], p[3]) for p in patches]
        assert json.loads(patches[0][3]) == {
            "model_parameters": {"temperature": 0, "seed": 7},
            "instructions": I.agent_instructions("Legal"),
        }, patches[0][3]

        # --- a failed GET must not count as "reconciled" ---------------------
        # Marking the agent done before the GET meant one refused connection --
        # the app restarting, a slow boot -- skipped that agent until the next
        # container restart, which on a box nobody restarts is forever.
        FakeApp.agents[legal_agent_id].pop("model_parameters", None)
        FakeApp.fail_agent_get = legal_agent_id
        retrying = I.Ingester(cfg2)
        mark = len(FakeApp.seen)
        retrying.scan()
        assert FakeApp.fail_agent_get is None, "the failing GET must have consumed the flag"
        assert not [s for s in FakeApp.seen[mark:] if s[0] == "PATCH"], \
            "nothing to PATCH with: the agent could not be read"
        mark = len(FakeApp.seen)
        retrying.scan()          # same process, no restart
        patches = [s for s in FakeApp.seen[mark:] if s[0] == "PATCH"]
        assert len(patches) == 1, "the next scan must retry the agent it could not read"
        assert patches[0][1] == f"/api/agents/{legal_agent_id}", patches[0][1]

        # --- a stale cached id costs one login, not a dead daemon ------------
        # The state volume can outlive the database (a restore, a wiped Mongo),
        # leaving an id the app has never heard of. Every call would 401
        # forever if the daemon simply trusted what it had cached.
        logins = len([s for s in FakeApp.seen if s[1] == "/api/auth/login"])
        stale_id = I.Ingester(cfg)
        stale_id.app.user_id = "64bffffffffffffffffffffff"
        stale_id.scan()
        assert len([s for s in FakeApp.seen if s[1] == "/api/auth/login"]) == logins + 1, \
            "a 401 must trigger exactly one fresh login"
        assert json.loads((state / "state.json").read_text())["user_id"] == USER_ID, \
            "the id learned by that login must replace the stale one on disk"
    print("PASS")


if __name__ == "__main__":
    main()
