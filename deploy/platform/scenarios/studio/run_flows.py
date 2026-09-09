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


def run(base, key, flow_id, text, timeout=400):
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/v1/run/{flow_id}",
        data=json.dumps({"input_value": text, "output_type": "chat",
                         "input_type": "chat"}).encode(), method="POST")
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


def text_of(out):
    try:
        return out["outputs"][0]["outputs"][0]["results"]["message"]["text"]
    except Exception:
        return json.dumps(out, ensure_ascii=False)[:200]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:7860")
    ap.add_argument("--key", required=True)
    ap.add_argument("--flows", default="flows.json")
    ap.add_argument("--only", default="", help="run one flow by id instead of all")
    add_transport_args(ap)
    a = ap.parse_args()

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
    bad = 0
    for name, f in flows.items():
        started = time.time()
        code, out = run(a.base, a.key, f["id"], f["ask"])
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
