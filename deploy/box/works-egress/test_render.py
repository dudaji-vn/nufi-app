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


def render(allow=None, box_host=None):
    env = {k: v for k, v in os.environ.items() if k not in ("WORKS_EGRESS_ALLOW", "BOX_HOST")}
    if allow is not None:
        env["WORKS_EGRESS_ALLOW"] = allow
    if box_host is not None:
        env["BOX_HOST"] = box_host
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


def test_entries_are_lowercased_because_the_filter_is_not():
    """tinyproxy's fnmatch filter is case-sensitive and DNS is not; an operator
    who types PyPI.org must get pypi.org, and a duplicate in another case is a
    duplicate."""
    r = render("PyPI.org,pypi.org,Files.PythonHosted.org")
    assert lines(r) == ["works", "litellm-proxy", "pypi.org", "files.pythonhosted.org"], lines(r)
    print("PASS: entries are lowercased before they are checked or deduplicated")


def test_two_hosts_without_a_comma_are_refused_not_merged():
    """"pypi.org files.pythonhosted.org" is a forgotten comma. Stripping the
    space would render one host that exists nowhere and allow neither."""
    r = render("pypi.org files.pythonhosted.org")
    assert r.returncode == 2, (r.returncode, r.stdout)
    assert "pypi.org files.pythonhosted.org" in r.stderr, r.stderr
    print("PASS: a forgotten comma is refused, not merged into a host that exists nowhere")


def test_a_newline_inside_an_entry_is_refused_not_split():
    """grep validates one line at a time; an entry that carries a newline would
    pass on its first line and smuggle its second, unvalidated, into the filter."""
    r = render("pypi.org\nevil.com")
    assert r.returncode == 2, (r.returncode, r.stdout)
    assert "newline" in r.stderr, r.stderr
    print("PASS: a newline inside an entry is refused, not split into two lines")


def test_an_entry_that_is_not_a_hostname_is_refused():
    for bad in ("https://pypi.org", "pypi.org/simple", "pypi.org:443", "*.pypi.org", "10.0.0.5", "*", "[a-z]*"):
        r = render(bad)
        assert r.returncode == 2, (bad, r.returncode, r.stdout)
        assert bad in r.stderr, (bad, r.stderr)
    print("PASS: URLs, paths, ports, globs and bare addresses are refused")


def test_the_model_host_cannot_be_allowed_directly():
    """A sandbox reaches the model through the gateway or not at all."""
    for host in ("ollama", "host.docker.internal", "ollama:11434",
                 "gateway.docker.internal", "localhost", "works-egress"):
        r = render(host)
        assert r.returncode == 2, (host, r.stdout)
        assert "gateway" in r.stderr.lower(), r.stderr
    print("PASS: the model host is refused; the gateway is the only route to the model")


def test_the_box_s_own_name_is_a_model_host_only_when_it_is_the_box_s_name():
    """On an ollama-profile box, BOX_HOST serves the model directly on its own
    port -- allowing it would open a second, ungoverned route to the model. A
    hostname the box does not answer to is just a hostname."""
    r = render("NuFi.local", box_host="nufi.local")
    assert r.returncode == 2, (r.returncode, r.stdout)
    assert "gateway" in r.stderr.lower(), r.stderr
    r = render("nufi.local")
    assert r.returncode == 0, (r.returncode, r.stderr)
    print("PASS: the box's own name is refused as the model host only when BOX_HOST says so")


def test_nothing_else_is_in_the_output():
    r = render("example.com")
    for l in lines(r):
        assert l in ("works", "litellm-proxy", "example.com"), l
    print("PASS: the file holds hosts and comments, nothing else")


def test_the_entrypoint_keeps_the_three_directives_that_make_the_boundary():
    """Nothing in CI starts the image. These three lines are what turns a
    forward proxy into an allow list; a typo in any of them ships a proxy
    that matches substrings or denies nothing."""
    text = (HERE / "entrypoint.sh").read_text()
    for line in ("FilterDefaultDeny Yes", "FilterType fnmatch", 'Filter "/etc/tinyproxy/filter"'):
        assert line in text, line
    assert "LogFile" not in text, "tinyproxy 1.11 refuses /dev/stderr and then logs nothing"
    print("PASS: the entrypoint carries the three directives that make the boundary")


if __name__ == "__main__":
    test_the_two_fixed_hosts_are_always_first()
    test_the_operator_list_is_appended_trimmed_and_deduplicated()
    test_entries_are_lowercased_because_the_filter_is_not()
    test_two_hosts_without_a_comma_are_refused_not_merged()
    test_a_newline_inside_an_entry_is_refused_not_split()
    test_an_entry_that_is_not_a_hostname_is_refused()
    test_the_model_host_cannot_be_allowed_directly()
    test_the_box_s_own_name_is_a_model_host_only_when_it_is_the_box_s_name()
    test_nothing_else_is_in_the_output()
    test_the_entrypoint_keeps_the_three_directives_that_make_the_boundary()
