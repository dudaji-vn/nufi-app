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
import re
import time
import urllib.error
import urllib.request

HAN = re.compile(r"[一-鿿]")


def run(base, key, flow_id, text, timeout=400):
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/v1/run/{flow_id}",
        data=json.dumps({"input_value": text, "output_type": "chat",
                         "input_type": "chat"}).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-api-key", key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
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
    a = ap.parse_args()

    with open(a.flows) as fh:
        flows = json.load(fh)
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
