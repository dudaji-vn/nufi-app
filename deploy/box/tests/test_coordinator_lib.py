"""lib/coordinator.sh pure seams: the one-time API-key parse and the box-key
mint plan. No Docker daemon — the parse is a string function and the mint is
exercised under DRY=1 (plan only).

Run: cd deploy/box && python3 -m pytest tests/test_coordinator_lib.py -q
"""
import pathlib
import subprocess

BOX = pathlib.Path(__file__).resolve().parents[1]
BASH = "/bin/bash"  # macOS ships 3.2 here; lib/coordinator.sh must run under it


def sourced(call, dry="0", argv=()):
    """Source lib/coordinator.sh with the few things nufi-box provides, then
    run `call`. argv is passed as $1, $2, … so samples never touch the script
    text. Runs under pipefail, exactly as nufi-box sources it."""
    script = (
        "set -o pipefail; HERE=%r; DRY=%s; ENVF=/tmp/none.env; OS=Linux; "
        'die(){ echo "$*" >&2; exit 2; }; '
        ". lib/coordinator.sh; %s"
    ) % (str(BOX), dry, call)
    return subprocess.run([BASH, "-c", script, "bash", *argv],
                          cwd=str(BOX), capture_output=True, text=True)


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
