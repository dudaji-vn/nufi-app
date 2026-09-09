#!/usr/bin/env python3
"""Run every department flow and print what came back.

Used to check the scenarios before they are filmed, and to fail loudly rather
than let a broken flow reach a report. Han characters in a Korean answer are
flagged: the on-box model sometimes finishes a Korean sentence in Chinese, and
that is a defect worth seeing, not smoothing over.
"""
import argparse
import gzip
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from run_box import add_transport_args, transport_from_args  # noqa: E402

HAN = re.compile(r"[一-鿿]")
OPEN = urllib.request.urlopen  # replaced by main() when the box needs a CA


def tweaks_for(flow, department):
    """Point a recipe at another department for this run.

    The drive path is a field on a node, so switching department is a tweak
    rather than a second flow -- but the vector collection has to move with it,
    or hr's question is answered out of legal's index.
    """
    drive = flow.get("drive")
    if not department or not drive:
        return {}
    if drive.get("fixed"):
        # The HR helpdesk answers from the HR policy or it is a different
        # routine; say so rather than quietly answering out of another drive.
        print(f"    (fixed to {drive['path']}; --department ignored)")
        return {}
    root = drive.get("root", "/drives").rstrip("/")
    out = {drive["node"]: {"path": f"{root}/{department}"}}
    if drive.get("index_node"):
        out[drive["index_node"]] = {"collection_name": f"nufi-{department}"}
    return out


def run(base, key, flow_id, text, timeout=400, tweaks=None):
    body = {"input_value": text, "output_type": "chat", "input_type": "chat"}
    if tweaks:
        body["tweaks"] = tweaks
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/v1/run/{flow_id}",
        data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-api-key", key)
    try:
        with OPEN(req, timeout=timeout) as r:
            body = r.read()
            if body[:2] == b"\x1f\x8b":
                body = gzip.decompress(body)
            return 200, json.loads(body)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")[:300]
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Giving up here does NOT stop the run on the box, and the difference
        # matters: Studio applies no per-run deadline and the Ollama component
        # the recipes use exposes no output cap, so a routine that is still
        # generating goes on generating with nobody listening — holding the
        # model against every other question until something unloads it. The
        # P2 acceptance watched `weekly` climb past 39,000 tokens after its
        # client had been killed. Say that in words rather than let a socket
        # timeout arrive as a traceback.
        return 0, (f"no answer in {timeout}s ({exc}). The box is probably still "
                   "generating for this run: check `nufi-box logs ollama`, and "
                   "`ollama stop <model>` is what ends it.")


def text_of(out):
    try:
        return out["outputs"][0]["outputs"][0]["results"]["message"]["text"]
    except Exception:
        return json.dumps(out, ensure_ascii=False)[:200]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:7860")
    ap.add_argument("--key", default="", help="Studio API key; defaults to $STUDIO_API_KEY")
    ap.add_argument("--flows", default="flows.json")
    ap.add_argument("--only", default="", help="run one flow by id instead of all")
    ap.add_argument("--input", default="", help="ask this instead of the recorded question")
    ap.add_argument("--department", default="",
                    help="point a recipe's drive at this department for this run")
    add_transport_args(ap)
    a = ap.parse_args()

    a.key = a.key or os.environ.get("STUDIO_API_KEY", "")
    if not a.key:
        raise SystemExit("no Studio API key: pass --key or set $STUDIO_API_KEY")

    ctx, opener = transport_from_args(a)
    global OPEN
    OPEN = ((lambda req, timeout=400: opener.open(req, timeout=timeout)) if opener else
            (lambda req, timeout=400: urllib.request.urlopen(req, timeout=timeout, context=ctx)))

    with open(a.flows) as fh:
        flows = json.load(fh)
    if a.only:
        flows = {k: v for k, v in flows.items() if k == a.only}
        if not flows:
            raise SystemExit(f"no such flow: {a.only}")
    if a.input and len(flows) > 1:
        raise SystemExit("--input asks one question; name the flow with --only")
    bad = 0
    for name, f in flows.items():
        started = time.time()
        code, out = run(a.base, a.key, f["id"], a.input or f["ask"],
                        tweaks=tweaks_for(f, a.department))
        if code == 0:
            print(f"{name:9} TIMEOUT {time.time() - started:4.0f}s")
            print(f"    {out}")
            bad += 1
            continue
        if code != 200:
            print(f"{name:9} FAIL HTTP {code}  {out}")
            bad += 1
            continue
        answer = text_of(out)
        drift = bool(HAN.search(answer))
        bad += drift
        print(f"{name:9} {'DRIFT' if drift else 'ok   '} {time.time() - started:4.0f}s")
        for line in answer.strip().splitlines()[:6]:
            print(f"    {line[:110]}")
    print(f"\n{len(flows) - bad}/{len(flows)} clean")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
