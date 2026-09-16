#!/usr/bin/env python3
"""The box's adapter registry keeps every model call on the box's gateway.

apps/agents/nufi/adapters.json does this for the cloud (api.codechi.me);
this is the same invariant for a box, where the gateway is the litellm-proxy
service and nothing else is a model. The registry has replace semantics, so
an adapter absent here is unavailable, not defaulted -- which is why the two
disabled ones are still listed.

Run:  python3 deploy/box/works/test_adapters.py     (exit 0 = PASS)
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
GATEWAY = "http://litellm-proxy:4000"
CLOUD = (HERE / ".." / ".." / ".." / "apps" / "agents" / "nufi" / "adapters.json").resolve()


def load():
    return json.loads((HERE / "adapters.json").read_text())


def test_every_enabled_harness_reaches_only_the_box_gateway():
    for a in load():
        if not a.get("enabled") or a["adapterType"] == "nufi_agent":
            continue
        assert a["allowFqdns"] == ["litellm-proxy"], (a["adapterType"], a.get("allowFqdns"))
        for k, v in a["defaultEnv"].items():
            assert v.startswith(GATEWAY), (a["adapterType"], k, v)
    print("PASS: every enabled harness reaches only litellm-proxy")


def test_the_box_lists_the_same_adapters_as_the_cloud():
    """Same set, same enabled flags: the box offers what the cloud offers, on
    its own gateway. A harness turned on here and not there was never gated."""
    box = {a["adapterType"]: a.get("enabled", False) for a in load()}
    cloud = {a["adapterType"]: a.get("enabled", False) for a in json.loads(CLOUD.read_text())}
    assert set(box) == set(cloud), (sorted(box), sorted(cloud))
    # pi is not in the sandbox image; a harness the image cannot run is not
    # offered, whatever the cloud does.
    assert box.get("pi_local") is False, box.get("pi_local")
    for name in set(box) - {"pi_local"}:
        assert box[name] == cloud[name], (name, box[name], cloud[name])
    print("PASS: the box's adapter set matches the cloud's, pi excepted")


def test_the_probe_commands_name_binaries_the_sandbox_image_has():
    have = {"codex", "claude", "opencode"}
    for a in load():
        if a.get("enabled") and "probeCommand" in a:
            assert a["probeCommand"][0] in have, a["probeCommand"]
    print("PASS: every probe command is a binary the sandbox image installs")


if __name__ == "__main__":
    test_every_enabled_harness_reaches_only_the_box_gateway()
    test_the_box_lists_the_same_adapters_as_the_cloud()
    test_the_probe_commands_name_binaries_the_sandbox_image_has()
