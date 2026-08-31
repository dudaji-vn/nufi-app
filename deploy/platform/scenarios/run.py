#!/usr/bin/env python3
"""Run the department scenarios against a live MeshBox box and record what happened.

The appliance's own rule (appliance `docs/GUARDRAILS.md`) is that a use story may
not be published unless the thing it describes was actually done. So this runner
does not illustrate a scenario -- it *performs* one, through the box's public
`/api/v1` surface, and writes down the real request and the real response.

Per department it walks the daily triad the product introduction names:

    shared drive  ->  RAG answer with sources  ->  agent routine

and then checks each answer. An extraction question must contain the fact the
document states; an out-of-scope question must be refused rather than answered.
A check that fails is written down as a failure. Nothing here retries until it
looks good, and nothing is summarised away: the evidence file is the transcript.

Usage:
    python3 run.py --base http://127.0.0.1:8080 --user admin --password meshbox
    python3 run.py --only hr           # one department
"""
import argparse
import base64
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REFUSAL_MARKERS = ("모르", "모릅", "없습니다", "찾을 수 없", "확인할 수 없",
                   "확인되지 않", "알 수 없", "제공되지 않", "언급되지 않",
                   "포함되어 있지 않",
                   # The model sometimes declines correctly but slips out of
                   # Korean mid-sentence. That is a different defect from
                   # inventing an answer, and conflating the two would hide the
                   # one that matters, so refusals are recognised in the drifted
                   # languages too and the drift is reported separately.
                   "无法回答", "并未", "未提及", "没有提到",
                   "don't know", "not mentioned", "no information")


def drifted(text):
    """True when a Korean answer contains Han characters Korean prose would not.

    A crude but sufficient tell: the on-box model occasionally finishes a Korean
    sentence in Chinese. For a product sold to Korean departments that is a
    defect worth naming, even when the answer is otherwise right.
    """
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


class Box:
    """The box's /api/v1 surface, as a person's session sees it."""

    def __init__(self, base, timeout=600.0):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.token = ""

    def call(self, method, path, payload=None):
        url = self.base + path
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                body = json.loads(raw) if raw else {}
                return resp.status, body, time.time() - started
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"error": raw[:300]}
            return exc.code, body, time.time() - started
        except (urllib.error.URLError, TimeoutError) as exc:
            return 0, {"error": f"unreachable: {getattr(exc, 'reason', exc)}"}, \
                time.time() - started

    def login(self, user, password):
        code, body, _ = self.call("POST", "/api/login",
                                  {"username": user, "password": password})
        if code != 200 or not body.get("session"):
            raise SystemExit(f"login failed: HTTP {code} {body}")
        self.token = body["session"]


def judge(kind, answer, expect):
    """Did the box do what this question asked of it?

    Two different things are being checked. An extraction question is right when
    the stated fact is in the answer. An out-of-scope question is right when the
    box *declines* -- inventing a plausible answer there is the failure mode that
    matters most, so a fluent reply with no refusal marker counts as wrong.
    """
    text = (answer or "").strip()
    if not text:
        return False, "empty answer"
    if kind == "refuse":
        if any(m in text for m in REFUSAL_MARKERS):
            return True, "declined, as it should"
        return False, "answered a question the document does not cover"
    if expect and expect in text:
        return True, f"states {expect!r}"
    return False, f"does not state {expect!r}"


def run_department(box, dept, out):
    name, did = dept["department"], dept["id"]
    out(f"\n## {name}\n")
    out(f"> {dept['why']}\n")
    result = {"id": did, "department": name, "checks": [], "notes": []}

    # --- 1. the shared drive -------------------------------------------------
    code, body, _ = box.call("POST", "/api/v1/drives",
                             {"name": dept["drive"], "desc": f"{name} 공유함"})
    if code == 201:
        drive_id = body["drive"]["id"]
    else:
        # A drive that already exists is fine; find it rather than fail. Match on
        # id and share as well as name: the box ships seeded department drives
        # whose id is "legal" while their display name is "법무 공유", so matching
        # on name alone silently skips the whole department.
        _, listing, _ = box.call("GET", "/api/v1/drives")
        want = dept["drive"]
        match = [d for d in listing.get("drives", [])
                 if want in (d.get("id"), d.get("share"), d.get("name"))]
        if not match:
            out(f"- drive `{dept['drive']}` could not be created: HTTP {code} {body}\n")
            result["notes"].append(f"drive create failed: {code}")
            return result
        drive_id = match[0]["id"]
    out(f"공유 드라이브 `{dept['drive']}` (id `{drive_id}`)\n")

    for doc in dept["documents"]:
        blob = base64.b64encode(doc["text"].encode("utf-8")).decode()
        code, body, _ = box.call("POST", f"/api/v1/drives/{drive_id}/files",
                                 {"name": doc["name"], "content_b64": blob,
                                  "content_type": "text/plain; charset=utf-8"})
        out(f"- 드라이브 업로드 `{doc['name']}` → HTTP {code}\n")

        # --- 2. the same document becomes answerable knowledge ---------------
        code, body, _ = box.call("POST", "/api/v1/rag/documents",
                                 {"name": doc["name"], "text": doc["text"]})
        doc_rec = body.get("document", body)
        out(f"- RAG 색인 `{doc['name']}` → HTTP {code} "
            f"`{json.dumps(doc_rec, ensure_ascii=False)[:120]}`\n")
        if code not in (200, 201):
            result["notes"].append(f"rag ingest failed for {doc['name']}: {code}")

    # --- 3. the questions a person in this department actually asks ----------
    out("\n| 질문 | 답변 | 근거 | 판정 |\n|---|---|---|---|\n")
    for q in dept["questions"]:
        code, body, secs = box.call("POST", "/api/v1/rag/query", {"question": q["ask"]})
        answer = (body.get("answer") or body.get("error") or "").strip()
        sources = body.get("sources") or []
        ok, why = (False, f"HTTP {code}") if code != 200 else \
            judge(q["kind"], answer, q.get("expect"))
        drift = drifted(answer)
        if drift:
            why += "; drifted out of Korean"
        result["checks"].append({"ask": q["ask"], "kind": q["kind"], "http": code,
                                 "answer": answer, "sources": sources,
                                 "ok": ok, "drift": drift, "why": why,
                                 "seconds": round(secs, 1)})
        cell = answer.replace("\n", " ").replace("|", "\\|")
        out(f"| {q['ask']} | {cell[:150]} | {', '.join(sources) or '—'} | "
            f"{'PASS' if ok else 'FAIL'} — {why} |\n")

    return result


def run_routine(box, routine_id, out):
    """Trigger one agent routine and record exactly what came back.

    Recorded separately from the department walk because the portal's run call
    carries only `{routine_id, routine}` -- the routine's *name*, with no channel
    for the meeting or the documents it is supposed to act on. Whatever the model
    answers to a bare title is written down as-is.
    """
    code, body, secs = box.call("POST", f"/api/v1/agent/routines/{routine_id}/run", {})
    run = body.get("run", body)
    out(f"\n- `{routine_id}` → HTTP {code}, status `{run.get('status')}`, "
        f"{secs:.0f}s\n\n```\n{(run.get('output') or run.get('error') or '')[:400]}\n```\n")
    return {"routine_id": routine_id, "http": code, "status": run.get("status"),
            "output": run.get("output", ""), "seconds": round(secs, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8080")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="meshbox")
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=str(HERE / "evidence"))
    args = ap.parse_args()

    depts = json.loads((HERE / "departments.json").read_text())["departments"]
    if args.only:
        depts = [d for d in depts if d["id"] == args.only]
        if not depts:
            raise SystemExit(f"no such department: {args.only}")

    box = Box(args.base)
    box.login(args.user, args.password)

    _, status, _ = box.call("GET", "/api/v1/ai/status")
    modules = {m["id"]: m["status"] for m in status.get("modules", [])}

    lines = []
    def out(text):
        lines.append(text)
        sys.stdout.write(text)

    out("# 부서별 시나리오 — 실제 실행 기록\n\n")
    out(f"box `{args.base}` · " + " · ".join(f"{k} `{v}`" for k, v in modules.items()) + "\n")

    # Retrieval is not scoped per department (the box's /v1/query carries only a
    # question), so every answer below is grounded in whatever the box already
    # holds. Recording that set is what makes these results reproducible.
    _, docs, _ = box.call("GET", "/api/v1/rag/documents")
    held = [d.get("name") for d in docs.get("documents", [])]
    listed = ", ".join(f"`{h}`" for h in held) or "없음"
    out(f"\n시작 시점 색인 문서 {len(held)}건: {listed}\n")

    results = [run_department(box, d, out) for d in depts]

    out("\n## 에이전트 루틴\n")
    routines = [run_routine(box, r, out) for r in ("r1", "r2")]

    passed = sum(1 for r in results for c in r["checks"] if c["ok"])
    total = sum(len(r["checks"]) for r in results)
    drifts = sum(1 for r in results for c in r["checks"] if c.get("drift"))
    out(f"\n---\n\n**{passed}/{total} 확인 통과", )
    out(f", 한국어 이탈 {drifts}건.**\n" if drifts else ".**\n")

    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "scenarios.md").write_text("".join(lines))
    (outdir / "scenarios.json").write_text(json.dumps(
        {"modules": modules, "departments": results, "routines": routines},
        ensure_ascii=False, indent=2) + "\n")
    print(f"\nwrote {outdir}/scenarios.md and scenarios.json")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
