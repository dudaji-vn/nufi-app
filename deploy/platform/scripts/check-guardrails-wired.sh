#!/usr/bin/env bash
# Reconcile policy.yaml, config.yaml and entrypoints.py against each other.
#
# The failure this exists for: a control that is declared but does not actually
# inspect anything, while every in-process signal says it is fine. LiteLLM only
# imports what config.yaml names, so an unwired control publishes no gauge, logs
# no status and trips no startup assertion — it is silent because it is absent,
# and a green dashboard looks identical either way. Detection cannot come from
# inside the process, which is why this lives out here.
#
# `default_on: false`, a mismatched `mode:` and a typo'd class name all leave a
# control looking healthy from the outside too, so each gets its own check
# below rather than being left to "someone will notice".
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

"${PYTHON}" - \
  "litellm/guardrails/policy.yaml" \
  "litellm/config.yaml" \
  "litellm/guardrails/entrypoints.py" <<'PY'
import ast
import sys

import yaml

policy_path, config_path, entrypoints_path = sys.argv[1], sys.argv[2], sys.argv[3]

with open(policy_path, encoding="utf-8") as handle:
    policy = yaml.safe_load(handle) or {}
# Parse, never grep. A grep for `guardrails.entrypoints.*G1` matches a line that
# starts with `#` -- and a commented-out security control in a live config is
# the precise failure this project exists to end. yaml.safe_load sees a
# commented entry as absent for the same reason the proxy does.
with open(config_path, encoding="utf-8") as handle:
    config = yaml.safe_load(handle) or {}

# EVERY declared control, not just the mandatory ones. `mandatory` answers
# "should the proxy refuse to start when this control is DISABLED"; whether a
# control actually runs is a different axis. Only G1 and G4 are mandatory
# today, so a mandatory-only check would leave G2a, G2b and G3 -- including
# both PII controls -- unchecked.
declared = sorted((policy.get("controls") or {}))

# --- what the code actually implements ---------------------------------------
# Read out of entrypoints.py with `ast`, not imported: the check must run in CI
# and in lint.sh without litellm installed, and parsing yields the same two
# facts an import would -- which classes exist, and which hook each implements.
#
# LiteLLM picks the method to call from the `mode:` in config.yaml, and a class
# only does its work in the hook it implements. Both directions of a mismatch
# are silent:
#   * a class implementing only `async_pre_call_hook`, wired `post_call`, gets
#     `CustomLogger.async_post_call_success_hook` -- the inherited no-op. It
#     never runs at all.
#   * a class implementing only `apply_guardrail`, wired `pre_call`, is routed
#     through litellm's `unified_guardrail` bridge and invoked with
#     input_type="request"; a control written for responses returns its input
#     unchanged, so it inspects nothing.
# Verified against the installed litellm==1.83.10
# (proxy/utils.py::_execute_guardrail_hook, which swaps in the unified bridge
# for any class defining `apply_guardrail`, and unified_guardrail.py).
HOOK_MODE = {
    "async_pre_call_hook": "pre_call",
    "async_moderation_hook": "during_call",
    "apply_guardrail": "post_call",
    "async_post_call_success_hook": "post_call",
}

ENTRYPOINTS_MODULE = "guardrails.entrypoints"

with open(entrypoints_path, encoding="utf-8") as handle:
    tree = ast.parse(handle.read(), filename=entrypoints_path)

classes = {}
for node in tree.body:
    if not isinstance(node, ast.ClassDef):
        continue
    control_id = ""
    for stmt in node.body:
        targets = []
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
        elif isinstance(stmt, ast.AnnAssign):
            targets = [stmt.target]
        if any(getattr(target, "id", None) == "control_id" for target in targets):
            value = getattr(stmt, "value", None)
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                control_id = value.value
    methods = {
        stmt.name
        for stmt in node.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    classes[node.name] = {
        "control_id": control_id,
        "modes": {HOOK_MODE[name] for name in methods if name in HOOK_MODE},
    }

problems = []
wired = {}

for raw_entry in config.get("guardrails") or []:
    entry = raw_entry or {}
    params = entry.get("litellm_params") or {}
    target = params.get("guardrail") or ""
    if not target.startswith("guardrails."):
        # A LiteLLM built-in (presidio, lakera, ...). Not ours to reconcile.
        continue
    name = entry.get("guardrail_name") or target
    module, _, symbol = target.rpartition(".")

    if module != ENTRYPOINTS_MODULE:
        problems.append(
            f"UNVERIFIABLE: {name} points at {target}, but this check only knows "
            f"{ENTRYPOINTS_MODULE}. Move the control there, or teach this script "
            f"about the new module -- an unreconciled control is an unwatched one."
        )
        continue

    info = classes.get(symbol)
    if info is None:
        available = ", ".join(
            sorted(n for n, i in classes.items() if i["control_id"])
        )
        problems.append(
            f"UNKNOWN TARGET: {name} points at {target}, which is not a class "
            f"defined in {entrypoints_path}. LiteLLM instantiates this path, so a "
            f"typo -- or a module-level instance where the class was meant -- "
            f"stops the proxy from booting. Classes available: {available}"
        )
        continue

    control = info["control_id"]
    if not control:
        problems.append(
            f"NOT A CONTROL: {name} points at {target}, a class with no "
            f"`control_id`, so it has no policy entry to take thresholds from."
        )
        continue

    wired[control] = name

    if control not in (policy.get("controls") or {}):
        problems.append(
            f"ORPHAN: {config_path} wires {name} at {target} (control {control}), "
            f"but {policy_path} declares no control {control}, so it has no "
            f"thresholds to decide with."
        )

    mode = params.get("mode")
    if not info["modes"]:
        problems.append(
            f"NO HOOK: {symbol} implements none of {sorted(HOOK_MODE)}, so LiteLLM "
            f"has no method to call for {name} on any request."
        )
    elif mode not in info["modes"]:
        expected = " or ".join(sorted(info["modes"]))
        problems.append(
            f"WRONG HOOK: {name} is wired `mode: {mode}` but {symbol} implements "
            f"the {expected} hook. LiteLLM calls the method matching `mode`, so "
            f"the control registers, gauges and logs exactly like a healthy one "
            f"and inspects nothing. Expected `mode: {expected}`."
        )

    # `default_on` decides whether the control runs on requests that do not name
    # it. `false` is the quietest way to disable a control that exists: LiteLLM
    # still imports the module, constructs the guardrail, publishes every gauge
    # and logs the startup status -- the exposition is byte-identical to a
    # healthy control -- but `should_run_guardrail` returns False for every
    # request that does not list the guardrail explicitly, so it inspects
    # nothing. The `presidio-mask-pii` entry this block replaced sat in exactly
    # that state, under a "flip back to true later" comment.
    if params.get("default_on") is not True:
        problems.append(
            f"NEVER RUNS: {name} sets `default_on: {params.get('default_on')!r}`. "
            f"The control still loads, gauges and logs like a healthy one, but "
            f"LiteLLM skips it on every request that does not name it explicitly. "
            f"Set `default_on: true`, or remove control {control} from "
            f"{policy_path} if you do not want it."
        )

for control in declared:
    if control not in wired:
        problems.append(
            f"MISSING: control {control} is declared in {policy_path} but no "
            f"guardrail in {config_path} points at a {ENTRYPOINTS_MODULE} class "
            f"whose control_id is {control}."
        )

if problems:
    print("\n".join(problems))
    print()
    print("A control declared in policy.yaml but absent from config.yaml never")
    print("loads, so it cannot warn about its own absence. One that loads but")
    print("cannot run -- default_on: false, or the wrong hook -- is worse: it")
    print("reports itself present. Wire it properly, or delete it from")
    print("policy.yaml.")
    sys.exit(1)

print(
    f"all {len(declared)} declared controls are wired and able to run: "
    f"{', '.join(declared)}"
)
PY
