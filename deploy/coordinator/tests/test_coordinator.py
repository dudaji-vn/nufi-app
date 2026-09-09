"""Renders deploy/coordinator's compose files and bootstrap.sh --dry-run and
asserts the shape headscale v0.29.3 + Caddy need.

No Docker daemon needed for most of this file: `docker compose config` only
needs the CLI. The one exception, test_headscale_configtest_accepts_the_
rendered_config, actually runs the pinned headscale image; it skips with a
clear message when Docker is unavailable.

Run: cd deploy/coordinator && python3 -m pytest tests -q
"""

import json
import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

COORD = pathlib.Path(__file__).resolve().parents[1]
BASH = "/bin/bash"  # macOS ships 3.2 here; bootstrap.sh must run under it

LAB_ENV = {
    "MESH_SERVER_HOST": "coordinator.lab",
    "MESH_BASE_DOMAIN": "box.lab",
    "TLS_MODE": "internal",
    "ACME_EMAIL": "",
}


def render(*files, env_overrides=None):
    env = dict(os.environ)
    env.update(LAB_ENV)
    if env_overrides:
        env.update(env_overrides)
    cmd = ["docker", "compose", "--project-directory", str(COORD)]
    for f in files or ("docker-compose.yml",):
        cmd += ["-f", str(COORD / f)]
    cmd += ["config", "--format", "json"]
    out = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


# ---------------------------------------------------------------------------
# docker-compose.yml
# ---------------------------------------------------------------------------


def test_services_present_and_named():
    cfg = render()
    assert cfg["name"] == "nufi-coordinator"
    assert set(cfg["services"]) == {"headscale", "caddy"}


def test_images_are_pinned():
    cfg = render()
    assert cfg["services"]["headscale"]["image"] == "ghcr.io/juanfont/headscale:v0.29.3"
    assert cfg["services"]["caddy"]["image"] == "caddy:2.10.0-alpine"
    for svc in cfg["services"].values():
        assert not svc["image"].endswith(":latest")


def test_every_service_follows_the_house_rules():
    cfg = render()
    for name, svc in cfg["services"].items():
        assert svc.get("restart") == "unless-stopped", name
        assert "healthcheck" in svc, name
        assert list(svc.get("networks", {}).keys()) == ["coord"], name


def test_ports_published_by_the_right_service():
    cfg = render()

    def published(name):
        out = {}
        for p in cfg["services"][name].get("ports", []) or []:
            out.setdefault(int(p["target"]), set()).add(p["protocol"])
        return out

    caddy_ports = published("caddy")
    assert 443 in caddy_ports and "tcp" in caddy_ports[443]
    assert 80 in caddy_ports

    headscale_ports = published("headscale")
    assert 3478 in headscale_ports and "udp" in headscale_ports[3478]
    # headscale's own HTTPS/API port must never be published directly —
    # only Caddy terminates TLS.
    assert 8080 not in headscale_ports


def test_headscale_healthcheck_is_the_exec_form_health_subcommand():
    # The image has no shell (a "ko"-built binary, confirmed via `docker image
    # inspect` — Entrypoint is /ko-app/headscale, no /bin/sh), so a
    # wget/curl-based probe cannot run here; `headscale health` is the
    # binary's own healthcheck subcommand, confirmed present with
    # `docker run --rm ghcr.io/juanfont/headscale:v0.29.3 --help`.
    cfg = render()
    assert cfg["services"]["headscale"]["healthcheck"]["test"] == ["CMD", "headscale", "health"]


def test_lab_ports_override_replaces_not_appends():
    # `ports:` merges by concatenation across compose files by default —
    # verified empirically with a throwaway compose file — so the override
    # must use the compose-spec `!override` merge tag or the lab would try
    # to bind 80/443 (already held by deploy/box's own Caddy) as well as the
    # lab ports.
    cfg = render("docker-compose.yml", "docker-compose.lab-ports.yml")
    caddy_ports = {(int(p["target"]), int(p["published"])) for p in cfg["services"]["caddy"]["ports"]}
    assert caddy_ports == {(80, 8080), (443, 8443)}
    hs_ports = {(int(p["target"]), int(p["published"]), p["protocol"]) for p in cfg["services"]["headscale"]["ports"]}
    assert hs_ports == {(3478, 13478, "udp")}


def test_env_example_declares_every_variable_bootstrap_needs():
    lines = (COORD / ".env.example").read_text().splitlines()
    declared = {line.split("=", 1)[0]: line for line in lines if "=" in line and not line.startswith("#")}
    for var in ("MESH_SERVER_HOST", "MESH_BASE_DOMAIN", "TLS_MODE", "ACME_EMAIL"):
        assert var in declared, var
    # every placeholder except the one meant to be replaced is a real default
    assert "replace-me" not in declared["MESH_SERVER_HOST"]
    assert "replace-me" not in declared["MESH_BASE_DOMAIN"]
    assert "replace-me" in declared["ACME_EMAIL"]


# ---------------------------------------------------------------------------
# bootstrap.sh --dry-run
# ---------------------------------------------------------------------------


def bootstrap(*args, **env):
    # COORDINATOR_ENV points at a path that does not exist unless the caller
    # says otherwise: on a machine where the coordinator is actually running,
    # deploy/coordinator/.env is right there, and bootstrap.sh would reuse its
    # answers — the plan under test would be that coordinator's, not the one
    # the test described (mirrors deploy/box/tests/test_install.py).
    with tempfile.TemporaryDirectory() as tmp:
        e = dict(os.environ, **LAB_ENV)
        e.setdefault("COORDINATOR_ENV", str(pathlib.Path(tmp) / "absent.env"))
        e.update(env)
        return subprocess.run(
            [BASH, str(COORD / "bootstrap.sh"), *args],
            cwd=COORD,
            env=e,
            capture_output=True,
            text=True,
        )


def test_dry_run_does_not_touch_docker():
    r = bootstrap("--dry-run")
    assert r.returncode == 0, r.stderr
    assert "docker compose up" not in r.stdout  # only the plan, `run()`-style, is printed as `$ ...`
    assert not (COORD / "config" / "headscale.yaml").exists()
    assert not (COORD / "Caddyfile.rendered").exists()


def test_dry_run_prints_rendered_headscale_yaml():
    out = bootstrap("--dry-run").stdout
    assert "server_url: https://coordinator.lab" in out
    assert "base_domain: box.lab" in out
    assert "path: /etc/headscale/policy.hujson" in out
    assert 'stun_listen_addr: "0.0.0.0:3478"' in out
    assert "magic_dns: true" in out
    # derp.server.enabled: true, indented under `server:` — not derp.urls
    assert "    enabled: true" in out
    assert "urls: []" in out


def test_dry_run_prints_rendered_caddyfile_internal_mode():
    out = bootstrap("--dry-run", TLS_MODE="internal").stdout
    assert "tls internal" in out
    assert "skip_install_trust" in out
    assert "email {$ACME_EMAIL}" not in out


def test_dry_run_prints_rendered_caddyfile_acme_mode():
    out = bootstrap("--dry-run", TLS_MODE="acme", ACME_EMAIL="ops@nufi.me").stdout
    assert "email {$ACME_EMAIL}" in out
    assert "tls internal" not in out


def test_dry_run_refuses_when_base_domain_is_a_suffix_of_the_server_host():
    r = bootstrap("--dry-run", MESH_SERVER_HOST="mesh.box.lab", MESH_BASE_DOMAIN="box.lab")
    assert r.returncode != 0
    assert "base_domain" in (r.stdout + r.stderr).lower()


def test_dry_run_requires_the_two_env_vars():
    with tempfile.TemporaryDirectory() as tmp:
        e = dict(os.environ, COORDINATOR_ENV=str(pathlib.Path(tmp) / "absent.env"))
        e.pop("MESH_SERVER_HOST", None)
        e.pop("MESH_BASE_DOMAIN", None)
        r = subprocess.run([BASH, str(COORD / "bootstrap.sh"), "--dry-run"], cwd=COORD, env=e,
                            capture_output=True, text=True)
    assert r.returncode != 0
    assert "MESH_SERVER_HOST" in r.stderr or "MESH_SERVER_HOST" in r.stdout


def test_bootstrap_handles_headscales_null_json_for_an_empty_list():
    # `headscale users list -o json` / `apikeys list -o json` print the bare
    # JSON literal `null`, not `[]`, when there is nothing yet (confirmed
    # live against v0.29.3 on a fresh database) -- `json.load(...) or []`
    # in bootstrap.sh must be present, not a bare `json.load(...)` that
    # would crash iterating None.
    text = (COORD / "bootstrap.sh").read_text()
    assert "json.load(sys.stdin) or []" in text


def test_help_mentions_rotate_key():
    r = bootstrap("--help")
    assert r.returncode == 0
    assert "--rotate-key" in r.stdout


# ---------------------------------------------------------------------------
# The Caddyfile template itself (static text assertions, no rendering)
# ---------------------------------------------------------------------------


def test_caddyfile_template_has_both_placeholders():
    text = (COORD / "Caddyfile").read_text()
    assert "@GLOBAL_TLS_OPT@" in text
    assert "@SITE_TLS@" in text
    assert "{$MESH_SERVER_HOST}" in text
    assert "reverse_proxy headscale:8080" in text
    assert ":80 {" in text and "/healthz" in text


# ---------------------------------------------------------------------------
# The policy file
# ---------------------------------------------------------------------------


def test_readme_health_check_uses_the_certificates_name_not_localhost():
    # curl -sk https://localhost:8443/health fails the TLS/SNI match --
    # confirmed live (curl exit 35): Caddy's site is bound to the literal
    # hostname coordinator.lab, which is the only name on the internal-CA
    # certificate, and there is no catch-all/on-demand TLS. --resolve keeps
    # coordinator.lab as the SNI/Host while still connecting to 127.0.0.1.
    text = (COORD / "README.md").read_text()
    assert "https://localhost:8443/health" not in text
    assert "--resolve coordinator.lab:8443" in text


def test_policy_hujson_uses_the_at_suffix_user_reference():
    # Confirmed against headscale v0.29.3's own ACL docs
    # (docs/ref/policy.md, tag v0.29.3): a user acting as a tag owner or a
    # policy src/dst is written "name@" (e.g. "alice@", "boss@").
    text = (COORD / "config" / "policy.hujson").read_text()
    assert '"box@"' in text
    assert '"tag:box"' in text and '"tag:member"' in text


def test_policy_check_accepts_the_policy_file(tmp_path):
    # `policy check` validates against a config (it needs to know
    # policy.path and, for --bypass-grpc-and-access-database-directly, a
    # database — headscale creates a fresh sqlite db on first read if none
    # exists). Render our real config + real policy file into a scratch dir
    # and point headscale's data dir there so nothing touches a real box.
    if not shutil.which("docker"):
        pytest.skip("docker not available")
    proc = subprocess.run(["docker", "info"], capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.skip("docker daemon not reachable")

    r = bootstrap("--dry-run")
    assert r.returncode == 0, r.stderr
    rendered = _extract_between(r.stdout, "--- config/headscale.yaml ---", "--- Caddyfile.rendered ---")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(rendered)
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{cfg_file}:/etc/headscale/config.yaml:ro",
            "-v", f"{COORD / 'config' / 'policy.hujson'}:/etc/headscale/policy.hujson:ro",
            "-v", f"{data_dir}:/var/lib/headscale",
            "ghcr.io/juanfont/headscale:v0.29.3",
            "--force", "policy", "check", "-f", "/etc/headscale/policy.hujson",
            "--bypass-grpc-and-access-database-directly",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# The one test that actually runs headscale: catches a wrong config key name.
# ---------------------------------------------------------------------------


def test_headscale_configtest_accepts_the_rendered_config(tmp_path):
    if not shutil.which("docker"):
        pytest.skip("docker not available")
    proc = subprocess.run(["docker", "info"], capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.skip("docker daemon not reachable")

    r = bootstrap("--dry-run")
    assert r.returncode == 0, r.stderr
    rendered = _extract_between(r.stdout, "--- config/headscale.yaml ---", "--- Caddyfile.rendered ---")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(rendered)

    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{cfg_file}:/etc/headscale/config.yaml:ro",
            "-v", f"{COORD / 'config' / 'policy.hujson'}:/etc/headscale/policy.hujson:ro",
            "ghcr.io/juanfont/headscale:v0.29.3",
            "configtest",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _extract_between(text, start_marker, end_marker):
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    return text[start:end].strip() + "\n"
