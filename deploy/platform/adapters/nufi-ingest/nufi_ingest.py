#!/usr/bin/env python3
"""nufi-ingest: department drive folders → agent Knowledge in the NuFi app.

Watches NUFI_DRIVES_DIR/<dept>/ (polling; no inotify, so it works on a bind
mount from any host OS). For every department folder it ensures one team
("<Dept>"), one agent ("<Dept> assistant", author = this service account) and a
viewer grant of the agent to the team. Every stable, supported file is uploaded
through POST /api/files with agent_id + tool_resource=file_search, which embeds
it in rag_api and attaches it to the agent in one call. A changed file is
deleted and re-uploaded; a removed file is deleted. State lives in
NUFI_STATE_DIR/state.json so a restart does not re-embed the world.

Auth: one login to learn the service account's id, then self-minted HS256 JWTs
signed with JWT_SECRET (the app's strategy checks only payload.id). Every call
to /api/files and /api/agents carries a Chrome User-Agent; a single bare UA
bans the account for two hours. stdlib only.
"""
import base64
import hashlib
import hmac
import io
import json
import logging
import mimetypes
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass

LOG = logging.getLogger("nufi-ingest")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")
SUPPORTED = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".csv", ".json", ".html", ".htm"}
IGNORED_PREFIXES = (".", "~$", "._")
UPLOADS_PER_WINDOW = 40          # app default is 50 per 15 min per user
WINDOW_SECONDS = 15 * 60


@dataclass
class Config:
    app_url: str
    email: str
    password: str
    jwt_secret: str
    drives_dir: str
    state_dir: str
    model: str
    provider: str = "NuFi"
    interval: float = 20.0
    share: str = "team"          # team | public | none
    settle_scans: int = 2        # a file must look identical this many scans in a row

    @classmethod
    def from_env(cls):
        e = os.environ
        return cls(app_url=e["NUFI_APP_URL"].rstrip("/"), email=e["NUFI_INGEST_EMAIL"],
                   password=e["NUFI_INGEST_PASSWORD"], jwt_secret=e["JWT_SECRET"],
                   drives_dir=e.get("NUFI_DRIVES_DIR", "/drives"), state_dir=e.get("NUFI_STATE_DIR", "/state"),
                   model=e["NUFI_MODEL"], provider=e.get("NUFI_PROVIDER", "NuFi"),
                   interval=float(e.get("NUFI_INGEST_INTERVAL", "20")), share=e.get("NUFI_INGEST_SHARE", "team"))


def _b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def mint_jwt(user_id, secret, ttl=3600):
    """HS256 {id} — all the app's JWT strategy reads."""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    now = int(time.time())
    payload = _b64url(json.dumps({"id": user_id, "iat": now, "exp": now + ttl}, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(sig)}"


def display_name(dept):
    return dept.replace("_", " ").replace("-", " ").strip().capitalize()


def agent_instructions(name):
    """The system prompt for a department assistant.

    The two rules after the first one are not style preferences; each one is a
    failure observed on a live box running the default on-box model
    (qwen2.5:7b behind the local gateway), where the whole corpus and every
    question are Korean:

    * Language. With an English-only instruction the model answered Korean
      questions in Chinese and Vietnamese -- not a translation of the right
      answer, but a different answer that no Korean reader can check against
      the source. It has no way to know which language to use unless it is
      told, so the rule ties the answer to the question rather than naming a
      language, which also keeps a non-Korean drive working.

    * Tool narration. The model leaked its own function-calling scaffolding
      into the answer -- '让我使用file_search工具', a bare
      '{"name": "file_search", ...}', a stray '</tool_call>'. Every one of
      those reached the user as the beginning of the answer.

    Written in English deliberately: the corpus language is whatever the drive
    holds, and pinning the instruction to Korean would break a box whose
    documents are not.
    """
    return (
        f"You are the {name} department's assistant. Answer only from the documents in the "
        f"{name} drive, cite the file you used, and say plainly when the documents do not "
        "cover a question.\n"
        "Always write your answer in the same language the question was asked in.\n"
        "Never describe the tools you are about to use and never show tool-call syntax; "
        "search first, then reply with the answer alone."
    )


class AppError(RuntimeError):
    pass


class App:
    """The slice of the NuFi app API the daemon uses."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.user_id = None
        self._token = None
        self._token_exp = 0

    def _request(self, method, path, body=None, headers=None, browser=False, auth=True):
        url = self.cfg.app_url + path
        data = body
        h = {"Accept": "application/json"}
        if browser:
            h["User-Agent"] = UA
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        if auth:
            h["Authorization"] = "Bearer " + self.token()
        h.update(headers or {})
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            raise AppError(f"{method} {path} -> {e.code}: {raw[:300]}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            # connection refused, DNS failure, read timeout, etc. — a blip,
            # not an HTTP error; callers already handle AppError per item.
            raise AppError(f"{method} {path} -> {e}") from e

    def login(self):
        status, body = self._request("POST", "/api/auth/login",
                                     {"email": self.cfg.email, "password": self.cfg.password}, auth=False)
        user = body.get("user") or {}
        self.user_id = user.get("id") or user.get("_id")
        if not self.user_id:
            raise AppError(f"login returned no user id: {body}")
        LOG.info("logged in as %s (%s)", self.cfg.email, user.get("role"))

    def token(self):
        if self.user_id is None:
            self.login()
        if time.time() > self._token_exp - 60:
            self._token = mint_jwt(self.user_id, self.cfg.jwt_secret)
            self._token_exp = time.time() + 3600
        return self._token

    # --- teams -------------------------------------------------------------
    def find_or_create_team(self, name):
        _, body = self._request("GET", "/api/teams")
        for t in body.get("teams", []):
            if t.get("name") == name:
                return t["_id"]
        _, body = self._request("POST", "/api/teams", {"name": name, "description": f"{name} department"})
        return body["team"]["_id"]

    # --- agents ------------------------------------------------------------
    def find_or_create_agent(self, name, instructions):
        _, body = self._request("GET", "/api/agents?limit=200", browser=True)
        for a in body.get("data", []):
            if a.get("name") == name:
                return a["id"], a.get("_id")
        _, body = self._request("POST", "/api/agents", {
            "provider": self.cfg.provider, "model": self.cfg.model, "name": name,
            "instructions": instructions, "tools": ["file_search"],
        }, browser=True)
        return body["id"], body.get("_id")

    def share_agent(self, team_id, agent_id, agent_oid):
        if self.cfg.share == "team":
            try:
                self._request("POST", f"/api/teams/{team_id}/agents/{agent_id}", {})
            except AppError as e:
                if "409" not in str(e):
                    raise
        elif self.cfg.share == "public":
            self._request("PUT", f"/api/permissions/agent/{agent_oid}", {
                "updated": [], "removed": [], "public": True, "publicAccessRoleId": "agent_viewer",
            }, browser=True)

    # --- files -------------------------------------------------------------
    def upload(self, path, agent_id):
        boundary = "----nufi" + uuid.uuid4().hex
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        fields = {"file_id": str(uuid.uuid4()), "endpoint": "agents",
                  "tool_resource": "file_search", "agent_id": agent_id}
        buf = io.BytesIO()
        for k, v in fields.items():
            buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        # The app percent-decodes the multipart filename (its own web client
        # sends encodeURIComponent(file.name)), and the multipart parser reads
        # header parameters as latin-1. A raw UTF-8 name therefore arrives as
        # mojibake — "계약검토_표준조항.txt" became "ê³ì½ê²í _íì¤ì¡°í­.txt" —
        # in the file list and in every citation.
        filename = urllib.parse.quote(path.name)
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
                  f"Content-Type: {ctype}\r\n\r\n".encode())
        buf.write(path.read_bytes())
        buf.write(f"\r\n--{boundary}--\r\n".encode())
        _, body = self._request("POST", "/api/files", buf.getvalue(), browser=True,
                                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        if not body.get("file_id"):
            raise AppError(f"upload of {path.name} returned no file_id: {body}")
        return body["file_id"], body.get("filepath", "vectordb"), bool(body.get("embedded"))

    def delete(self, file_id, filepath, agent_id):
        self._request("DELETE", "/api/files", {
            "files": [{"file_id": file_id, "filepath": filepath}],
            "agent_id": agent_id, "tool_resource": "file_search",
        }, browser=True)


class Ingester:
    def __init__(self, cfg, app=None):
        self.cfg = cfg
        self.app = app or App(cfg)
        self.state_path = pathlib.Path(cfg.state_dir) / "state.json"
        self.state = {"departments": {}, "files": {}}
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text())
        self._pending = {}       # rel -> (size, mtime, scans seen identical)
        self._upload_times = []

    # --- persistence -------------------------------------------------------
    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1, ensure_ascii=False))
        tmp.replace(self.state_path)

    def _heartbeat(self):
        # touched at the end of every scan(), successful or not, so the
        # container healthcheck can tell "the daemon is alive" apart from
        # "the /state mount exists" (which is always true).
        path = pathlib.Path(self.cfg.state_dir) / "heartbeat"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)

    # --- departments -------------------------------------------------------
    def ensure_department(self, dept):
        d = self.state["departments"].get(dept)
        if d:
            return d
        name = display_name(dept)
        team_id = self.app.find_or_create_team(name) if self.cfg.share == "team" else None
        agent_id, agent_oid = self.app.find_or_create_agent(
            f"{name} assistant", agent_instructions(name))
        self.app.share_agent(team_id, agent_id, agent_oid)
        d = {"team_id": team_id, "agent_id": agent_id, "agent_oid": agent_oid}
        self.state["departments"][dept] = d
        self.save()
        LOG.info("department %s → team %s, agent %s", dept, team_id, agent_id)
        return d

    # --- scanning ----------------------------------------------------------
    def _department_dirs(self):
        root = pathlib.Path(self.cfg.drives_dir)
        if not root.exists():
            return []
        return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))

    def _listing(self):
        root = pathlib.Path(self.cfg.drives_dir)
        out = {}
        for dept_dir in self._department_dirs():
            for p in sorted(dept_dir.rglob("*")):
                if not p.is_file() or p.suffix.lower() not in SUPPORTED:
                    continue
                if any(part.startswith(IGNORED_PREFIXES) for part in p.relative_to(root).parts):
                    continue
                st = p.stat()
                out[p.relative_to(root).as_posix()] = (p, dept_dir.name, st.st_size, int(st.st_mtime))
        return out

    def _stable(self, rel, size, mtime):
        prev = self._pending.get(rel)
        if prev and prev[0] == size and prev[1] == mtime:
            self._pending[rel] = (size, mtime, prev[2] + 1)
        else:
            self._pending[rel] = (size, mtime, 1)
        return self._pending[rel][2] >= self.cfg.settle_scans

    def _throttle(self):
        now = time.time()
        self._upload_times = [t for t in self._upload_times if now - t < WINDOW_SECONDS]
        if len(self._upload_times) >= UPLOADS_PER_WINDOW:
            wait = WINDOW_SECONDS - (now - self._upload_times[0]) + 1
            LOG.warning("upload window full; sleeping %.0fs", wait)
            time.sleep(max(wait, 0))
        self._upload_times.append(time.time())

    def scan(self):
        # a department folder becomes an agent as soon as it exists, even before
        # it holds a single supported file
        for dept_dir in self._department_dirs():
            self.ensure_department(dept_dir.name)
        listing = self._listing()
        # removals
        for rel in list(self.state["files"]):
            if rel not in listing:
                rec = self.state["files"][rel]
                dept = rel.split("/", 1)[0]
                agent = self.state["departments"].get(dept, {}).get("agent_id")
                try:
                    self.app.delete(rec["file_id"], rec["filepath"], agent)
                    LOG.info("removed %s (%s)", rel, rec["file_id"])
                except AppError as e:
                    # keep the state record so the next scan retries the delete
                    # instead of orphaning the server-side file/embedding
                    LOG.error("delete %s failed: %s", rel, e)
                    continue
                del self.state["files"][rel]
                self.save()
        # additions and changes
        for rel, (path, dept, size, mtime) in listing.items():
            rec = self.state["files"].get(rel)
            if rec and rec["size"] == size and rec["mtime"] == mtime:
                continue
            if not self._stable(rel, size, mtime):
                continue
            d = self.ensure_department(dept)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if rec and rec.get("sha256") == digest:
                rec.update({"size": size, "mtime": mtime}); self.save(); continue
            if rec:
                try:
                    self.app.delete(rec["file_id"], rec["filepath"], d["agent_id"])
                except AppError as e:
                    # do not upload a fresh copy while the old one still lives
                    # server-side; keep the old record and retry next scan
                    LOG.error("delete before re-upload %s failed: %s", rel, e)
                    continue
            try:
                self._throttle()
                file_id, filepath, embedded = self.app.upload(path, d["agent_id"])
            except AppError as e:
                LOG.error("upload %s failed: %s", rel, e)
                continue
            self.state["files"][rel] = {"file_id": file_id, "filepath": filepath, "size": size,
                                        "mtime": mtime, "sha256": digest, "embedded": embedded}
            self.save()
            LOG.info("%s %s → %s (embedded=%s)", "updated" if rec else "added", rel, file_id, embedded)
            self._pending.pop(rel, None)
        self._heartbeat()

    def run(self):
        LOG.info("watching %s every %.0fs", self.cfg.drives_dir, self.cfg.interval)
        while True:
            try:
                self.scan()
            except Exception as e:      # keep the loop alive; the next scan retries
                LOG.error("scan failed: %s", e)
            time.sleep(self.cfg.interval)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    Ingester(Config.from_env()).run()


if __name__ == "__main__":
    main()
