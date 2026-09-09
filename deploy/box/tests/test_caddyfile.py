"""The Caddyfile is the box's front door; these are the rules it must keep."""
import pathlib
import re

import pytest

CADDYFILE = (pathlib.Path(__file__).resolve().parents[1] / "Caddyfile").read_text()
# The global options block: everything to the first `}` alone on a line. Not
# `split("}")` — the block itself contains `{$BOX_IP}`.
GLOBAL = re.match(r"\{\n(.*?)\n\}\n", CADDYFILE, re.S).group(1)


def test_plain_http_is_left_alone_for_the_certificate_download():
    # A laptop that does not trust the box CA yet opens http://<box>/ to get it.
    # Caddy's automatic HTTP->HTTPS redirect would send that to https://<box>:3001,
    # which is precisely the certificate the laptop cannot verify.
    assert "auto_https disable_redirects" in GLOBAL


def test_an_address_without_sni_still_gets_a_certificate():
    # https://<BOX_IP>:3080 is the documented fallback when <box>.local does not
    # resolve. A browser sends no SNI for an address, and Docker's NAT hides the
    # LAN IP from Caddy, so the IP has to be named as the default SNI or the
    # handshake is aborted with no certificate at all.
    assert "default_sni {$BOX_IP}" in GLOBAL
    assert "{$BOX_IP}:3080" in CADDYFILE


def test_every_product_port_is_served():
    for port in (3080, 3001, 3002, 7860, 4000):
        assert re.search(rf"^\{{\$BOX_HOST\}}:{port}, ", CADDYFILE, re.M), port
    assert ":80 {" in CADDYFILE


def test_the_certificate_is_downloadable_by_its_public_name():
    assert "handle /nufi-box-ca.crt {" in CADDYFILE
    assert "rewrite * /root.crt" in CADDYFILE


# --- Task 6: the mesh sites --------------------------------------------------

import json
import shutil
import subprocess

BOX = pathlib.Path(__file__).resolve().parents[1]
MESH_HOST = "nufi.box.lab"
MESH_IP = "100.64.0.7"


def render_mesh_caddy(out_path):
    """Call lib/mesh.sh's renderer the way `nufi-box mesh up` does."""
    r = subprocess.run(
        ["/bin/bash", "-c",
         'HERE="$0"; . "$0/lib/mesh.sh"; mesh_render_caddy "$1" "$2" "$3"',
         str(BOX), MESH_HOST, MESH_IP, str(out_path)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    return pathlib.Path(out_path).read_text()


def test_the_caddyfile_imports_the_generated_mesh_sites():
    # A glob, not a bare path: Caddy treats a missing literal import as a fatal
    # config error ("File to import not found") and the whole front door
    # refuses to start, while a glob that matches nothing is only a warning.
    # A box that has never joined a mesh has no caddy/mesh.caddy.
    assert "import caddy/mesh*.caddy" in CADDYFILE


def test_mesh_caddy_serves_the_five_product_ports_on_both_mesh_addresses(tmp_path):
    text = render_mesh_caddy(tmp_path / "mesh.caddy")
    for port in (3080, 3001, 3002, 7860, 4000):
        line = re.search(rf"^{re.escape(MESH_HOST)}:{port}, {re.escape(MESH_IP)}:{port} \{{$",
                         text, re.M)
        assert line, f"no site block for port {port} in:\n{text}"
    # Five blocks and no more. In particular no :80 block: the Caddyfile's own
    # plain-HTTP site already answers on the mesh name (see the test below), so
    # a sixth block here would be a second copy of the landing page that could
    # drift from the first.
    assert len(re.findall(r"^\S.*\{$", text, re.M)) == 5, text
    assert f"{MESH_HOST}:80" not in text, text
    assert "{$BOX_HOST}" not in text and "{$BOX_MESH_HOST}" not in text


def test_the_plain_http_site_answers_for_every_host_including_the_mesh_name():
    """Why caddy/mesh.caddy has no :80 block. The landing page carries the CA
    a member downloads before anything else works, so it must answer on the
    mesh name — and it does, because this site is matched by port alone.
    Adapting the Caddyfile is what proves it: a `host` matcher anywhere in the
    :80 server would silently make the mesh name a 404 for the one page a new
    laptop needs. Needs Docker; the source assertion below always runs."""
    assert re.search(r"^:80 \{$", CADDYFILE, re.M), CADDYFILE
    if not shutil.which("docker") or subprocess.run(
            ["docker", "info"], capture_output=True).returncode != 0:
        pytest.skip("no docker daemon")
    r = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{BOX / 'Caddyfile'}:/etc/caddy/Caddyfile:ro",
         "-e", "BOX_HOST=nufi.local", "-e", "BOX_IP=192.168.1.10",
         "caddy:2.10.0-alpine", "caddy", "adapt",
         "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    servers = json.loads(r.stdout)["apps"]["http"]["servers"]
    on_80 = [s for s in servers.values() if any(l.endswith(":80") for l in s["listen"])]
    assert len(on_80) == 1, [s["listen"] for s in servers.values()]
    for route in on_80[0]["routes"]:
        for match in route.get("match", []):
            assert "host" not in match, match


def test_caddy_accepts_the_caddyfile_with_the_mesh_sites_imported(tmp_path):
    """The real check: Caddy itself adapts Caddyfile + caddy/mesh.caddy. Needs
    Docker; skipped without it (the assertions above still hold)."""
    if not shutil.which("docker") or subprocess.run(
            ["docker", "info"], capture_output=True).returncode != 0:
        pytest.skip("no docker daemon")
    root = tmp_path / "etc-caddy"
    (root / "caddy").mkdir(parents=True)
    shutil.copy(BOX / "Caddyfile", root / "Caddyfile")
    render_mesh_caddy(root / "caddy" / "mesh.caddy")
    r = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{root}:/etc/caddy:ro",
         "-e", "BOX_HOST=nufi.local", "-e", "BOX_IP=192.168.1.10",
         "caddy:2.10.0-alpine", "caddy", "validate",
         "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "Valid configuration" in r.stdout + r.stderr, r.stderr
    # Caddy groups sites by listener, so what proves the mesh ones arrived is
    # that `import caddy/mesh*.caddy` produced no warning about matching
    # nothing.
    assert "No files matching import glob pattern" not in r.stderr, r.stderr
