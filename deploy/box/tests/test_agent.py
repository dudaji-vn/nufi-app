"""nufibox-agent's join logic, driven in NUFIBOX_AGENT_DRY_RUN mode (nothing runs).

The agent is the de-branded mesh client a member installs instead of official
Tailscale: one thing, bundled tailscaled, joins with an invite's pre-auth key.
The wrapper is OS-aware; the OS is pinned per test (NUFIBOX_FAKE_OS) so the same
assertions hold on a Linux CI runner and on a macOS dev machine.
"""
import os
import pathlib
import subprocess

AGENT = pathlib.Path(__file__).resolve().parents[1] / "agent" / "nufibox-agent"


def run(*args, fake_os="Linux", **env):
    e = dict(os.environ, NUFIBOX_AGENT_DRY_RUN="1", NUFIBOX_FAKE_OS=fake_os, **env)
    return subprocess.run(["/bin/bash", str(AGENT), *args], capture_output=True, text=True, env=e)


# --- shared behaviour (asserted on Linux; the join command is OS-independent) ---

def test_enroll_builds_the_join_command_from_the_invite():
    r = run("enroll", "--server", "https://coordinator.internal", "--auth-key", "k-abc", "--hostname", "ivy")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "up --login-server=https://coordinator.internal --auth-key=k-abc --hostname=ivy --accept-dns" in out
    # headscale v0.29.3 rejects RequestTags on a pre-auth-key registration — the
    # tag:member tag rides on the key, never a flag here.
    assert "--advertise-tags" not in out


def test_enroll_requires_a_server_and_a_key():
    assert run("enroll", "--auth-key", "k").returncode != 0
    assert run("enroll", "--server", "https://c").returncode != 0
    assert "needs --server" in run("enroll", "--auth-key", "k").stderr


def test_status_and_down_use_the_nufibox_socket():
    assert "--socket=" in run("status").stdout and "nufibox" in run("status").stdout
    assert "down" in run("down").stdout


# --- Linux: systemd, a named tun, the system CA store ---

def test_linux_is_de_branded_and_never_reaches_tailscale_com():
    out = run("enroll", "--server", "https://c", "--auth-key", "k", fake_os="Linux").stdout
    assert "nufibox-tailscaled" in out                 # the bundled engine, nufibox-named
    assert "--tun=nufibox0" in out                     # its own interface, not tailscale0
    assert "--no-logs-no-support" in out               # never phones home
    assert "/nufibox" in out                           # private state/socket dir
    assert "tailscale.com" not in out                  # no external Tailscale dependency


def test_linux_enroll_without_ca_skips_cert_trust():
    assert "update-ca-certificates" not in run("enroll", "--server", "https://c", "--auth-key", "k").stdout


def test_linux_enroll_with_ca_trusts_it_then_joins():
    out = run("enroll", "--server", "https://c", "--auth-key", "k", "--ca", "/tmp/coord-ca.crt").stdout
    assert "cp /tmp/coord-ca.crt /usr/local/share/ca-certificates/nufibox-mesh.crt" in out
    assert "update-ca-certificates" in out
    # trust happens before the join
    assert out.index("update-ca-certificates") < out.index("up --login-server")


# --- macOS: launchd, utun, the System keychain ---

def test_macos_is_de_branded_with_utun_and_no_phone_home():
    out = run("enroll", "--server", "https://c", "--auth-key", "k", fake_os="Darwin").stdout
    assert "nufibox-tailscaled" in out
    assert "--tun=utun" in out                          # darwin requires utun naming
    assert "--tun=nufibox0" not in out                  # the linux name never leaks onto mac
    assert "--no-logs-no-support" in out
    assert "/Library/NufiBox" in out                    # macOS state/socket dir
    assert "tailscale.com" not in out


def test_macos_enroll_with_ca_trusts_it_in_the_system_keychain_then_joins():
    out = run("enroll", "--server", "https://c", "--auth-key", "k", "--ca", "/tmp/coord-ca.crt", fake_os="Darwin").stdout
    assert "security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain /tmp/coord-ca.crt" in out
    assert "update-ca-certificates" not in out          # that is the linux path, never on mac
    # trust happens before the join
    assert out.index("add-trusted-cert") < out.index("up --login-server")


def test_macos_enroll_without_ca_skips_cert_trust():
    assert "add-trusted-cert" not in run("enroll", "--server", "https://c", "--auth-key", "k", fake_os="Darwin").stdout
