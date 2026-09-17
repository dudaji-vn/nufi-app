import os, pathlib, shutil, subprocess
BOX = pathlib.Path(__file__).resolve().parents[1]
BASH = "/bin/bash"   # macOS ships 3.2 here; the script must run under it

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
    # And the command it hands the operator has to work: headscale v0.29.3's
    # `--user` takes the numeric user id, so `--user box` fails as printed.
    assert "--user box" not in r.stderr
    assert "users list -o json" in r.stderr


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


def test_drive_add_gives_the_new_drive_to_the_samba_uid(tmp_path):
    """Defect D1's other half: `nufi-box drive add` creates a department drive
    too, and a drive the Samba account cannot write to is the same failure the
    P2 acceptance hit — `sudo nufi-box drive add` is all it takes."""
    envf = tmp_path / ".env"
    envf.write_text("NUFI_DATA_DIR=%s\nBOX_NAME=nufi\nNUFI_SMB_UID=501\nNUFI_SMB_GID=988\n" % tmp_path)
    r = cli("drive", "add", "finance", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    assert "chown -R 501:988" in r.stdout and "drives/finance" in r.stdout
    assert r.stdout.index("mkdir -p") < r.stdout.index("chown -R"), r.stdout


def test_drive_add_on_a_box_that_predates_the_uid_still_works(tmp_path):
    """An .env written before NUFI_SMB_UID existed must not make the verb fail."""
    envf = tmp_path / ".env"; envf.write_text("NUFI_DATA_DIR=%s\nBOX_NAME=nufi\n" % tmp_path)
    r = cli("drive", "add", "finance", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    assert "chown" not in r.stdout


# --- the mesh node is part of a mesh box's stack -----------------------------
#
# $COMPOSE knew about the emulate, linux, gpu and extra layers and not the mesh
# one, which was layered exclusively inside mesh_compose_cmd. So `nufi-box logs
# tailscale` -- the command lib/mesh.sh prints when a join fails -- exited "no
# such service"; `status` did not show the node; and `down` stopped the box's
# front door while leaving the node registered and advertising it. install-box.
# sh:500 already assembles it this way for the same box.


def test_a_mesh_box_knows_about_its_own_mesh_node(tmp_path):
    envf = mesh_env(tmp_path, BOX_MESH_IP="100.64.0.7", BOX_MESH_HOST="nufi.box.lab")
    for verb, tail in (("status", "ps --format"), ("down", "down"), ("up", "up -d")):
        r = cli(verb, NUFI_BOX_ENV=envf, NUFI_BOX_FAKE_OS="Linux")
        assert r.returncode == 0, r.stderr
        line = next(l for l in r.stdout.splitlines() if tail in l and l.startswith("  $ docker compose"))
        assert "docker-compose.mesh.yml" in line, (verb, line)
        assert "--profile mesh" in line, (verb, line)


def test_the_hint_printed_when_a_join_fails_names_a_service_nufi_box_has(tmp_path):
    # lib/mesh.sh: "tailscaled never reported an address; look at: nufi-box
    # logs tailscale" -- handed to the operator whose box has just failed to
    # join, and it used to exit "no such service".
    envf = mesh_env(tmp_path)
    r = cli("logs", "tailscale", NUFI_BOX_ENV=envf, NUFI_BOX_FAKE_OS="Linux")
    assert r.returncode == 0, r.stderr
    assert "docker-compose.mesh.yml" in r.stdout
    assert "logs -f --tail=200 tailscale" in r.stdout


def test_a_lan_only_box_gets_no_mesh_layer(tmp_path):
    envf = tmp_path / ".env"
    envf.write_text("NUFI_DATA_DIR=%s\nBOX_NAME=nufi\n" % tmp_path)
    r = cli("status", NUFI_BOX_ENV=str(envf), NUFI_BOX_FAKE_OS="Linux")
    assert r.returncode == 0, r.stderr
    assert "docker-compose.mesh.yml" not in r.stdout


def test_a_macos_mesh_box_gets_no_mesh_container(tmp_path):
    """Docker Desktop's host network is the Linux VM's, so a tailscale
    container there could never give the Mac a mesh address -- a Mac box joins
    with the native app (mesh_up_native)."""
    r = cli("status", NUFI_BOX_ENV=mesh_env(tmp_path), NUFI_BOX_FAKE_OS="Darwin")
    assert r.returncode == 0, r.stderr
    assert "docker-compose.mesh.yml" not in r.stdout


def test_mesh_up_does_not_pass_the_mesh_file_twice(tmp_path):
    """Both nufi-box and mesh_compose_cmd want to add it; the same -f twice
    asks compose to merge the file with itself."""
    r = cli("mesh", "up", NUFI_BOX_ENV=mesh_env(tmp_path), NUFI_BOX_FAKE_OS="Linux")
    assert r.returncode == 0, r.stderr
    line = next(l for l in r.stdout.splitlines() if "up -d tailscale" in l)
    assert line.count("docker-compose.mesh.yml") == 1, line
    assert line.count("--profile mesh") == 1, line


# --- backup and restore ---------------------------------------------------
#
# Dry run, so these assert the plan rather than the effect: the same trick the
# drive and mesh tests use. What is worth pinning is what a restore would NEED
# and an eye would not miss -- two database dumps look like a complete backup
# right up to the moment someone tries to bring a box back from them.

def _env(tmp_path, **extra):
    envf = tmp_path / ".env"
    body = {"NUFI_DATA_DIR": str(tmp_path), "BOX_NAME": "nufi", "BOX_HOST": "nufi.local",
            "POSTGRES_USER": "nufi", "NUFI_MODEL": "qwen2.5-14b"}
    body.update(extra)
    envf.write_text("".join(f"{k}={v}\n" for k, v in body.items()))
    return envf


def test_backup_takes_everything_a_restore_needs(tmp_path):
    r = cli("backup", NUFI_BOX_ENV=str(_env(tmp_path)))
    assert r.returncode == 0, r.stderr
    out = r.stdout
    # The two the plan names...
    # --clean, or a restore onto a box that still has its databases merges into
    # them: "relation already exists" on every table, rows added since the
    # backup surviving, and success reported.
    assert "pg_dumpall --clean" in out, out
    assert "mongodump" in out, out
    # ...and the four it does not, each of which a restore cannot do without.
    # A box rebuilt from the dumps alone comes up with every account and agent
    # and no documents, on new secrets, behind a certificate no laptop trusts.
    assert "drives.tar.gz" in out, "the department's own documents"
    assert "app-uploads.tar.gz" in out, "files people attached in the app"
    assert "ca.tar.gz" in out, "the certificate published to laptops"
    # The box's real authority is the root key inside caddy-data; the file on
    # the host is only the copy handed out. Restore without the volume and the
    # box comes back serving a certificate nothing trusts.
    assert "caddy-data.tar.gz" in out, "the certificate authority itself"
    assert "ingest-state.tar.gz" in out, "what has already been uploaded, or it all goes up twice"
    assert "/env" in out, "the secrets every one of those is keyed to"


def test_backup_leaves_generated_reports_out_of_the_archive(tmp_path):
    # _routines holds what the scheduler wrote; the box can write them again,
    # and keeping them would grow every backup for ever.
    r = cli("backup", NUFI_BOX_ENV=str(_env(tmp_path)))
    assert "--exclude '_routines'" in r.stdout, r.stdout


def test_backup_prunes_old_runs_and_keeps_the_newest(tmp_path):
    backups = tmp_path / "backup"
    backups.mkdir()
    for day in range(1, 10):
        (backups / f"2026090{day}-000000").mkdir()
    (backups / "not-a-backup").mkdir()
    r = cli("backup", "--keep", "3", NUFI_BOX_ENV=str(_env(tmp_path)))
    assert r.returncode == 0, r.stderr
    pruned = {line.split()[-1] for line in r.stdout.splitlines() if line.strip().startswith("pruning ")}
    assert pruned == {f"2026090{d}-000000" for d in range(1, 7)}, pruned
    assert "not-a-backup" not in r.stdout, "only this command's own directories are pruned"


def test_restore_refuses_a_directory_that_is_not_a_backup(tmp_path):
    (tmp_path / "junk").mkdir()
    r = cli("restore", str(tmp_path / "junk"), "--yes", NUFI_BOX_ENV=str(_env(tmp_path)))
    assert r.returncode != 0
    assert "MANIFEST" in r.stderr


def test_restore_puts_the_secrets_back_before_it_starts_anything(tmp_path):
    """Order is the whole correctness of a restore.

    Data restored into a stack already running on freshly generated secrets is
    a restore that half-works: the rows come back and the sessions, signed
    tokens and certificate do not match them.
    """
    src = tmp_path / "20260914-000000"
    src.mkdir()
    (src / "MANIFEST").write_text("box: nufi\n")
    (src / "env").write_text("BOX_NAME=nufi\n")
    r = cli("restore", str(src), "--yes", NUFI_BOX_ENV=str(_env(tmp_path)))
    assert r.returncode == 0, r.stderr
    plan = r.stdout
    assert plan.index("/env") < plan.index("compose") and plan.index("/env") < plan.index("up -d"), plan


def test_status_says_when_the_last_backup_was(tmp_path):
    envf = _env(tmp_path)
    r = cli("status", NUFI_BOX_ENV=str(envf))
    assert "Last backup: never" in r.stdout, r.stdout
    (tmp_path / "backup" / "20260914-033000").mkdir(parents=True)
    r = cli("status", NUFI_BOX_ENV=str(envf))
    assert "Last backup: 20260914-033000" in r.stdout, r.stdout


def test_nightly_installs_a_host_timer_not_a_container(tmp_path):
    """The box's own scheduler runs Studio flows, and a container that could
    back the box up would need the docker socket -- the whole host, handed to
    anything that gets into that container. The timer belongs to the host."""
    env = str(_env(tmp_path))
    mac = cli("backup", "--install-nightly", "--at", "02:15",
              NUFI_BOX_ENV=env, NUFI_BOX_FAKE_OS="Darwin")
    assert mac.returncode == 0, mac.stderr
    assert "launchctl load" in mac.stdout and "LaunchAgents" in mac.stdout
    assert "<integer>02</integer>" in mac.stdout and "<integer>15</integer>" in mac.stdout

    linux = cli("backup", "--install-nightly", "--at", "02:15",
                NUFI_BOX_ENV=env, NUFI_BOX_FAKE_OS="Linux")
    assert linux.returncode == 0, linux.stderr
    assert "nufi-box-backup.timer" in linux.stdout
    assert "OnCalendar=*-*-* 02:15:00" in linux.stdout


# --- the name every other laptop uses -------------------------------------

def test_doctor_checks_the_name_and_not_only_localhost(tmp_path):
    """`doctor` passed ten checks and none of them was the one that breaks.

    Every check went to localhost. `nufi.local` — the address each laptop in
    the room types — was never looked at. The installer announces that name
    over mDNS with the address the machine had at install time, so a new DHCP
    lease leaves the name pointing at a stranger while `doctor` still reports
    All good. That happened three times in five days on the development box.
    """
    r = cli("doctor", NUFI_BOX_ENV=str(_env(tmp_path, BOX_IP="192.168.1.25")))
    assert "nufi.local" in r.stdout, r.stdout


def test_announce_republishes_the_name_at_the_address_the_box_has_now(tmp_path):
    """The fix has to be one command, or it will not be run before a demo.

    Re-running the whole installer works and is far too big a hammer for "the
    laptop moved network", which is the common case.
    """
    r = cli("announce", NUFI_BOX_ENV=str(_env(tmp_path, BOX_IP="10.0.0.9")),
            NUFI_BOX_FAKE_OS="Darwin")
    assert r.returncode == 0, r.stderr
    # The stale publisher has to go first: a second dns-sd for a name another
    # process still holds is ignored, so the announce silently does nothing.
    assert "pkill" in r.stdout, r.stdout
    assert "dns-sd -P nufi" in r.stdout, r.stdout
    assert "BOX_IP=" in r.stdout, "the new address belongs in .env too"


def test_announce_on_linux_uses_avahi(tmp_path):
    r = cli("announce", NUFI_BOX_ENV=str(_env(tmp_path)), NUFI_BOX_FAKE_OS="Linux")
    assert r.returncode == 0, r.stderr
    assert "avahi-publish" in r.stdout, r.stdout


# --- people, as opposed to laptops ----------------------------------------

def test_user_add_creates_an_account_through_the_apps_own_tool(tmp_path):
    """A box shipped with no way to give the second person an account.

    Registration is off by design — a department appliance is not a public
    sign-up — and `invite` and `members` are about laptops joining the mesh,
    not people. The capability was inside the app image all along, behind
    `docker compose exec librechat npm run create-user`, which nobody had
    written down. A department of eight could not log in.
    """
    r = cli("user", "add", "alice@dept.local", NUFI_BOX_ENV=str(_env(tmp_path)))
    assert r.returncode == 0, r.stderr
    assert "create-user" in r.stdout, r.stdout
    assert "alice@dept.local" in r.stdout
    # The username is derived, because the app wants one and an email is what
    # an administrator actually has to hand.
    assert "alice" in r.stdout


def test_user_add_generates_a_password_rather_than_asking_for_one(tmp_path):
    """The installer generates the admin's password; this matches it.

    Asking an administrator to invent a password per person is how every
    account on the box ends up with the same one.
    """
    import re
    r = cli("user", "add", "bob@dept.local", NUFI_BOX_ENV=str(_env(tmp_path)))
    assert r.returncode == 0, r.stderr
    shown = re.search(r"password:\s+([0-9a-f]{16})\b", r.stdout)
    assert shown, f"no generated password in the output: {r.stdout}"
    # ...and a second call does not hand out the same one.
    again = cli("user", "add", "bob@dept.local", NUFI_BOX_ENV=str(_env(tmp_path)))
    other = re.search(r"password:\s+([0-9a-f]{16})\b", again.stdout)
    assert other and other.group(1) != shown.group(1), "the password is not being generated"


def test_user_list_and_a_refused_verb(tmp_path):
    env = str(_env(tmp_path))
    assert "list-users" in cli("user", "list", NUFI_BOX_ENV=env).stdout
    assert cli("user", "frobnicate", NUFI_BOX_ENV=env).returncode != 0
    assert cli("user", NUFI_BOX_ENV=env).returncode != 0


def test_user_add_refuses_something_that_is_not_an_email(tmp_path):
    """The address becomes a login; a typo becomes an account nobody can use."""
    r = cli("user", "add", "not-an-email", NUFI_BOX_ENV=str(_env(tmp_path)))
    assert r.returncode != 0
    assert "email" in (r.stderr + r.stdout).lower()


# --- the egress proxy, asked to prove its filter is loaded -----------------

def test_doctor_checks_the_egress_proxy_refuses(tmp_path):
    """A proxy that lets everything through looks identical to one that
    works, from the box. Doctor asks it for a host that is not on the list
    and expects a 403 -- the one answer that proves the filter is loaded."""
    r = cli("doctor", NUFI_BOX_ENV=str(_env(tmp_path)))
    assert "works-egress" in r.stdout, r.stdout
    assert "403" in r.stdout or "refuses" in r.stdout, r.stdout


# --- Works on the box: register the sandbox environment --------------------

def _works_env(tmp_path, **extra):
    body = {"NUFI_WORKS": "1", "ADMIN_EMAIL": "admin@nufi.local", "ADMIN_PASSWORD": "pw",
            "LITELLM_MASTER_KEY": "sk-master", "BOX_NAME": "nufi",
            "WORKS_SANDBOX_IMAGE": "ghcr.io/dudaji-vn/nufi-sandbox@sha256:" + "0" * 64}
    body.update(extra)
    return _env(tmp_path, **body)


def test_works_needs_a_subcommand(tmp_path):
    envf = _works_env(tmp_path)
    r = cli("works", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 2 and "install or status" in r.stderr
    assert cli("works", "frobnicate", NUFI_BOX_ENV=str(envf)).returncode == 2


def test_works_install_runs_the_registrar_inside_the_box_network(tmp_path):
    """The registrar must reach the box by the name the certificate carries and
    trust the box's CA, and inside the network both are already true: the name
    resolves to Caddy and the CA is a file. So it runs there, via compose run,
    with the secrets in the environment and never in an argument."""
    envf = _works_env(tmp_path)
    r = cli("works", "install", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "compose" in out and "run --rm --no-deps" in out and "nufi-cron" in out, out
    assert "register_works.py" in out
    for arg in ("--works https://nufi.local:3003", "--chat https://nufi.local:3080",
                "--litellm http://litellm-proxy:4000", "--login admin@nufi.local", "--company nufi",
                "--image ghcr.io/dudaji-vn/nufi-sandbox@sha256:"):
        assert arg in out, (arg, out)
    for secret in ("pw", "sk-master"):
        assert " %s " % secret not in out and "=%s" % secret not in out, secret
    for passed in ("-e ADMIN_PASSWORD", "-e LITELLM_MASTER_KEY", "-e WORKS_BOX_KEY", "-e WORKS_MODEL_KEY"):
        assert passed in out, passed
    assert "--profile works" in out


def test_works_install_refuses_a_box_installed_without_works(tmp_path):
    envf = _env(tmp_path, NUFI_WORKS="0")
    r = cli("works", "install", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 2
    assert "--with-works" in r.stderr


def test_works_install_needs_the_pinned_image(tmp_path):
    envf = _works_env(tmp_path, WORKS_SANDBOX_IMAGE="")
    r = cli("works", "install", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 2
    assert "WORKS_SANDBOX_IMAGE" in r.stderr


def test_works_status_plans_the_read_only_check(tmp_path):
    envf = _works_env(tmp_path, WORKS_BOX_KEY="bk")
    r = cli("works", "status", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    assert "--check" in r.stdout and "register_works.py" in r.stdout
    assert "bk" not in r.stdout.replace("WORKS_BOX_KEY", "")


# --- doctor knows a Works box -----------------------------------------------

def test_doctor_checks_a_works_box_four_ways(tmp_path):
    r = cli("doctor", NUFI_BOX_ENV=str(_works_env(tmp_path)))
    out = r.stdout
    assert "runsc" in out, "the runtime the sandboxes depend on"
    assert "DOCKER_GID" in out, "the socket's group, or every sandbox creation fails EACCES"
    assert "3003/api/health" in out
    assert "--check" in out and "register_works.py" in out, "the registration, read-only"


def test_doctor_says_nothing_about_works_on_a_box_without_it(tmp_path):
    r = cli("doctor", NUFI_BOX_ENV=str(_env(tmp_path)))
    for absent in ("runsc", "3003", "register_works"):
        assert absent not in r.stdout, absent


# --- schedule list, including event-triggered (watch) sections -------------

def test_schedule_list_shows_a_watch_section(tmp_path):
    """Not a dry run: `schedule_list` only ever runs `python3` for real (it
    has nothing to plan), so NUFI_BOX_DRY_RUN is dropped here -- the same
    real path `test_flows_list_without_a_key_says_what_to_run` exercises."""
    envf = _env(tmp_path)
    (tmp_path / "schedules.ini").write_text(
        "[hr-onboarding]\n"
        "watch = onboarding/new\n"
        "flow  = HR · leave entitlement\n"
        "drive = hr\n"
        "ask   = onboarding/new/{file} 에 새 입사자의 서류가 들어왔습니다.\n"
        "out   = onboarding-{file}-{date}.md\n"
    )
    e = dict(os.environ, NUFI_BOX_ENV=str(envf))
    e.pop("NUFI_BOX_DRY_RUN", None)
    r = subprocess.run(["/bin/bash", str(BOX / "nufi-box"), "schedule", "list"],
                       cwd=BOX, env=e, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "hr-onboarding" in r.stdout
    assert "on file in onboarding/new/" in r.stdout
    assert "(next file)" in r.stdout
    # the {date} half is filled in for the preview; {file} stays literal
    assert "-> hr/_routines/onboarding-{file}-" in r.stdout


def test_schedule_list_still_shows_a_cron_section_next_to_a_watch_one(tmp_path):
    envf = _env(tmp_path)
    (tmp_path / "schedules.ini").write_text(
        "[legal-weekly]\n"
        "cron  = 0 17 * * 5\n"
        "flow  = Routine · weekly report from the drive\n"
        "drive = legal\n"
        "ask   = q\n"
        "out   = weekly-report-{date}.md\n"
        "\n"
        "[hr-onboarding]\n"
        "watch = onboarding/new\n"
        "flow  = HR · leave entitlement\n"
        "drive = hr\n"
        "ask   = q {file}\n"
        "out   = onboarding-{file}-{date}.md\n"
    )
    e = dict(os.environ, NUFI_BOX_ENV=str(envf))
    e.pop("NUFI_BOX_DRY_RUN", None)
    r = subprocess.run(["/bin/bash", str(BOX / "nufi-box"), "schedule", "list"],
                       cwd=BOX, env=e, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "legal-weekly" in r.stdout and "0 17 * * 5" in r.stdout
    assert "hr-onboarding" in r.stdout and "on file in onboarding/new/" in r.stdout



# --- update ---------------------------------------------------------------
#
# `update` fetches over the network, resolves a ref through the GitHub API,
# snapshots and re-tags real docker images, and re-runs install-box.sh —
# none of which this suite may do for real. The dry-run tests below are the
# plan; the real-mode ones run the actual (non---dry-run) code path against a
# temp HERE built the same way test_install.py's
# test_a_failing_image_pull_is_retried_three_times_then_explained builds one:
# a full copy of this checkout, so every real file `update` depends on
# (lib/mesh.sh, Caddyfile, docker-compose.yml, ...) is there, with
# `curl`/`docker` replaced by a stub PATH, `NUFI_BOX_SOURCE` pointed at the
# stub (so the GitHub API resolve is never attempted), and install-box.sh
# plus the `doctor` verb replaced by fakes this test controls.

def test_update_dry_run_plan_names_the_fetch_snapshot_apply_check_and_rollback(tmp_path):
    r = cli("update", NUFI_BOX_ENV=str(_env(tmp_path)))
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "api.github.com/repos/dudaji-vn/nufi-app/commits/main" in out
    assert "codeload.github.com/dudaji-vn/nufi-app/tar.gz" in out
    assert "tar -xzf" in out, "the whole archive, not selected members -- GNU tar does not glob member names"
    assert "deploy/box" in out
    assert "deploy/platform/scenarios" in out
    assert "deploy/platform/adapters/nufi-cron" in out
    assert "nufi-box backup" in out
    assert ".previous" in out
    assert "images.txt" in out
    assert "COMPLETE" in out
    assert "install-box.sh --yes --no-trust" in out
    assert "doctor" in out
    assert "rollback" in out, "the plan has to say a failed check rolls back on its own"


def test_update_ref_resolves_the_named_tag(tmp_path):
    out = cli("update", "--ref", "nufi-box-v1.2.0", NUFI_BOX_ENV=str(_env(tmp_path))).stdout
    assert "api.github.com/repos/dudaji-vn/nufi-app/commits/nufi-box-v1.2.0" in out
    assert "Fetching nufi-box-v1.2.0" in out


def test_update_a_custom_source_skips_the_resolve(tmp_path):
    envf = _env(tmp_path, NUFI_BOX_SOURCE="https://mirror.example/box.tar.gz")
    out = cli("update", NUFI_BOX_ENV=str(envf)).stdout
    assert "api.github.com" not in out
    assert "mirror.example/box.tar.gz" in out


def test_update_rollback_dry_run_plan_names_previous_tag_up_and_doctor(tmp_path):
    r = cli("update", "--rollback", NUFI_BOX_ENV=str(_env(tmp_path)))
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert ".previous" in out
    assert "docker tag" in out
    assert "up -d" in out
    assert "doctor" in out


def test_update_rollback_without_previous_dies_with_nothing_to_roll_back_to(tmp_path):
    """Real mode, not dry-run: a box (or, here, a temp HERE holding just
    enough of one) that has never been updated has no .previous to roll back
    to, and that has to be a plain refusal, not a script erroring its way
    through a missing directory."""
    here = tmp_path / "box"
    here.mkdir()
    shutil.copy(BOX / "nufi-box", here / "nufi-box")
    (here / "nufi-box").chmod(0o755)
    (here / "lib").mkdir()
    shutil.copy(BOX / "lib" / "update.sh", here / "lib" / "update.sh")
    e = dict(os.environ, NUFI_BOX_ENV=str(_env(tmp_path)))
    e.pop("NUFI_BOX_DRY_RUN", None)
    r = subprocess.run([BASH, str(here / "nufi-box"), "update", "--rollback"],
                       cwd=here, env=e, capture_output=True, text=True)
    assert r.returncode == 2
    assert "nothing to roll back to" in r.stderr


def test_update_rollback_with_an_incomplete_snapshot_dies(tmp_path):
    """A .previous started but never finished (the box lost power between the
    file copy and images.txt, say) must read as no snapshot at all, not as
    one a rollback trusts halfway."""
    here = tmp_path / "box"
    here.mkdir()
    shutil.copy(BOX / "nufi-box", here / "nufi-box")
    (here / "nufi-box").chmod(0o755)
    (here / "lib").mkdir()
    shutil.copy(BOX / "lib" / "update.sh", here / "lib" / "update.sh")
    (here / ".previous").mkdir()
    (here / ".previous" / "tree").mkdir()
    # No COMPLETE file -- the interrupted case.
    e = dict(os.environ, NUFI_BOX_ENV=str(_env(tmp_path)))
    e.pop("NUFI_BOX_DRY_RUN", None)
    r = subprocess.run([BASH, str(here / "nufi-box"), "update", "--rollback"],
                       cwd=here, env=e, capture_output=True, text=True)
    assert r.returncode == 2
    assert "incomplete" in r.stderr
    assert "nothing to roll back to" in r.stderr


# --- C3: a NUFI_DATA_DIR that is not literally $HERE/data ------------------
#
# Exercises _update_protect_paths + _update_copy directly, the way
# test_envfile_set_... sources lib/envfile.sh directly: no docker, no curl,
# no backup -- just the exclude computation and the copy it drives, which is
# the whole surface the bug (an unanchored exclude protecting nothing for a
# custom data directory) lived in.

def _run_update_copy(here, data_dir, src, dst):
    lib = str(BOX / "lib" / "update.sh")
    script = (
        'HERE="$1"; DRY=0; NUFI_DATA_DIR="$2"; src="$3"; dst="$4"\n'
        'run() { "$@"; }\n'
        'die() { echo "$*" >&2; exit 2; }\n'
        'source "$0"\n'
        '_update_protect_paths\n'
        '_update_copy "$src" "$dst"\n'
    )
    return subprocess.run([BASH, "-c", script, lib, str(here), str(data_dir), str(src), str(dst)],
                          capture_output=True, text=True)


def test_a_custom_data_dir_under_here_survives_apply_and_rollback(tmp_path):
    here = tmp_path / "box"
    storage = here / "storage"
    storage.mkdir(parents=True)
    (storage / "drives.txt").write_text("the department's own documents\n")
    src = tmp_path / "release"
    src.mkdir()
    (src / "newfile.txt").write_text("the new release\n")

    r = _run_update_copy(here, storage, src, here)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (storage / "drives.txt").read_text() == "the department's own documents\n", \
        "an apply must not delete a NUFI_DATA_DIR that is not literally $HERE/data"
    assert (here / "newfile.txt").read_text() == "the new release\n"

    # And the same holds copying the other direction, as a rollback does.
    src2 = tmp_path / "previous"
    src2.mkdir()
    (src2 / "oldfile.txt").write_text("what was here before\n")
    r2 = _run_update_copy(here, storage, src2, here)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert (storage / "drives.txt").read_text() == "the department's own documents\n"
    assert (here / "oldfile.txt").read_text() == "what was here before\n"


def test_a_data_dir_that_is_the_box_directory_itself_refuses(tmp_path):
    """A misconfiguration an apply cannot protect its way around: every file
    under $HERE is "the tree" to an exclude list that ends up excluding
    nothing. Refused outright, before anything is copied."""
    here = tmp_path / "box"
    here.mkdir()
    src = tmp_path / "release"
    src.mkdir()
    (src / "newfile.txt").write_text("new\n")
    r = _run_update_copy(here, here, src, here)
    assert r.returncode == 2
    assert "NUFI_DATA_DIR is the box directory itself" in r.stderr
    assert not (here / "newfile.txt").exists(), "nothing on the box was changed"


def test_here_reached_through_a_symlink_still_protects_the_data_dir(tmp_path):
    """HERE and NUFI_DATA_DIR spelled through different symlink chains to
    the same disk location must not read as unrelated paths — the
    regression this closes: the old code compared strings, not places."""
    real = tmp_path / "real"
    (real / "data").mkdir(parents=True)
    (real / "data" / "drives.txt").write_text("the department's own documents\n")
    link = tmp_path / "link"
    link.symlink_to(real)
    src = tmp_path / "release"
    src.mkdir()
    (src / "newfile.txt").write_text("new\n")

    r = _run_update_copy(link, real / "data", src, link)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (real / "data" / "drives.txt").read_text() == "the department's own documents\n"
    assert (link / "newfile.txt").read_text() == "new\n"


def test_a_data_dir_symlink_to_another_disk_survives_apply_and_rollback(tmp_path):
    """A trailing-slash exclude (rsync's directory-only form) does not match
    a symlink entry, so `data -> /mnt/drives` (a second disk mounted for the
    drives) was deleted outright by the old pattern; the fix drops the
    trailing slash so the symlink itself matches too."""
    here = tmp_path / "box"
    here.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "drives.txt").write_text("the department's own documents\n")
    (here / "data").symlink_to(elsewhere)
    src = tmp_path / "release"
    src.mkdir()
    (src / "newfile.txt").write_text("new\n")

    r = _run_update_copy(here, here / "data", src, here)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (here / "data").is_symlink(), "the symlink itself must survive, not just its target"
    assert (elsewhere / "drives.txt").read_text() == "the department's own documents\n"

    # And the same holds copying the other direction, as a rollback does.
    src2 = tmp_path / "previous"
    src2.mkdir()
    (src2 / "oldfile.txt").write_text("old\n")
    r2 = _run_update_copy(here, here / "data", src2, here)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert (here / "data").is_symlink()
    assert (elsewhere / "drives.txt").read_text() == "the department's own documents\n"


def _update_wrap_nufi_box(box_dir, doctor_exit):
    """Turn box_dir/nufi-box into a wrapper that answers `doctor` with
    doctor_exit and delegates every other verb to the real script (renamed
    nufi-box.real). Doctor's checks are real docker/curl calls inline in
    nufi-box's own case arm, not a lib function update.sh could call
    in-process, so a subprocess-level fake is the only way to control it."""
    (box_dir / "nufi-box").rename(box_dir / "nufi-box.real")
    wrapper = box_dir / "nufi-box"
    wrapper.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "doctor" ]; then\n'
        "  exit %d\n"
        "fi\n"
        'exec "$(dirname "$0")/nufi-box.real" "$@"\n' % doctor_exit
    )
    wrapper.chmod(0o755)


def _update_here(tmp_path):
    """A temp HERE: a full, working copy of this checkout (so lib/mesh.sh,
    Caddyfile, docker-compose.yml — everything update's real code touches —
    is there), plus its platform siblings beside it, doctor faked to pass,
    and the files an update must leave alone."""
    box_dir = tmp_path / "box"
    here = box_dir
    shutil.copytree(BOX, here, ignore=shutil.ignore_patterns("data", ".env", "tests"))
    _update_wrap_nufi_box(here, doctor_exit=0)
    (here / "data" / "drives").mkdir(parents=True)
    (here / "data" / "nufi-box-ca.crt").write_text("ca-dummy\n")
    (here / "data" / "x").write_text("data-x-content\n")
    (here / "caddy").mkdir(exist_ok=True)
    (here / "caddy" / "mesh.caddy").write_text("mesh-caddy-content\n")
    (here / "VERSION").write_text("pre-existing\n")
    # Not part of any fake release built below -- a real file an apply has
    # to actually delete, not a name that is merely absent because nothing
    # ever wrote it.
    (here / "OLD_FILE_NOT_IN_THE_RELEASE.txt").write_text("gone once applied\n")
    (here / ".env").write_text(
        "NUFI_DATA_DIR=%s/data\nBOX_NAME=nufi\nBOX_HOST=nufi.local\n"
        "POSTGRES_USER=nufi\nMONGO_USER=nufi\nMONGO_PASSWORD=testpw\n"
        "NUFI_MODEL=qwen2.5-14b\n" % here
    )
    platform = tmp_path / "platform"
    (platform / "scenarios" / "studio").mkdir(parents=True)
    (platform / "scenarios" / "run_box.py").write_text("# run_box\n")
    (platform / "scenarios" / "run.py").write_text("# run\n")
    (platform / "scenarios" / "studio" / "build_flows.py").write_text("v0\n")
    (platform / "adapters" / "nufi-cron").mkdir(parents=True)
    (platform / "adapters" / "nufi-cron" / "nufi_cron.py").write_text("v0\n")
    return here


def _update_fake_release(root, top, doctor_exit, version, install_exit=0):
    """Build root/<top>/deploy/{box,platform/...} the shape a codeload
    archive extracts to, with install-box.sh and doctor faked the same way
    _update_wrap_nufi_box fakes them in HERE — apply overwrites HERE's copies
    of both with whatever the archive holds, so the fakes have to travel with
    the archive too, not just live in HERE beforehand. Returns the tarball
    path curl's stub is told to hand back."""
    box = root / top / "deploy" / "box"
    shutil.copytree(BOX, box, ignore=shutil.ignore_patterns("data", ".env", "tests"))
    _update_wrap_nufi_box(box, doctor_exit)
    (box / "install-box.sh").write_text("#!/bin/sh\nexit %d\n" % install_exit)
    (box / "install-box.sh").chmod(0o755)
    (box / "VERSION").write_text("%s\n" % version)
    scenarios = root / top / "deploy" / "platform" / "scenarios"
    (scenarios / "studio").mkdir(parents=True)
    (scenarios / "run_box.py").write_text("# run_box\n")
    (scenarios / "run.py").write_text("# run\n")
    (scenarios / "studio" / "build_flows.py").write_text("%s\n" % version)
    cron = root / top / "deploy" / "platform" / "adapters" / "nufi-cron"
    cron.mkdir(parents=True)
    (cron / "nufi_cron.py").write_text("%s\n" % version)
    tar_path = root / (top + ".tar.gz")
    # COPYFILE_DISABLE: macOS's bsdtar otherwise writes an AppleDouble
    # "._<name>" sidecar for the top-level entry, which becomes the archive's
    # FIRST member — exactly the one update.sh's own top-directory read
    # (tarfile.open(...).next()) trusts. A real codeload tarball never has
    # one; this is purely an artifact of building the test fixture here.
    subprocess.run(["tar", "-czf", str(tar_path), "-C", str(root), top],
                   check=True, env=dict(os.environ, COPYFILE_DISABLE="1"))
    return tar_path


def _update_stub_path(tmp_path, images_json):
    """curl copies whichever tarball $STUB_TARBALL names, ignoring the real
    URL (NUFI_BOX_SOURCE is set by the caller to a stub URL so the GitHub API
    resolve is never attempted, and curl never sees a real network call);
    docker answers `compose config --services` and `compose images --format
    json` with fixed data and `image inspect` with a fixed digest, and logs
    every call it sees to $STUB_LOG. It does not answer `config --images` —
    update no longer calls it, on purpose (C2: that call prints a service's
    whole dependency closure, not just its own image)."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "curl").write_text(
        "#!/bin/sh\n"
        'prev=""; dest=""\n'
        'for a in "$@"; do [ "$prev" = "-o" ] && dest="$a"; prev="$a"; done\n'
        '[ -n "$dest" ] && cp "$STUB_TARBALL" "$dest"\n'
        "exit 0\n"
    )
    (bin_ / "curl").chmod(0o755)
    (bin_ / "docker").write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$STUB_LOG"\n'
        'if [ "$1" = "compose" ]; then\n'
        "  shift\n"
        '  while [ $# -gt 0 ]; do case "$1" in -f) shift 2 ;; *) break ;; esac; done\n'
        '  sub="$1"; [ $# -gt 0 ] && shift\n'
        '  case "$sub" in\n'
        '    config) case "$1" in --services) echo web ;; esac; exit 0 ;;\n'
        '    images) cat "$STUB_IMAGES_JSON"; exit 0 ;;\n'
        "    *) exit 0 ;;\n"
        "  esac\n"
        "fi\n"
        'case "$1" in\n'
        '  image) printf "%s\\n" "$STUB_REPO_DIGEST"; exit 0 ;;\n'
        '  tag) [ "$STUB_TAG_FAILS" = "1" ] && exit 1; exit 0 ;;\n'
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    (bin_ / "docker").chmod(0o755)
    images_json_path = tmp_path / "images.json"
    images_json_path.write_text(images_json)
    log = tmp_path / "calls.log"
    log.write_text("")
    return bin_, log, images_json_path


def _run_update(here, bin_, log, images_json_path, repo_digest, tarball, *extra_args):
    log.write_text("")
    # The stub dir wins for curl/docker; everything else (python3, rsync,
    # tar) falls back to wherever this host already has it -- a hardcoded
    # /usr/bin:/bin misses python3 on, say, the python:3.12-slim image the
    # GNU-tar gate runs this suite in, which ships it under /usr/local/bin.
    e = dict(os.environ, PATH="%s:%s" % (bin_, os.environ.get("PATH", "/usr/bin:/bin")),
             NUFI_BOX_FAKE_OS="Darwin",
             NUFI_BOX_SOURCE="https://stub.invalid/archive.tar.gz",
             STUB_TARBALL=str(tarball), STUB_LOG=str(log),
             STUB_IMAGES_JSON=str(images_json_path), STUB_REPO_DIGEST=repo_digest)
    e.pop("NUFI_BOX_DRY_RUN", None)
    e.pop("NUFI_BOX_ENV", None)
    return subprocess.run([BASH, str(here / "nufi-box"), "update", "--yes", *extra_args],
                          cwd=here, env=e, capture_output=True, text=True)


def _run_rollback(here, bin_, log, tag_fails=False):
    """Standalone `nufi-box update --rollback` against a HERE that already
    has a completed .previous/ (a prior _run_update call), independent of
    another update having just failed."""
    log.write_text("")
    e = dict(os.environ, PATH="%s:%s" % (bin_, os.environ.get("PATH", "/usr/bin:/bin")),
             NUFI_BOX_FAKE_OS="Darwin", STUB_LOG=str(log),
             STUB_TAG_FAILS="1" if tag_fails else "0")
    e.pop("NUFI_BOX_DRY_RUN", None)
    e.pop("NUFI_BOX_ENV", None)
    return subprocess.run([BASH, str(here / "nufi-box"), "update", "--rollback"],
                          cwd=here, env=e, capture_output=True, text=True)


def test_update_applies_the_release_snapshots_digests_and_rolls_back_on_a_failed_doctor(tmp_path):
    """One update that succeeds, then one that does not — the shape a box
    actually sees (a good release, then a bad one), and the only way to prove
    a rollback puts back the LAST GOOD state, not just the box's original
    install."""
    here = _update_here(tmp_path)
    bin_, log, images_json_path = _update_stub_path(
        tmp_path, '[{"Repository":"ghcr.io/dudaji-vn/nufichat","Tag":"main","ID":"sha256:cfgaaa"}]')

    # A good release: doctor passes, nothing rolls back.
    good_root = tmp_path / "repo-good"; good_root.mkdir()
    good_tar = _update_fake_release(good_root, "nufi-app-goodsha", doctor_exit=0, version="good-v1")
    r = _run_update(here, bin_, log, images_json_path,
                    "ghcr.io/dudaji-vn/nufichat@sha256:realdigest111", good_tar)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Updated to main (sha unknown)" in r.stdout, r.stdout

    # (i) .env, data/x, caddy/mesh.caddy are untouched by an update.
    assert (here / ".env").read_text().startswith("NUFI_DATA_DIR=%s/data" % here)
    assert (here / "data" / "x").read_text() == "data-x-content\n"
    assert (here / "caddy" / "mesh.caddy").read_text() == "mesh-caddy-content\n"

    # (ii) the new release's content is here (I7: content, not just presence),
    # and a file that was here but is not in the release is gone -- present
    # in .previous/tree, which the next assertions cover.
    assert (here / "VERSION").read_text() == "good-v1\n"
    assert not (here / "OLD_FILE_NOT_IN_THE_RELEASE.txt").exists()
    assert (here / ".previous" / "tree" / "OLD_FILE_NOT_IN_THE_RELEASE.txt").read_text() == "gone once applied\n"

    # (iii) images.txt names the digest the stub answered and the tag to
    # re-tag it as (C2: recorded at snapshot time, three columns).
    images_txt = (here / ".previous" / "images.txt").read_text()
    assert images_txt.strip() == \
        "web ghcr.io/dudaji-vn/nufichat@sha256:realdigest111 ghcr.io/dudaji-vn/nufichat:main"
    assert (here / ".previous" / "COMPLETE").exists()

    # I6: the routine builder and adapter are snapshotted and applied too.
    platform = tmp_path / "platform"
    assert (platform / "scenarios" / "studio" / "build_flows.py").read_text() == "good-v1\n"
    assert (platform / "scenarios" / "run_box.py").exists()
    assert (platform / "adapters" / "nufi-cron" / "nufi_cron.py").read_text() == "good-v1\n"
    assert (here / ".previous" / "platform" / "scenarios" / "studio" / "build_flows.py").read_text() == "v0\n"

    # I4: updated-from lives at NUFI_DATA_DIR, not .previous, and is not
    # touched by the next update's snapshot/apply.
    assert (here / "data" / "updated-from").exists()
    assert not (here / ".previous" / "updated-from").exists()

    # A bad release: doctor fails, update rolls back to what the good release left.
    bad_root = tmp_path / "repo-bad"; bad_root.mkdir()
    bad_tar = _update_fake_release(bad_root, "nufi-app-badsha", doctor_exit=1, version="bad-v2")
    r = _run_update(here, bin_, log, images_json_path,
                    "ghcr.io/dudaji-vn/nufichat@sha256:realdigest222", bad_tar)
    assert r.returncode == 1
    assert "rolling back" in r.stdout
    assert "Rolled back" in r.stdout

    # (iv) the digest snapshotted this run was re-tagged, the stack was
    # brought back up, and the OLD content (the good release's, not just
    # "a" file) is back.
    calls = log.read_text()
    assert "tag ghcr.io/dudaji-vn/nufichat@sha256:realdigest222 ghcr.io/dudaji-vn/nufichat:main" in calls
    assert "up -d" in calls
    assert (here / "VERSION").read_text() == "good-v1\n"
    assert (platform / "scenarios" / "studio" / "build_flows.py").read_text() == "good-v1\n"

    # I4: a rollback clears the record — the box is no longer running what
    # updated-from said it was.
    assert not (here / "data" / "updated-from").exists()


def test_update_rolls_back_when_the_installer_itself_fails(tmp_path):
    """C5: a failing install-box.sh (or a failing apply copy) must not leave
    the box half-applied with no hint. First establishes a good baseline the
    same way the test above does, then a release whose installer fails
    outright — no doctor check is even reached."""
    here = _update_here(tmp_path)
    bin_, log, images_json_path = _update_stub_path(
        tmp_path, '[{"Repository":"ghcr.io/dudaji-vn/nufichat","Tag":"main","ID":"sha256:cfgaaa"}]')

    good_root = tmp_path / "repo-good"; good_root.mkdir()
    good_tar = _update_fake_release(good_root, "nufi-app-goodsha", doctor_exit=0, version="good-v1")
    r = _run_update(here, bin_, log, images_json_path,
                    "ghcr.io/dudaji-vn/nufichat@sha256:realdigest111", good_tar)
    assert r.returncode == 0, r.stdout + r.stderr

    broken_root = tmp_path / "repo-broken"; broken_root.mkdir()
    broken_tar = _update_fake_release(broken_root, "nufi-app-brokensha", doctor_exit=0,
                                      version="broken-v3", install_exit=1)
    r = _run_update(here, bin_, log, images_json_path,
                    "ghcr.io/dudaji-vn/nufichat@sha256:realdigest333", broken_tar)
    assert r.returncode == 1
    assert "installer failed" in r.stdout
    assert "rolling back" in r.stdout
    assert "Rolled back" in r.stdout

    calls = log.read_text()
    assert "up -d" in calls
    assert (here / "VERSION").read_text() == "good-v1\n"


def test_rollback_survives_a_re_tag_that_fails(tmp_path):
    """A `docker tag` failure (the image already pruned between the update
    and a stand-alone --rollback) used to be a bare statement inside a
    `while read` loop -- set -e killed the rollback right there, before
    mesh_caddy_refresh, `up -d`, or the doctor recheck ever ran. One failing
    service must not take the rest of the rollback down with it."""
    here = _update_here(tmp_path)
    bin_, log, images_json_path = _update_stub_path(
        tmp_path, '[{"Repository":"ghcr.io/dudaji-vn/nufichat","Tag":"main","ID":"sha256:cfgaaa"}]')

    good_root = tmp_path / "repo-good"; good_root.mkdir()
    good_tar = _update_fake_release(good_root, "nufi-app-goodsha", doctor_exit=0, version="good-v1")
    r = _run_update(here, bin_, log, images_json_path,
                    "ghcr.io/dudaji-vn/nufichat@sha256:realdigest111", good_tar)
    assert r.returncode == 0, r.stdout + r.stderr

    r = _run_rollback(here, bin_, log, tag_fails=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "could not re-tag" in r.stdout
    assert "Rolled back" in r.stdout
    calls = log.read_text()
    assert "up -d" in calls


def test_dry_run_rollback_does_not_delete_the_real_updated_from_record(tmp_path):
    """`rm -f` on updated-from was a bare statement, not `run`-gated -- a
    --dry-run rollback (meant to only print a plan) deleted the real record
    of what the box last updated to."""
    here = _update_here(tmp_path)
    bin_, log, images_json_path = _update_stub_path(
        tmp_path, '[{"Repository":"ghcr.io/dudaji-vn/nufichat","Tag":"main","ID":"sha256:cfgaaa"}]')

    good_root = tmp_path / "repo-good"; good_root.mkdir()
    good_tar = _update_fake_release(good_root, "nufi-app-goodsha", doctor_exit=0, version="good-v1")
    r = _run_update(here, bin_, log, images_json_path,
                    "ghcr.io/dudaji-vn/nufichat@sha256:realdigest111", good_tar)
    assert r.returncode == 0, r.stdout + r.stderr
    updated_from = here / "data" / "updated-from"
    assert updated_from.exists()
    before = updated_from.read_text()

    e = dict(os.environ, NUFI_BOX_DRY_RUN="1")
    e.pop("NUFI_BOX_ENV", None)
    r = subprocess.run([BASH, str(here / "nufi-box"), "update", "--rollback"],
                       cwd=here, env=e, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert updated_from.exists(), "a --dry-run must not delete the real record"
    assert updated_from.read_text() == before
