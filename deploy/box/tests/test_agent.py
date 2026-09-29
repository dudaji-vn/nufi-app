"""nufibox-agent's join logic, driven in NUFIBOX_AGENT_DRY_RUN mode (nothing runs).

The agent is the de-branded mesh client a member installs instead of official
Tailscale: one thing, bundled tailscaled, joins with an invite's pre-auth key.
"""
import os
import pathlib
import subprocess

AGENT = pathlib.Path(__file__).resolve().parents[1] / "agent" / "nufibox-agent"


def run(*args, **env):
    e = dict(os.environ, NUFIBOX_AGENT_DRY_RUN="1", **env)
    return subprocess.run(["/bin/bash", str(AGENT), *args], capture_output=True, text=True, env=e)


def test_enroll_builds_the_join_command_from_the_invite():
    r = run("enroll", "--server", "https://coordinator.internal", "--auth-key", "k-abc", "--hostname", "ivy")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "up --login-server=https://coordinator.internal --auth-key=k-abc --hostname=ivy --accept-dns" in out
    # headscale v0.29.3 rejects RequestTags on a pre-auth-key registration — the
    # tag:member tag rides on the key, never a flag here.
    assert "--advertise-tags" not in out


def test_it_is_de_branded_and_never_reaches_tailscale_com():
    r = run("enroll", "--server", "https://c", "--auth-key", "k")
    out = r.stdout
    assert "nufibox-tailscaled" in out                 # the bundled engine, nufibox-named
    assert "--tun=nufibox0" in out                     # its own interface, not tailscale0
    assert "--no-logs-no-support" in out               # never phones home
    assert "/nufibox" in out                           # private state/socket dir
    assert "tailscale.com" not in out                  # no external Tailscale dependency


def test_enroll_without_ca_skips_cert_trust():
    assert "update-ca-certificates" not in run("enroll", "--server", "https://c", "--auth-key", "k").stdout


def test_enroll_with_ca_trusts_it_then_joins():
    out = run("enroll", "--server", "https://c", "--auth-key", "k", "--ca", "/tmp/coord-ca.crt").stdout
    assert "cp /tmp/coord-ca.crt /usr/local/share/ca-certificates/nufibox-mesh.crt" in out
    assert "update-ca-certificates" in out
    # trust happens before the join
    assert out.index("update-ca-certificates") < out.index("up --login-server")


def test_enroll_requires_a_server_and_a_key():
    assert run("enroll", "--auth-key", "k").returncode != 0
    assert run("enroll", "--server", "https://c").returncode != 0
    assert "needs --server" in run("enroll", "--auth-key", "k").stderr


def test_status_and_down_use_the_nufibox_socket():
    assert "--socket=" in run("status").stdout and "nufibox" in run("status").stdout
    assert "down" in run("down").stdout
