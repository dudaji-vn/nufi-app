#!/usr/bin/env bash
# Reconcile policy.yaml against config.yaml, in both directions.
#
# A control declared in policy.yaml but never referenced from config.yaml is
# never imported by LiteLLM, so it cannot report its own absence: no startup
# assertion, no gauge, no log line. It is silent because it is missing, and a
# green dashboard looks identical either way. In-process instrumentation cannot
# close this by construction, which is why the check lives out here.
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

# The check parses YAML, so it needs PyYAML. The repo venv has it; a bare
# system python3 usually does not (verified: Homebrew python3 on macOS has no
# yaml). Picking the wrong interpreter must be a loud failure with a fix in it,
# never a skip -- a wiring check that quietly does not run is the same silence
# it exists to detect.
PYTHON="${PYTHON:-}"
if [ -z "${PYTHON}" ]; then
  if [ -x .venv/bin/python ]; then
    PYTHON=.venv/bin/python
  else
    PYTHON=python3
  fi
fi

if ! "${PYTHON}" -c 'import yaml' >/dev/null 2>&1; then
  echo "check-guardrails-wired: ${PYTHON} cannot import yaml." >&2
  echo "  Install it (pip install PyYAML), create the venv" >&2
  echo "  (python3 -m venv .venv && .venv/bin/pip install -r litellm/requirements.txt)," >&2
  echo "  or point PYTHON= at an interpreter that has it." >&2
  exit 1
fi

"${PYTHON}" - "litellm/guardrails/policy.yaml" "litellm/config.yaml" <<'PY'
import re
import sys

import yaml

policy_path, config_path = sys.argv[1], sys.argv[2]

with open(policy_path, encoding="utf-8") as handle:
    policy = yaml.safe_load(handle) or {}
with open(config_path, encoding="utf-8") as handle:
    config = yaml.safe_load(handle) or {}

# EVERY declared control, not just the mandatory ones. `mandatory` answers
# "should the proxy refuse to start when this control is DISABLED"; whether a
# control is WIRED is a different axis. Only G1 and G4 are mandatory today, so
# a mandatory-only check would leave G2a, G2b and G3 -- including both PII
# controls -- with no wiring check at all.
declared = sorted((policy.get("controls") or {}))

PREFIX = "guardrails.entrypoints."
# config.yaml points `guardrail:` at a CLASS, because that is what LiteLLM
# instantiates (guardrail_registry.initialize_custom_guardrail). The control id
# is the leading `G<digits><lowercase suffix>` of the class name, which is
# exactly how policy.yaml spells it: G1Injection -> G1, G2aPiiInput -> G2a. The
# suffix stops at the next capital, so a future `G2Something` maps to G2 and
# cannot be confused with G2a.
CONTROL_ID = re.compile(r"^(G\d+[a-z]*)")

# Parse, never grep. A grep for `guardrails.entrypoints.*G1` matches a line
# that starts with `#` -- and a commented-out security control in a live config
# is the precise failure this project exists to end. yaml.safe_load sees a
# commented entry as absent for the same reason the proxy does.
wired = {}
for entry in config.get("guardrails") or []:
    target = ((entry or {}).get("litellm_params") or {}).get("guardrail") or ""
    if not target.startswith(PREFIX):
        continue
    symbol = target[len(PREFIX):]
    match = CONTROL_ID.match(symbol)
    key = match.group(1).lower() if match else symbol.lower()
    wired[key] = entry.get("guardrail_name") or target

problems = []
for control in declared:
    if control.lower() not in wired:
        problems.append(
            f"MISSING: control {control} is declared in {policy_path} "
            f"but no guardrail in {config_path} points at {PREFIX}{control}*"
        )

declared_lower = {c.lower() for c in declared}
for key, name in sorted(wired.items()):
    if key not in declared_lower:
        problems.append(
            f"ORPHAN: {config_path} wires {name} at {PREFIX}{key}* "
            f"but no matching control is declared in {policy_path}"
        )

if problems:
    print("\n".join(problems))
    print()
    print("A control declared in policy.yaml but absent from config.yaml never")
    print("loads, so it cannot warn about its own absence. A guardrail wired in")
    print("config.yaml with no policy entry has no thresholds to decide with.")
    print("Wire it, or delete it from policy.yaml.")
    sys.exit(1)

print(f"all {len(declared)} declared controls are wired: {', '.join(declared)}")
PY
