#!/usr/bin/env python3
"""The egress allow list, rendered. Stdlib only; no Docker.

The proxy is the only way out of the sandbox network, so what this script
writes is the whole of what an agent may reach. Two hosts are always there and
cannot be removed -- the Works server the sandbox reports to, and the gateway
the model is reached through -- and the model host itself can never be added,
because a sandbox that reaches Ollama directly is a sandbox outside the
gateway's limits and guardrails.

Run:  python3 deploy/box/works-egress/test_render.py     (exit 0 = PASS)
"""
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
RENDER = HERE / "render.sh"


def render(allow=None):
    env = {k: v for k, v in os.environ.items() if k != "WORKS_EGRESS_ALLOW"}
    if allow is not None:
        env["WORKS_EGRESS_ALLOW"] = allow
    return subprocess.run(["/bin/sh", str(RENDER)], env=env, capture_output=True, text=True)


def lines(r):
    return [l for l in r.stdout.splitlines() if l and not l.startswith("#")]


def test_the_two_fixed_hosts_are_always_first():
    for allow in (None, "", "pypi.org"):
        r = render(allow)
        assert r.returncode == 0, r.stderr
        assert lines(r)[:2] == ["works", "litellm-proxy"], (allow, lines(r))
    print("PASS: works and litellm-proxy are always allowed, and first")


def test_the_operator_list_is_appended_trimmed_and_deduplicated():
    r = render(" pypi.org, files.pythonhosted.org ,pypi.org,")
    assert lines(r) == ["works", "litellm-proxy", "pypi.org", "files.pythonhosted.org"], lines(r)
    print("PASS: the operator list is appended, trimmed, deduplicated")


def test_an_entry_that_is_not_a_hostname_is_refused():
    for bad in ("https://pypi.org", "pypi.org/simple", "pypi.org:443", "*.pypi.org", "10.0.0.5"):
        r = render(bad)
        assert r.returncode == 2, (bad, r.returncode, r.stdout)
        assert bad in r.stderr, (bad, r.stderr)
    print("PASS: URLs, paths, ports, globs and bare addresses are refused")


def test_the_model_host_cannot_be_allowed_directly():
    """A sandbox reaches the model through the gateway or not at all."""
    for host in ("ollama", "host.docker.internal", "ollama:11434"):
        r = render(host)
        assert r.returncode == 2, (host, r.stdout)
        assert "gateway" in r.stderr.lower(), r.stderr
    print("PASS: the model host is refused; the gateway is the only route to the model")


def test_nothing_else_is_in_the_output():
    r = render("example.com")
    for l in lines(r):
        assert l in ("works", "litellm-proxy", "example.com"), l
    print("PASS: the file holds hosts and comments, nothing else")


if __name__ == "__main__":
    test_the_two_fixed_hosts_are_always_first()
    test_the_operator_list_is_appended_trimmed_and_deduplicated()
    test_an_entry_that_is_not_a_hostname_is_refused()
    test_the_model_host_cannot_be_allowed_directly()
    test_nothing_else_is_in_the_output()
