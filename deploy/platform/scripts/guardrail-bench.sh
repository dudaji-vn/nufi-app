#!/usr/bin/env bash
# Measure guardrail latency against a running stack. Reads the histogram the
# proxy already exports, so it reflects real in-network timing rather than a
# harness's own view of the clock.
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

# NOTE the trailing slash. LiteLLM mounts the metrics ASGI app at `/metrics`
# (integrations/prometheus.py::_mount_metrics_endpoint), and Starlette answers
# the un-slashed form with a 307 and an EMPTY body. A plain
# `curl http://localhost:4000/metrics | grep nufi_guardrail` therefore matches
# nothing on a perfectly healthy stack, and any "no samples found" branch built
# on it reports a guardrail outage that is not happening. monitoring/
# prometheus.yml scrapes `metrics_path: /metrics/` for the same reason.
PROXY_METRICS="${PROXY_METRICS:-http://localhost:4000/metrics/}"
PROXY_URL="${PROXY_URL:-http://localhost:4000}"
ITERATIONS="${ITERATIONS:-50}"
MODEL="${BENCH_MODEL:-}"

# Same fallback as scripts/smoke-test.sh: the key lives in .env, and requiring
# a manual export before every run is friction with no safety value.
if [ -z "${LITELLM_MASTER_KEY:-}" ] && [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . .env
  set +a
fi

if [ -z "${MODEL}" ]; then
  echo "set BENCH_MODEL to a model_name served by the proxy (see /v1/models)" >&2
  exit 1
fi
if [ -z "${LITELLM_MASTER_KEY:-}" ]; then
  echo "set LITELLM_MASTER_KEY (or put it in .env)" >&2
  exit 1
fi

PYTHON="${PYTHON:-}"
if [ -z "${PYTHON}" ]; then
  if [ -x .venv/bin/python ]; then
    PYTHON=.venv/bin/python
  else
    PYTHON=python3
  fi
fi

scrape() {
  # -f so an HTTP error is an error here rather than an empty file that the
  # percentile maths would read as "no traffic".
  curl -fsS "${PROXY_METRICS}"
}

# One request. Echoes the HTTP status so the caller can tell a measured request
# from a rejected one -- `-o /dev/null` on its own hides a 400, and a run where
# every call failed still produces pre_call samples and thus a plausible-looking
# report covering half the pipeline.
chat() {
  local prompt=$1
  curl -s -o /dev/null -w '%{http_code}' -X POST "${PROXY_URL}/v1/chat/completions" \
    -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
    -H 'content-type: application/json' \
    -d "{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"${prompt}\"}]}"
}

before=$(mktemp)
after=$(mktemp)
trap 'rm -f "${before}" "${after}"' EXIT

echo "==> warming up (5 requests, not measured)"
for _ in $(seq 1 5); do
  status=$(chat "hello")
  if [ "${status}" != "200" ]; then
    echo "warm-up request returned HTTP ${status}; fix the model registration before benchmarking" >&2
    exit 1
  fi
done

# Snapshot AFTER the warm-up and diff against the end state. The histogram is
# cumulative since proxy start and already carries whatever traffic the stack
# has seen; printing it raw would mix this run in with every earlier one.
scrape >"${before}"

echo "==> ${ITERATIONS} iterations"
failed=0
for _ in $(seq 1 "${ITERATIONS}"); do
  status=$(chat "summarise the history of Hanoi")
  if [ "${status}" != "200" ]; then
    failed=$((failed + 1))
  fi
done
if [ "${failed}" -ne 0 ]; then
  # Exit non-zero. This block used to warn and fall through, and the Python
  # heredoc below (the last command) set the status, so a run in which EVERY
  # request was rejected still printed a plausible per-control table and
  # exited 0. Measured: 3 requests, all HTTP 400, reported G1 at 102.1 mean /
  # 198.5 p99 -- within noise of the honest 25-request figures.
  #
  # It matters most exactly when the numbers matter most: the warm-up prompt
  # ("hello") differs from the measured one, so a content-dependent rejection
  # -- which is what happens once a control stops being logging_only, the
  # decision these numbers exist to inform -- passes warm-up and fails every
  # measured request.
  echo "${failed}/${ITERATIONS} requests did not return 200." >&2
  echo "post_call controls did not run on those, so any table below would" >&2
  echo "describe a different pipeline than the one you meant to measure." >&2
  exit 1
fi

scrape >"${after}"

echo
"${PYTHON}" - "${before}" "${after}" <<'PY'
"""Diff two /metrics scrapes and report per-control guardrail latency.

Percentiles follow Prometheus `histogram_quantile` semantics: locate the
bucket the rank falls in, then interpolate linearly between its lower and
upper bounds. Resolution is bounded by the bucket edges declared in
litellm/guardrails/audit.py, so a p99 reported as 194.4 means "somewhere in
the 100-200 ms bucket", not 194.4 ms exactly.

Interpolation inside the LOWEST bucket is reported as `<5.0` rather than as a
number. Straight interpolation there assumes the samples are spread evenly
across [0, 5 ms), which for a control that finishes in microseconds yields a
p50 of 2.5 ms -- a figure that looks measured, is off by three orders of
magnitude, and disagrees with the mean printed beside it. The mean comes from
`_sum` and is exact; trust it over any percentile flagged `<`.
"""
import re
import sys

SAMPLE = re.compile(r"^(?P<name>[a-zA-Z_:][\w:]*)(?:\{(?P<labels>[^}]*)\})? (?P<value>.+)$")
LABEL = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')


def parse(path):
    out = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = SAMPLE.match(line)
            if not match:
                continue
            labels = tuple(sorted(LABEL.findall(match.group("labels") or "")))
            try:
                out[(match.group("name"), labels)] = float(match.group("value"))
            except ValueError:
                continue
    return out


def delta(before, after, name):
    """after - before, restricted to `name`. Absent-in-before counts as 0."""
    return {
        key[1]: value - before.get(key, 0.0)
        for key, value in after.items()
        if key[0] == name
    }


def quantile(buckets, total, q):
    """`buckets` is [(le, cumulative_count)] sorted ascending, +Inf last.

    Returns (value_seconds, resolved). When the rank lands in the lowest
    bucket the value is that bucket's upper bound and `resolved` is False --
    see the module docstring.
    """
    rank = q * total
    lower = 0.0
    prev_count = 0.0
    first = True
    for le, count in buckets:
        if count >= rank:
            if le == float("inf"):
                return None, False  # beyond the largest finite bucket
            if first:
                return le, False
            if count == prev_count:
                return le, True
            return lower + (le - lower) * (rank - prev_count) / (count - prev_count), True
        lower = le if le != float("inf") else lower
        prev_count = count
        first = False
    return None, False


def fmt(pair):
    value, resolved = pair
    if value is None:
        return "  >5000"
    if not resolved:
        return f"{'<' + format(value * 1000, '.1f'):>8}"
    return f"{value * 1000:8.1f}"


before_path, after_path = sys.argv[1], sys.argv[2]
before, after = parse(before_path), parse(after_path)

buckets = delta(before, after, "nufi_guardrail_latency_seconds_bucket")
counts = delta(before, after, "nufi_guardrail_latency_seconds_count")
sums = delta(before, after, "nufi_guardrail_latency_seconds_sum")

by_control = {}
for labels, value in buckets.items():
    fields = dict(labels)
    control = fields.get("control")
    le = fields.get("le")
    if control is None or le is None:
        continue
    by_control.setdefault(control, []).append((float(le), value))

if not by_control:
    print("no nufi_guardrail_latency_seconds samples were recorded during this run.")
    print("The controls are registered but never ran. Check that config.yaml wires")
    print("them (npm run check:wired) and that the requests actually reached the proxy.")
    sys.exit(1)

print("==> guardrail latency observed during this run (ms)")
print(f"{'control':<8} {'n':>5} {'mean':>8} {'p50':>8} {'p95':>8} {'p99':>8}")
for control in sorted(by_control):
    series = sorted(by_control[control])
    total = dict(counts).get((("control", control),), 0.0)
    if total <= 0:
        print(f"{control:<8} {0:>5}      --       --       --       --")
        continue
    seconds = sums.get((("control", control),), 0.0)
    print(
        f"{control:<8} {int(total):>5} {seconds / total * 1000:8.1f} "
        f"{fmt(quantile(series, total, 0.50))} "
        f"{fmt(quantile(series, total, 0.95))} "
        f"{fmt(quantile(series, total, 0.99))}"
    )

# A control that is loaded but recorded nothing prints no row at all, which is
# indistinguishable from a control that is not loaded -- the exact ambiguity
# this project exists to remove. `nufi_guardrail_enabled` is published for
# every registered control at startup, so it names the full set.
registered = {
    dict(labels).get("control")
    for (name, labels) in after
    if name == "nufi_guardrail_enabled"
}
silent = sorted(control for control in registered if control and control not in by_control)
if silent:
    print()
    print(f"==> registered but recorded no samples: {', '.join(silent)}")
    print("    Not necessarily broken: a control returns before timing itself when")
    print("    it has nothing to inspect (G3 needs a system message in the request;")
    print("    G2b needs response text). Check `npm run check:wired` before")
    print("    concluding the control is unwired.")

print()
print("==> raw bucket deltas (cumulative, le in seconds)")
for control in sorted(by_control):
    edges = " ".join(
        f"{le if le != float('inf') else '+Inf'}={int(count)}"
        for le, count in sorted(by_control[control])
    )
    print(f"{control:<8} {edges}")

decisions = delta(before, after, "nufi_guardrail_decisions_total")
print()
print("==> decisions recorded during this run")
recorded = {labels: value for labels, value in decisions.items() if value}
if not recorded:
    print("(none -- the benchmark prompt tripped no control)")
for labels, value in sorted(recorded.items()):
    fields = dict(labels)
    print(
        f"  {fields.get('control', '?'):<5} risk={fields.get('risk', '?'):<7} "
        f"action={fields.get('action', '?'):<7} "
        f"enforced={fields.get('enforced', '?'):<5} {int(value)}"
    )
PY
