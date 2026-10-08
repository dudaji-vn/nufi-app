"""lib/coordinator.sh pure seams: the one-time API-key parse and the box-key
mint plan. No Docker daemon — the parse is a string function and the mint is
exercised under DRY=1 (plan only).

Run: cd deploy/box && python3 -m pytest tests/test_coordinator_lib.py -q
"""
import os
import pathlib
import subprocess

BOX = pathlib.Path(__file__).resolve().parents[1]
BASH = "/bin/bash"  # macOS ships 3.2 here; lib/coordinator.sh must run under it


def sourced(call, dry="0", argv=(), env=None):
    """Source lib/coordinator.sh with the few things nufi-box provides, then
    run `call`. argv is passed as $1, $2, … so samples never touch the script
    text; `env` sets the box vars coordinator_up reads (NUFI_SELF_HOST_COORD,
    MESH_SERVER_HOST, …, NUFI_HEADSCALE_IMAGE) the way nufi-box sources them
    from .env. Runs under pipefail, exactly as nufi-box sources it."""
    script = (
        "set -o pipefail; HERE=%r; DRY=%s; ENVF=/tmp/none.env; OS=Linux; "
        'die(){ echo "$*" >&2; exit 2; }; '
        ". lib/coordinator.sh; %s"
    ) % (str(BOX), dry, call)
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run([BASH, "-c", script, "bash", *argv],
                          cwd=str(BOX), capture_output=True, text=True, env=e)


def test_the_api_key_is_read_from_a_fresh_bootstrap_output():
    sample = "==> Minting an API key (365d)\n\nMESH_API_KEY=hskey-abc123.def456\nStore this now.\n"
    r = sourced('coordinator_api_key_from_output "$1"', argv=(sample,))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "hskey-abc123.def456"


def test_no_api_key_is_read_from_a_rerun_output():
    # A re-run prints "api key already minted" and no MESH_API_KEY= line; the
    # stored key must be kept, so the parse returns empty (not a crash).
    sample = " ok api key already minted; rotate with --rotate-key\n"
    r = sourced('coordinator_api_key_from_output "$1"', argv=(sample,))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


def test_the_box_key_mint_uses_the_numeric_user_id():
    r = sourced("coordinator_mint_box_key", dry="1")
    assert r.returncode == 0, r.stderr
    assert "users list -o json" in r.stdout
    assert "preauthkeys create --user <id> --tags tag:box" in r.stdout
    # headscale v0.29.3's --user takes the numeric id, never the username.
    assert "--user box" not in r.stdout


def test_coordinator_up_passes_the_lan_headscale_image_when_set():
    # A --registry self-host box hands the mirror's headscale image to the
    # coordinator bootstrap as COORD_HEADSCALE_IMAGE.
    r = sourced("coordinator_up", dry="1", env={
        "NUFI_SELF_HOST_COORD": "1",
        "MESH_SERVER_HOST": "coordinator.internal",
        "MESH_BASE_DOMAIN": "box.internal",
        "NUFI_HEADSCALE_IMAGE": "10.0.0.5:5000/headscale:main",
    })
    assert r.returncode == 0, r.stderr
    assert "COORD_HEADSCALE_IMAGE=10.0.0.5:5000/headscale:main" in r.stdout
    assert "bootstrap.sh" in r.stdout


def test_coordinator_up_omits_the_headscale_override_on_a_plain_self_host_box():
    # No NUFI_HEADSCALE_IMAGE → no override token; the coordinator keeps its
    # own pinned headscale default.
    r = sourced("coordinator_up", dry="1", env={
        "NUFI_SELF_HOST_COORD": "1",
        "MESH_SERVER_HOST": "coordinator.internal",
        "MESH_BASE_DOMAIN": "box.internal",
    })
    assert r.returncode == 0, r.stderr
    assert "COORD_HEADSCALE_IMAGE" not in r.stdout
    assert "TLS_MODE=internal" in r.stdout


def test_coordinator_up_makes_the_copied_ca_world_readable():
    # The installer runs under umask 077 (it writes .env), so the plain `cp` of
    # the coordinator CA lands 0600. The owner-console runs as a DIFFERENT uid
    # and must read that CA to serve /agent/mesh-ca.crt for the macOS agent
    # enrol; a 0600 CA makes that endpoint a silent 404 and breaks self-host
    # onboarding. The plan must chmod the CA (a public cert) world-readable.
    r = sourced("coordinator_up", dry="1", env={
        "NUFI_SELF_HOST_COORD": "1",
        "MESH_SERVER_HOST": "coordinator.internal",
        "MESH_BASE_DOMAIN": "box.internal",
    })
    assert r.returncode == 0, r.stderr
    assert "chmod 644" in r.stdout
    assert "mesh-coordinator-ca.crt" in r.stdout
