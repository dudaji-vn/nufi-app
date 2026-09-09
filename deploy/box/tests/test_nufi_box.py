import os, pathlib, subprocess
BOX = pathlib.Path(__file__).resolve().parents[1]

def cli(*args, **env):
    e = dict(os.environ, NUFI_BOX_DRY_RUN="1", **env)
    return subprocess.run(["/bin/bash", str(BOX / "nufi-box"), *args], cwd=BOX, env=e, capture_output=True, text=True)

def test_help_lists_verbs():
    r = cli("--help"); assert r.returncode == 0
    for verb in ("status", "logs", "drive add", "ca-cert", "doctor"):
        assert verb in r.stdout

def test_drive_add_plans_folder_env_and_restart(tmp_path):
    envf = tmp_path / ".env"; envf.write_text("NUFI_DATA_DIR=%s\nDEPARTMENTS=legal\nBOX_NAME=nufi\n" % tmp_path)
    r = cli("drive", "add", "finance", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    assert "drives/finance" in r.stdout
    assert 'SAMBA_VOLUME_CONFIG_finance=' in r.stdout
    assert "DEPARTMENTS=legal,finance" in r.stdout

def test_drive_add_with_no_departments_yet(tmp_path):
    envf = tmp_path / ".env"; envf.write_text("NUFI_DATA_DIR=%s\nBOX_NAME=nufi\n" % tmp_path)
    r = cli("drive", "add", "legal", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    assert "DEPARTMENTS=legal" in r.stdout

def test_unknown_verb_fails():
    assert cli("frobnicate").returncode != 0


# --- fix round: defect 1 — hyphenated department name must not corrupt .env ---

def test_drive_add_hyphenated_department_env_key(tmp_path):
    envf = tmp_path / ".env"; envf.write_text("NUFI_DATA_DIR=%s\nBOX_NAME=nufi\n" % tmp_path)
    r = cli("drive", "add", "back-office", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    assert 'SAMBA_VOLUME_CONFIG_back_office="[back-office]; path=/shares/back-office;' in r.stdout


# --- fix round: defect 2 — relative one-level symlink invocation ---

def test_help_works_through_relative_symlink(tmp_path):
    real_dir = tmp_path / "real"; real_dir.mkdir()
    bin_dir = tmp_path / "bin"; bin_dir.mkdir()
    script = real_dir / "nufi-box"
    script.write_text((BOX / "nufi-box").read_text())
    script.chmod(0o755)
    link = bin_dir / "nufi-box"
    link.symlink_to(pathlib.Path("..") / "real" / "nufi-box")
    e = dict(os.environ, NUFI_BOX_DRY_RUN="1")
    r = subprocess.run(["/bin/bash", str(link), "--help"], cwd=str(tmp_path), env=e, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# --- fix round: defect 3 — friendly guard when .env is missing / incomplete ---

def test_drive_add_with_missing_env_file(tmp_path):
    missing = tmp_path / "does-not-exist.env"
    r = cli("drive", "add", "x", NUFI_BOX_ENV=str(missing))
    assert r.returncode == 2
    assert "no .env next to nufi-box" in r.stderr

def test_drive_add_without_nufi_data_dir(tmp_path):
    envf = tmp_path / ".env"; envf.write_text("BOX_NAME=nufi\n")
    r = cli("drive", "add", "x", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 2
    assert "NUFI_DATA_DIR is not set in .env" in r.stderr


# --- minor: clearer messages before usage ---

def test_drive_add_missing_name_message(tmp_path):
    envf = tmp_path / ".env"; envf.write_text("NUFI_DATA_DIR=%s\n" % tmp_path)
    r = cli("drive", "add", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 2
    assert "drive add: a name is required" in r.stderr

def test_unknown_verb_message(tmp_path):
    envf = tmp_path / ".env"; envf.write_text("NUFI_DATA_DIR=%s\n" % tmp_path)
    r = cli("frobnicate", NUFI_BOX_ENV=str(envf))
    assert r.returncode != 0
    assert "unknown command: frobnicate" in r.stderr


# --- fix round: defect 4 — envfile.sh helper, tested directly ---

def test_envfile_set_replaces_appends_and_preserves_other_keys(tmp_path):
    f = tmp_path / ".env"
    f.write_text("FOO=bar\nDEPARTMENTS=legal\nBAZ=qux\n")
    lib = str(BOX / "lib" / "envfile.sh")
    r = subprocess.run(
        ["/bin/bash", "-c", 'source "$0"; envfile_set "$1" DEPARTMENTS legal,hr', lib, str(f)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    content = f.read_text()
    assert "FOO=bar" in content
    assert "BAZ=qux" in content
    assert content.count("DEPARTMENTS=") == 1
    assert "DEPARTMENTS=legal,hr" in content

    r2 = subprocess.run(
        ["/bin/bash", "-c", 'source "$0"; envfile_set "$1" NEWKEY hello', lib, str(f)],
        capture_output=True, text=True,
    )
    assert r2.returncode == 0, r2.stderr
    assert "NEWKEY=hello" in f.read_text()

    leftovers = [p.name for p in tmp_path.iterdir() if p.name != ".env"]
    assert leftovers == [], leftovers

def test_envfile_has(tmp_path):
    f = tmp_path / ".env"
    f.write_text("FOO=bar\n")
    lib = str(BOX / "lib" / "envfile.sh")
    r = subprocess.run(
        ["/bin/bash", "-c", 'source "$0"; envfile_has "$1" FOO && echo yes || echo no', lib, str(f)],
        capture_output=True, text=True,
    )
    assert r.stdout.strip() == "yes"
    r2 = subprocess.run(
        ["/bin/bash", "-c", 'source "$0"; envfile_has "$1" MISSING && echo yes || echo no', lib, str(f)],
        capture_output=True, text=True,
    )
    assert r2.stdout.strip() == "no"


# --- fix round 2: trailing-newline guard ---

def test_envfile_set_appends_when_file_lacks_trailing_newline(tmp_path):
    f = tmp_path / ".env"
    f.write_bytes(b"FOO=1\nBAZ=2")  # no trailing newline
    lib = str(BOX / "lib" / "envfile.sh")
    r = subprocess.run(
        ["/bin/bash", "-c", 'source "$0"; envfile_set "$1" NEWKEY v', lib, str(f)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert f.read_text() == "FOO=1\nBAZ=2\nNEWKEY=v\n"

def test_envfile_set_replace_when_file_lacks_trailing_newline(tmp_path):
    f = tmp_path / ".env"
    f.write_bytes(b"FOO=1\nBAZ=2")  # no trailing newline, BAZ is the last line
    lib = str(BOX / "lib" / "envfile.sh")
    r = subprocess.run(
        ["/bin/bash", "-c", 'source "$0"; envfile_set "$1" BAZ 9', lib, str(f)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert f.read_text() == "FOO=1\nBAZ=9\n"


# --- fix round 2: literal (non-regex) key matching ---

def test_envfile_set_key_matching_is_literal_not_regex(tmp_path):
    f = tmp_path / ".env"
    f.write_text("A.B=1\nAXB=1\n")
    lib = str(BOX / "lib" / "envfile.sh")
    r = subprocess.run(
        ["/bin/bash", "-c", 'source "$0"; envfile_set "$1" A.B 2', lib, str(f)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    content = f.read_text()
    assert "A.B=2" in content
    assert "AXB=1" in content
    assert content.count("A.B=") == 1

def test_envfile_has_key_matching_is_literal_not_regex(tmp_path):
    f = tmp_path / ".env"
    f.write_text("AXB=1\n")
    lib = str(BOX / "lib" / "envfile.sh")
    r = subprocess.run(
        ["/bin/bash", "-c", 'source "$0"; envfile_has "$1" A.B && echo yes || echo no', lib, str(f)],
        capture_output=True, text=True,
    )
    assert r.stdout.strip() == "no"

def test_doctor_asks_the_box_about_ollama_not_this_shell(tmp_path):
    envf = tmp_path / ".env"
    envf.write_text("NUFI_DATA_DIR=%s\nOLLAMA_BASE_URL=http://host.docker.internal:11434\n" % tmp_path)
    r = cli("doctor", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    probe = [l for l in r.stdout.splitlines() if "OLLAMA_BASE_URL" in l or "api/tags" in l]
    assert probe, r.stdout
    # host.docker.internal resolves in a container and nowhere else, so a probe
    # from the host cries wolf on every healthy macOS box.
    for line in probe:
        assert "exec -T rag_api" in line, line


# --- day two must layer the same compose files the installer did ---

def test_up_layers_the_gpu_file_when_the_env_says_the_box_has_a_gpu(tmp_path):
    """install-box.sh adds docker-compose.gpu.yml + --profile gpu from
    has_nvidia() and records the answer as NVIDIA_VISIBLE_DEVICES in .env.
    nufi-box has to read it back, or `nufi-box restart` re-creates ollama from
    the base file alone: no device reservation, no gpu profile, and a box that
    silently answers on the CPU."""
    envf = tmp_path / ".env"
    envf.write_text("NUFI_DATA_DIR=%s\nNVIDIA_VISIBLE_DEVICES=all\n" % tmp_path)
    r = cli("up", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    assert "docker-compose.gpu.yml" in r.stdout
    assert "--profile gpu" in r.stdout


def test_up_leaves_the_gpu_file_out_on_a_box_without_one(tmp_path):
    envf = tmp_path / ".env"
    envf.write_text("NUFI_DATA_DIR=%s\nNVIDIA_VISIBLE_DEVICES=\n" % tmp_path)
    r = cli("up", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    assert "docker-compose.gpu.yml" not in r.stdout
    assert "--profile gpu" not in r.stdout


def test_a_missing_extra_compose_file_stops_the_command(tmp_path):
    """docker compose treats a missing -f as an empty override, so a typo in
    NUFI_BOX_COMPOSE_EXTRA would start the box without the site-local port map
    or mount it exists to apply. install-box.sh refuses; so must this."""
    envf = tmp_path / ".env"
    envf.write_text("NUFI_DATA_DIR=%s\n" % tmp_path)
    r = cli("up", NUFI_BOX_ENV=str(envf), NUFI_BOX_COMPOSE_EXTRA="/nope/missing.yml")
    assert r.returncode == 2, r.stdout
    assert "NUFI_BOX_COMPOSE_EXTRA: no such file: /nope/missing.yml" in r.stderr


def test_an_extra_compose_file_that_exists_is_layered_last(tmp_path):
    envf = tmp_path / ".env"
    envf.write_text("NUFI_DATA_DIR=%s\n" % tmp_path)
    extra = tmp_path / "local-ports.yml"
    extra.write_text("services: {}\n")
    r = cli("up", NUFI_BOX_ENV=str(envf), NUFI_BOX_COMPOSE_EXTRA=str(extra))
    assert r.returncode == 0, r.stderr
    assert f"-f {extra} up -d" in r.stdout


def test_doctor_probes_the_admin_panel_and_the_gateway(tmp_path):
    """Both are published on the box and both are things people report as
    "the box is broken": the admin panel on 3002 and the LiteLLM gateway on
    4000, whose /health/liveliness is the only check that does not need a
    master key."""
    envf = tmp_path / ".env"
    envf.write_text("NUFI_DATA_DIR=%s\n" % tmp_path)
    r = cli("doctor", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    assert "https://localhost:3002/" in r.stdout
    assert "https://localhost:4000/health/liveliness" in r.stdout


# --- Task 6: nufi-box mesh up | status | down --------------------------------

def mesh_env(tmp_path, **extra):
    lines = {
        "NUFI_DATA_DIR": str(tmp_path),
        "BOX_NAME": "nufi",
        "BOX_HOST": "nufi.local",
        "BOX_IP": "192.168.1.10",
        "MESH_SERVER_URL": "https://coordinator.lab",
        "MESH_AUTH_KEY": "tskey-auth-test",
    }
    lines.update(extra)
    envf = tmp_path / ".env"
    envf.write_text("".join("%s=%s\n" % kv for kv in lines.items()))
    return str(envf)


def test_mesh_up_plans_the_join_the_env_write_and_the_caddy_reload(tmp_path):
    r = cli("mesh", "up", NUFI_BOX_ENV=mesh_env(tmp_path), NUFI_BOX_FAKE_OS="Linux")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "docker-compose.mesh.yml" in out
    assert "--profile mesh" in out
    assert "up -d tailscale" in out
    assert "tailscale ip -4" in out
    assert "BOX_MESH_IP=" in out
    assert "BOX_MESH_HOST=" in out
    assert "caddy/mesh.caddy" in out
    assert "caddy reload --config /etc/caddy/Caddyfile" in out


def test_mesh_up_refuses_without_a_coordinator(tmp_path):
    envf = tmp_path / ".env"
    envf.write_text("NUFI_DATA_DIR=%s\nBOX_NAME=nufi\n" % tmp_path)
    r = cli("mesh", "up", NUFI_BOX_ENV=str(envf), NUFI_BOX_FAKE_OS="Linux")
    assert r.returncode == 2
    assert "MESH_SERVER_URL" in r.stderr


def test_mesh_up_refuses_without_an_auth_key_on_linux(tmp_path):
    envf = mesh_env(tmp_path, MESH_AUTH_KEY="")
    r = cli("mesh", "up", NUFI_BOX_ENV=envf, NUFI_BOX_FAKE_OS="Linux")
    assert r.returncode == 2
    assert "MESH_AUTH_KEY" in r.stderr


def test_mesh_up_on_macos_prints_the_native_tailscale_commands(tmp_path):
    """Docker Desktop's `network_mode: host` is the Linux VM's network, not the
    Mac's, so a macOS box joins with the real Tailscale app instead."""
    r = cli("mesh", "up", NUFI_BOX_ENV=mesh_env(tmp_path), NUFI_BOX_FAKE_OS="Darwin")
    assert "/Applications/Tailscale.app/Contents/MacOS/Tailscale" in r.stdout
    assert "--login-server=https://coordinator.lab" in r.stdout
    assert "--auth-key=" in r.stdout
    assert "docker-compose.mesh.yml" not in r.stdout


def test_mesh_status_plans_tailscale_status(tmp_path):
    envf = mesh_env(tmp_path, BOX_MESH_IP="100.64.0.7", BOX_MESH_HOST="nufi.box.lab")
    r = cli("mesh", "status", NUFI_BOX_ENV=envf, NUFI_BOX_FAKE_OS="Linux")
    assert r.returncode == 0, r.stderr
    assert "100.64.0.7" in r.stdout
    assert "nufi.box.lab" in r.stdout
    assert "tailscale status" in r.stdout


def test_mesh_down_stops_the_node_and_clears_the_addresses(tmp_path):
    envf = mesh_env(tmp_path, BOX_MESH_IP="100.64.0.7", BOX_MESH_HOST="nufi.box.lab")
    r = cli("mesh", "down", NUFI_BOX_ENV=envf, NUFI_BOX_FAKE_OS="Linux")
    assert r.returncode == 0, r.stderr
    assert "stop tailscale" in r.stdout
    assert "BOX_MESH_IP=" in r.stdout
    assert "caddy reload" in r.stdout


def test_mesh_without_a_subcommand_is_an_error(tmp_path):
    r = cli("mesh", NUFI_BOX_ENV=mesh_env(tmp_path))
    assert r.returncode == 2
    assert "mesh" in r.stderr


def test_help_lists_the_mesh_lifecycle_verbs():
    out = cli("--help").stdout
    assert "mesh up" in out


# --- the department routines in Studio (Task 8) ---

def _flows_env(tmp_path, **extra):
    envf = tmp_path / ".env"
    lines = ["NUFI_DATA_DIR=%s" % tmp_path, "DEPARTMENTS=legal,hr", "BOX_HOST=nufi.local",
             "ADMIN_EMAIL=admin@nufi.local", "INFERENCE_MODEL=qwen2.5:7b",
             "EMBEDDINGS_MODEL=bge-m3",
             "OLLAMA_BASE_URL=http://host.docker.internal:11434"]
    lines += ["%s=%s" % kv for kv in extra.items()]
    envf.write_text("\n".join(lines) + "\n")
    return envf


def test_flows_needs_a_subcommand(tmp_path):
    envf = _flows_env(tmp_path)
    r = cli("flows", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 2
    assert "install or list" in r.stderr
    assert cli("flows", "frobnicate", NUFI_BOX_ENV=str(envf)).returncode == 2


def test_flows_install_plans_the_builder_call(tmp_path):
    envf = _flows_env(tmp_path)
    r = cli("flows", "install", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    assert "build_flows.py" in r.stdout
    for arg in ("--box https://localhost:7860", "--drives-root /drives",
                "--departments legal,hr", "--model qwen2.5:7b", "--embeddings bge-m3",
                "--login admin@nufi.local"):
        assert arg in r.stdout, (arg, r.stdout)
    assert str(tmp_path / "studio-flows.json") in r.stdout


def test_flows_install_never_puts_the_key_in_an_argument(tmp_path):
    """An argument is readable by any other local user through `ps`. The key
    travels in the environment (the builder reads $STUDIO_API_KEY) and the
    minted one comes back through a mode-0600 file."""
    envf = _flows_env(tmp_path, STUDIO_API_KEY="sk-secret-value")
    r = cli("flows", "install", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    assert "sk-secret-value" not in r.stdout
    assert "--key " not in r.stdout


def test_flows_list_without_a_key_says_what_to_run(tmp_path):
    """Not a dry run: this is the real path, and it must refuse before it
    reaches the network rather than asking Studio with an empty key."""
    envf = _flows_env(tmp_path)
    e = dict(os.environ, NUFI_BOX_ENV=str(envf))
    e.pop("NUFI_BOX_DRY_RUN", None)
    e.pop("STUDIO_API_KEY", None)
    r = subprocess.run(["/bin/bash", str(BOX / "nufi-box"), "flows", "list"],
                       cwd=BOX, env=e, capture_output=True, text=True)
    assert r.returncode == 2, r.stdout
    assert "nufi-box flows install" in r.stderr


def test_flows_install_says_what_is_missing_without_the_builder(tmp_path):
    """deploy/box travels with deploy/platform/scenarios. When someone copies
    only the box, say which directory is missing instead of failing inside
    python3."""
    box = tmp_path / "box"
    (box / "lib").mkdir(parents=True)
    for name in ("nufi-box", "docker-compose.yml"):
        (box / name).write_text((BOX / name).read_text())
    for name in ("flows.sh", "envfile.sh"):
        (box / "lib" / name).write_text((BOX / "lib" / name).read_text())
    (box / ".env").write_text("NUFI_DATA_DIR=%s\nDEPARTMENTS=legal\n" % tmp_path)
    r = subprocess.run(["/bin/bash", str(box / "nufi-box"), "flows", "install"],
                       cwd=box, env=dict(os.environ, NUFI_BOX_DRY_RUN="1"),
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "the builder is missing" in r.stderr
    assert "deploy/platform/scenarios" in r.stderr


def test_help_lists_the_flows_verbs():
    out = cli("--help").stdout
    assert "flows install" in out and "flows list" in out


# --- Task 9b / defect D3: a generated caddy/mesh.caddy from an older box ---

def test_up_and_restart_check_the_generated_mesh_caddy_first(tmp_path):
    """Both start Caddy again, so both are where a render left by an older box
    refuses the whole front door. The acceptance found the box crash-looping
    after an upgrade; nothing but a human noticing had ever put it right."""
    envf = tmp_path / ".env"; envf.write_text("NUFI_DATA_DIR=%s\nBOX_NAME=nufi\n" % tmp_path)
    for verb, compose in (("up", "up -d"), ("restart", "restart")):
        r = cli(verb, NUFI_BOX_ENV=str(envf))
        assert r.returncode == 0, r.stderr
        assert "caddy/mesh.caddy" in r.stdout, r.stdout
        assert r.stdout.index("caddy/mesh.caddy") < r.stdout.index(compose), r.stdout


def test_doctor_says_when_the_generated_mesh_caddy_is_from_an_older_box(tmp_path):
    """It only bites at the next Caddy restart, so a box can be answering now
    and be one reboot from six dead ports. doctor is where that gets said."""
    envf = tmp_path / ".env"; envf.write_text("NUFI_DATA_DIR=%s\nBOX_NAME=nufi\n" % tmp_path)
    r = cli("doctor", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    assert "caddy/mesh.caddy" in r.stdout and "Caddyfile" in r.stdout
