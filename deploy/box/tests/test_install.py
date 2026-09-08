"""install-box.sh --dry-run must plan the right steps for each OS without touching anything."""
import os
import pathlib
import subprocess
import tempfile

BOX = pathlib.Path(__file__).resolve().parents[1]
BASH = "/bin/bash"   # macOS ships 3.2 here; the script must run under it


def install(*flags, **env):
    """Run the installer in dry-run mode and hand back the completed process.

    NUFI_BOX_ENV points at a path that does not exist unless the caller says
    otherwise: on a machine where the box is actually installed, deploy/box/.env
    is right there, and the installer would reuse its answers and secrets — the
    plan under test would be that box's, not the one the test described.
    """
    with tempfile.TemporaryDirectory() as tmp:
        env.setdefault("NUFI_BOX_ENV", str(pathlib.Path(tmp) / "absent.env"))
        e = dict(os.environ, NUFI_BOX_DRY_RUN="1", **env)
        return subprocess.run([BASH, str(BOX / "install-box.sh"), "--dry-run", "--yes", *flags],
                              cwd=BOX, env=e, capture_output=True, text=True)


def dry(*flags, **env):
    r = install(*flags, **env)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_macos_plan_uses_native_ollama_and_file_sharing():
    out = dry(NUFI_BOX_FAKE_OS="Darwin", BOX_NAME="demo", DEPARTMENTS="legal,hr")
    assert "INFERENCE_PROFILE=ollama" in out
    assert "INFERENCE_BASE_URL=http://host.docker.internal:11434/v1" in out
    assert "--profile linux" not in out
    assert "File Sharing" in out
    assert "drives/legal" in out and "drives/hr" in out
    assert "BOX_HOST=demo.local" in out


def test_linux_gpu_plan_uses_ollama_container_and_samba():
    out = dry(NUFI_BOX_FAKE_OS="Linux", NUFI_BOX_FAKE_NVIDIA="1", DEPARTMENTS="legal")
    assert "INFERENCE_PROFILE=ollama-docker" in out
    assert "--profile linux" in out
    assert "NVIDIA_VISIBLE_DEVICES=all" in out
    assert 'SAMBA_VOLUME_CONFIG_legal="[legal]; path=/shares/legal;' in out
    assert "--profile gpu" in out
    assert "docker-compose.gpu.yml" in out


def test_linux_cpu_plan_has_no_gpu_layer():
    # No NUFI_BOX_FAKE_NVIDIA: has_nvidia() is false (unless a real nvidia-smi is on PATH,
    # which a CPU host doesn't have). Deliberately doesn't assert on INFERENCE_PROFILE — that
    # choice also depends on whether `ollama` happens to be on the test runner's PATH, which
    # isn't what this test is about.
    out = dry(NUFI_BOX_FAKE_OS="Linux", DEPARTMENTS="legal")
    assert "--profile linux" in out
    assert "NVIDIA_VISIBLE_DEVICES=" in out
    assert "NVIDIA_VISIBLE_DEVICES=all" not in out
    assert "--profile gpu" not in out
    assert "docker-compose.gpu.yml" not in out


def test_secrets_are_generated_not_placeholders():
    out = dry(NUFI_BOX_FAKE_OS="Linux")
    assert "replace-me" not in out
    assert "LANGFLOW_SECRET_KEY=" in out
    for line in out.splitlines():
        if line.startswith("LANGFLOW_SECRET_KEY="):
            key = line.split("=", 1)[1]
            assert len(key) == 44 and key.endswith("="), key


def test_dry_run_creates_nothing():
    before = set(p.name for p in BOX.iterdir())
    with tempfile.TemporaryDirectory() as tmp:
        envfile = pathlib.Path(tmp) / "would-be.env"
        dry(NUFI_BOX_FAKE_OS="Linux", NUFI_BOX_ENV=str(envfile))
        assert not envfile.exists()
    after = set(p.name for p in BOX.iterdir())
    assert before == after


def test_department_names_with_dashes_get_sanitized_env_keys():
    out = dry(NUFI_BOX_FAKE_OS="Linux", DEPARTMENTS="legal,back-office")
    assert 'SAMBA_VOLUME_CONFIG_back_office="[back-office]; path=/shares/back-office;' in out


def test_rerun_keeps_previous_answers_but_explicit_overrides_win():
    with tempfile.TemporaryDirectory() as tmp:
        envfile = pathlib.Path(tmp) / "existing.env"
        original = "BOX_NAME=oldbox\nDEPARTMENTS=legal\nJWT_SECRET=keepme-keepme\n"
        envfile.write_text(original)
        out = dry(NUFI_BOX_FAKE_OS="Linux", NUFI_BOX_ENV=str(envfile), DEPARTMENTS="legal,sales")
        # explicit override wins over what is already on disk
        assert "DEPARTMENTS=legal,sales" in out
        # not overridden by the caller: kept from the existing file
        assert "BOX_NAME=oldbox" in out
        assert "JWT_SECRET=keepme-keepme" in out
        # the newly-added department still gets rendered
        assert 'SAMBA_VOLUME_CONFIG_sales="[sales]; path=/shares/sales;' in out
        # dry-run must not touch the env file it read
        assert envfile.read_text() == original


def test_no_pull_skips_the_pull_but_still_starts_the_stack():
    out = dry("--no-pull", NUFI_BOX_FAKE_OS="Darwin")
    assert "compose -f docker-compose.yml pull" not in out
    assert "--no-pull: using the images already on this machine" in out
    assert "compose -f docker-compose.yml up -d" in out


def test_emulate_amd64_layers_the_platform_file_and_records_it_in_env():
    out = dry("--emulate-amd64", NUFI_BOX_FAKE_OS="Darwin")
    assert "-f docker-compose.yml -f docker-compose.emulate.yml up -d" in out
    # written to .env so `nufi-box up` keeps the platform on day two
    assert "NUFI_EMULATE_AMD64=1" in out
    # without the flag the layer stays out of the way
    plain = dry(NUFI_BOX_FAKE_OS="Darwin")
    assert "docker-compose.emulate.yml" not in plain
    assert "NUFI_EMULATE_AMD64=0" in plain


def test_no_trust_prints_the_manual_step_instead_of_touching_the_keychain():
    out = dry("--no-trust", NUFI_BOX_FAKE_OS="Darwin")
    assert "Not touching the login keychain" in out
    assert "security add-trusted-cert -r trustRoot" in out


def test_bare_src_says_what_is_missing_instead_of_exiting_silently():
    r = install("--src")
    assert r.returncode == 1, r.stdout
    assert "--src needs a directory" in r.stderr
    r = install("--src=")
    assert r.returncode == 1, r.stdout
    assert "--src needs a directory" in r.stderr


def test_extra_compose_files_are_layered_last_and_must_exist(tmp_path):
    extra = tmp_path / "local-ports.yml"
    extra.write_text("services: {}\n")
    out = dry("--emulate-amd64", NUFI_BOX_FAKE_OS="Darwin",
              NUFI_BOX_COMPOSE_EXTRA=str(extra))
    assert f"-f docker-compose.emulate.yml -f {extra} up -d" in out
    r = install(NUFI_BOX_FAKE_OS="Darwin", NUFI_BOX_COMPOSE_EXTRA="/nope/missing.yml")
    assert r.returncode == 1
    assert "no such file: /nope/missing.yml" in r.stderr


def test_ingest_runs_as_the_admin_by_default():
    """Whoever creates a department team owns it, and only the daemon ever
    creates one — so a daemon on its own bot account leaves the admin with no
    teams and no agents on a fresh box, and no way in (membership is
    invite-and-accept only). The default must be the admin."""
    out = dry(NUFI_BOX_FAKE_OS="Darwin", ADMIN_EMAIL="sun@dudaji.com")
    assert "INGEST_EMAIL=sun@dudaji.com" in out
    # same account => same password, and no second user created for it
    admin_pw = next(l.split("=", 1)[1] for l in out.splitlines() if l.startswith("ADMIN_PASSWORD="))
    assert f"INGEST_PASSWORD={admin_pw}" in out
    assert "Ingest bot" not in out
    assert "no separate bot account" in out


def test_an_explicit_ingest_email_still_gets_its_own_bot_account():
    out = dry(NUFI_BOX_FAKE_OS="Darwin", ADMIN_EMAIL="sun@dudaji.com",
              INGEST_EMAIL="bot@x")
    assert "INGEST_EMAIL=bot@x" in out
    admin_pw = next(l.split("=", 1)[1] for l in out.splitlines() if l.startswith("ADMIN_PASSWORD="))
    ingest_pw = next(l.split("=", 1)[1] for l in out.splitlines() if l.startswith("INGEST_PASSWORD="))
    assert ingest_pw and ingest_pw != admin_pw
    assert "create-user -- bot@x Ingest bot ingest" in out
