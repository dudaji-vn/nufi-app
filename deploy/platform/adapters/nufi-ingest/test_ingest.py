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
import os
import pathlib
import socket
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import nufi_ingest as I

# the delete-retry scenarios below deliberately trigger LOG.error() inside the
# daemon; keep that off stderr so the only thing this script prints is PASS.
logging.getLogger("nufi-ingest").addHandler(logging.NullHandler())
logging.getLogger("nufi-ingest").propagate = False

SECRET = "test-secret"
USER_ID = "64b000000000000000000001"


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _b64url_decode(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class FakeApp(BaseHTTPRequestHandler):
    seen = []          # (method, path, headers, body-bytes)
    agents = {}        # id -> doc
    teams = {}         # _id -> doc
    files = {}         # file_id -> doc
    counter = 0
    fail_next_delete = False   # set True to make the next DELETE return 500 once

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _auth_ok(self):
        tok = (self.headers.get("Authorization") or "").replace("Bearer ", "")
        try:
            h, p, s = tok.split(".")
            expect = hmac.new(SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
            return hmac.compare_digest(_b64url_decode(s), expect) and json.loads(_b64url_decode(p))["id"] == USER_ID
        except Exception:
            return False

    def do_POST(self):
        body = self._body()
        FakeApp.seen.append(("POST", self.path, dict(self.headers), body))
        if self.path == "/api/auth/login":
            return self._json(200, {"token": "login-token", "user": {"id": USER_ID, "role": "ADMIN"}})
        if not self._auth_ok():
            return self._json(401, {"error": "unauthorized"})
        if self.path in ("/api/files", "/api/agents") and "Chrome/" not in self.headers.get("User-Agent", ""):
            return self._json(403, {"message": "Illegal request"})
        if self.path == "/api/teams":
            FakeApp.counter += 1; tid = f"t{FakeApp.counter}"
            FakeApp.teams[tid] = {"_id": tid, "name": json.loads(body)["name"]}
            return self._json(201, {"team": FakeApp.teams[tid]})
        if self.path == "/api/agents":
            FakeApp.counter += 1; aid = f"agent_{FakeApp.counter}"
            doc = {"id": aid, "_id": f"oid{FakeApp.counter}", "tool_resources": {}, **json.loads(body)}
            FakeApp.agents[aid] = doc
            return self._json(201, doc)
        if self.path.startswith("/api/teams/") and "/agents/" in self.path:
            return self._json(201, {"success": True})
        if self.path == "/api/files":
            raw = body
            def field(name):
                m = raw.find(b'name="' + name.encode() + b'"'); j = raw.find(b"\r\n\r\n", m); k = raw.find(b"\r\n--", j)
                return raw[j + 4:k].decode() if m >= 0 else None
            FakeApp.counter += 1; fid = f"srv-{FakeApp.counter}"
            FakeApp.files[fid] = {"file_id": fid, "filepath": "vectordb", "agent_id": field("agent_id"),
                                  "tool_resource": field("tool_resource"), "endpoint": field("endpoint")}
            FakeApp.agents[field("agent_id")]["tool_resources"].setdefault("file_search", {}).setdefault("file_ids", []).append(fid)
            return self._json(200, {"message": "ok", "file_id": fid, "filepath": "vectordb", "embedded": True})
        self._json(404, {"error": self.path})

    def do_GET(self):
        FakeApp.seen.append(("GET", self.path, dict(self.headers), b""))
        if self.path == "/api/teams":
            return self._json(200, {"teams": list(FakeApp.teams.values())})
        if self.path.startswith("/api/agents"):
            return self._json(200, {"data": list(FakeApp.agents.values())})
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
        FakeApp.seen.append(("PATCH", self.path, dict(self.headers), self._body()))
        return self._json(200, {})


def main():
    port = _free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), FakeApp)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        drives = pathlib.Path(tmp) / "drives"; state = pathlib.Path(tmp) / "state"
        (drives / "legal").mkdir(parents=True); (drives / "hr").mkdir()
        (drives / "legal" / "policy.txt").write_text("자동연장 60일")
        (drives / "legal" / ".DS_Store").write_bytes(b"junk")
        (drives / "hr" / "~$draft.docx").write_bytes(b"lock")
        cfg = I.Config(app_url=f"http://127.0.0.1:{port}", email="ingest@box", password="pw",
                       jwt_secret=SECRET, drives_dir=str(drives), state_dir=str(state),
                       model="qwen2.5-7b", provider="NuFi", interval=0, share="team", settle_scans=1)
        d = I.Ingester(cfg)
        d.scan()   # first pass: only records sizes (settle)
        d.scan()   # second pass: file is stable → uploads
        uploads = [s for s in FakeApp.seen if s[0] == "POST" and s[1] == "/api/files"]
        assert len(uploads) == 1, uploads
        assert b'name="tool_resource"\r\n\r\nfile_search' in uploads[0][3]
        assert b'name="endpoint"\r\n\r\nagents' in uploads[0][3]
        assert "Chrome/" in uploads[0][2]["User-Agent"]
        assert len(FakeApp.teams) == 2 and len(FakeApp.agents) == 2
        names = sorted(a["name"] for a in FakeApp.agents.values())
        assert names == ["Hr assistant", "Legal assistant"], names
        shares = [s for s in FakeApp.seen if s[0] == "POST" and "/agents/" in s[1]]
        assert len(shares) == 2
        st = json.loads((state / "state.json").read_text())
        assert st["files"]["legal/policy.txt"]["file_id"].startswith("srv-")
        # changed file → delete then upload (size must actually change: the
        # daemon's size+mtime fast path only re-hashes on a detectable diff,
        # and mtime is second-granularity, so a same-length rewrite within
        # the same wall-clock second would be invisible to it)
        time.sleep(0.01); (drives / "legal" / "policy.txt").write_text("자동연장 90일로 변경")
        d.scan(); d.scan()
        deletes = [s for s in FakeApp.seen if s[0] == "DELETE"]
        assert len(deletes) == 1 and json.loads(deletes[0][3])["agent_id"].startswith("agent_")
        assert len([s for s in FakeApp.seen if s[0] == "POST" and s[1] == "/api/files"]) == 2
        # removed file → delete
        (drives / "legal" / "policy.txt").unlink(); d.scan()
        assert len([s for s in FakeApp.seen if s[0] == "DELETE"]) == 2
        assert "legal/policy.txt" not in json.loads((state / "state.json").read_text())["files"]

        # a failed DELETE on the removal path must not drop state (no orphan):
        # the record stays so the next scan retries instead of abandoning the
        # server-side file/embedding.
        (drives / "legal" / "note.txt").write_text("note v1")
        d.scan(); d.scan()
        note_id = json.loads((state / "state.json").read_text())["files"]["legal/note.txt"]["file_id"]
        assert note_id in FakeApp.files

        (drives / "legal" / "note.txt").unlink()
        FakeApp.fail_next_delete = True
        d.scan()
        st = json.loads((state / "state.json").read_text())
        assert st["files"]["legal/note.txt"]["file_id"] == note_id, "state must survive a failed delete"
        assert note_id in FakeApp.files, "server-side file must not be orphaned"
        assert FakeApp.fail_next_delete is False, "the failing attempt must have consumed the flag"

        d.scan()   # retry succeeds now that the flag is clear
        st = json.loads((state / "state.json").read_text())
        assert "legal/note.txt" not in st["files"]
        assert note_id not in FakeApp.files

        # a failed DELETE on the changed-file (delete-before-reupload) path
        # must not upload a fresh copy while the old one still lives server-side
        (drives / "legal" / "note2.txt").write_text("note2 v1")
        d.scan(); d.scan()
        note2_id = json.loads((state / "state.json").read_text())["files"]["legal/note2.txt"]["file_id"]
        uploads_before = len([s for s in FakeApp.seen if s[0] == "POST" and s[1] == "/api/files"])

        time.sleep(0.01); (drives / "legal" / "note2.txt").write_text("note2 v2 changed")
        FakeApp.fail_next_delete = True
        d.scan()
        assert len([s for s in FakeApp.seen if s[0] == "POST" and s[1] == "/api/files"]) == uploads_before, \
            "must not upload while the old copy's delete failed"
        st = json.loads((state / "state.json").read_text())
        assert st["files"]["legal/note2.txt"]["file_id"] == note2_id, "old file_id must be kept"
        assert note2_id in FakeApp.files, "old server-side copy must still exist"

        d.scan()   # delete succeeds now; re-upload proceeds
        st = json.loads((state / "state.json").read_text())
        assert st["files"]["legal/note2.txt"]["file_id"] != note2_id
        assert note2_id not in FakeApp.files
        assert len([s for s in FakeApp.seen if s[0] == "POST" and s[1] == "/api/files"]) == uploads_before + 1

        # login exactly once; everything else self-minted
        assert len([s for s in FakeApp.seen if s[1] == "/api/auth/login"]) == 1
        assert not [s for s in FakeApp.seen if s[0] == "PATCH"]
    print("PASS")


if __name__ == "__main__":
    main()
