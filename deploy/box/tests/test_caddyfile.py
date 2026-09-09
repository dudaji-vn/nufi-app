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
import os
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


# --- Task 9b / defect D3: the generated file, across an upgrade --------------
#
# caddy/mesh.caddy is generated and gitignored, so a box that joined a mesh on
# older code keeps its old render forever. Task 6 rendered `import landing` and
# its fix round then deleted the `(landing)` snippet from the Caddyfile — the
# deletion was right, the leftover render was not, and the P2 acceptance found
# the box crash-looping Caddy with all six ports down. These pin the upgrade
# path itself: a stale generated file already on disk when the box starts.

# The shape Task 6 actually left on the VM box (a0090190e), abridged to the
# part that matters: a block that imports a snippet the Caddyfile no longer has.
STALE_RENDER = """# caddy/mesh.caddy — GENERATED by `nufi-box mesh up`; do not edit.
# The box's sites on the mesh: {host} and {ip}.
# `nufi-box mesh down` replaces this with caddy/mesh.caddy.empty.

{host}:80, {ip}:80 {{
\timport landing
}}

{host}:3080, {ip}:3080 {{
\timport box_tls
\treverse_proxy librechat:3080
}}
""".format(host=MESH_HOST, ip=MESH_IP)


def a_box_dir(tmp_path, mesh_caddy=None):
    """A copy of the box's Caddy inputs: Caddyfile, caddy/, and a generated file."""
    root = tmp_path / "box"
    (root / "caddy").mkdir(parents=True)
    shutil.copy(BOX / "Caddyfile", root / "Caddyfile")
    shutil.copy(BOX / "caddy" / "mesh.caddy.empty", root / "caddy" / "mesh.caddy.empty")
    shutil.copytree(BOX / "caddy" / "landing", root / "caddy" / "landing")
    if mesh_caddy is not None:
        (root / "caddy" / "mesh.caddy").write_text(mesh_caddy)
    return root


def mesh_sh(snippet, *args, **env):
    """Run one lib/mesh.sh function the way nufi-box does, and hand back the run.

    BOX_MESH_HOST / BOX_MESH_IP come from .env on a real box; here they come
    from the caller, so a box that has joined a mesh and one that has not are
    both expressible.
    """
    e = dict(os.environ)
    e.update({"BOX_MESH_HOST": "", "BOX_MESH_IP": ""})
    e.update(env)
    return subprocess.run(
        ["/bin/bash", "-c",
         'DRY=0; . "$0/lib/mesh.sh"; ' + snippet,
         str(BOX), *[str(a) for a in args]],
        capture_output=True, text=True, env=e)


def is_stale(path, caddyfile=None):
    r = mesh_sh('mesh_caddy_stale "$1" "$2"', path, caddyfile or (BOX / "Caddyfile"))
    return r.returncode == 0


def caddy_validate(root):
    return subprocess.run(
        ["docker", "run", "--rm", "-v", f"{root}:/etc/caddy:ro",
         "-e", "BOX_HOST=nufi.local", "-e", "BOX_IP=192.168.1.10",
         "caddy:2.10.0-alpine", "caddy", "validate",
         "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"],
        capture_output=True, text=True)


def test_a_generated_file_from_an_older_box_is_recognised_as_stale(tmp_path):
    root = a_box_dir(tmp_path, STALE_RENDER)
    assert is_stale(root / "caddy" / "mesh.caddy")


def test_this_boxs_own_render_and_the_empty_template_are_not_stale(tmp_path):
    root = a_box_dir(tmp_path)
    render_mesh_caddy(root / "caddy" / "mesh.caddy")
    assert not is_stale(root / "caddy" / "mesh.caddy")
    assert not is_stale(BOX / "caddy" / "mesh.caddy.empty")
    # Nothing generated yet is not stale — the installer seeds the template.
    assert not is_stale(tmp_path / "nothing-here")


def test_a_current_stamp_does_not_excuse_an_import_that_no_longer_exists(tmp_path):
    """The stamp catches drift somebody remembered to bump; this catches the
    kind that actually happened, where nobody did."""
    root = a_box_dir(tmp_path)
    text = render_mesh_caddy(root / "caddy" / "mesh.caddy")
    assert "# nufi-box mesh.caddy rev " in text.splitlines()[0]
    (root / "caddy" / "mesh.caddy").write_text(text.replace("import box_tls", "import landing", 1))
    assert is_stale(root / "caddy" / "mesh.caddy")


def test_a_box_that_still_knows_its_mesh_address_gets_the_sites_back(tmp_path):
    root = a_box_dir(tmp_path, STALE_RENDER)
    r = mesh_sh('mesh_caddy_refresh "$1"', root,
                BOX_MESH_HOST=MESH_HOST, BOX_MESH_IP=MESH_IP)
    assert r.returncode == 0, r.stderr
    text = (root / "caddy" / "mesh.caddy").read_text()
    assert "import landing" not in text
    assert f"{MESH_HOST}:7860, {MESH_IP}:7860 {{" in text
    assert "written by an older box" in r.stdout


def test_a_box_with_no_mesh_address_is_emptied_rather_than_left_broken(tmp_path):
    """Better one box off the mesh than one box with no front door at all."""
    root = a_box_dir(tmp_path, STALE_RENDER)
    r = mesh_sh('mesh_caddy_refresh "$1"', root)
    assert r.returncode == 0, r.stderr
    assert (root / "caddy" / "mesh.caddy").read_text() == \
        (BOX / "caddy" / "mesh.caddy.empty").read_text()
    assert "nufi-box mesh up" in r.stdout


def test_caddy_refuses_the_stale_file_and_accepts_the_refreshed_one(tmp_path):
    """The defect and its fix, judged by Caddy rather than by a string match:
    the front door the acceptance found crash-looping, then the same box after
    the refresh the installer now runs before `compose up`. Needs Docker."""
    if not shutil.which("docker") or subprocess.run(
            ["docker", "info"], capture_output=True).returncode != 0:
        pytest.skip("no docker daemon")
    root = a_box_dir(tmp_path, STALE_RENDER)
    before = caddy_validate(root)
    assert before.returncode != 0, before.stdout
    assert "landing" in before.stderr + before.stdout

    r = mesh_sh('mesh_caddy_refresh "$1"', root,
                BOX_MESH_HOST=MESH_HOST, BOX_MESH_IP=MESH_IP)
    assert r.returncode == 0, r.stderr
    after = caddy_validate(root)
    assert after.returncode == 0, after.stderr
    assert "Valid configuration" in after.stdout + after.stderr


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
