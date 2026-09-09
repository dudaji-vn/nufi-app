"""install-box.sh --dry-run must plan the right steps for each OS without touching anything."""
import os
import pathlib
import re
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


def test_registry_flag_writes_nufi_registry_and_default_is_ghcr():
    out = dry("--registry", "10.0.0.5:5000", NUFI_BOX_FAKE_OS="Linux")
    assert "NUFI_REGISTRY=10.0.0.5:5000" in out
    plain = dry(NUFI_BOX_FAKE_OS="Linux")
    assert "NUFI_REGISTRY=ghcr.io/dudaji-vn" in plain


def test_registry_override_wins_over_env_on_a_rerun():
    with tempfile.TemporaryDirectory() as tmp:
        envfile = pathlib.Path(tmp) / "box.env"
        envfile.write_text("BOX_NAME=demo\nNUFI_REGISTRY=192.168.1.26:5000\n")
        out = dry(NUFI_BOX_FAKE_OS="Linux", NUFI_BOX_ENV=str(envfile),
                   BOX_NAME="demo", NUFI_REGISTRY="10.0.0.5:5000")
        assert "NUFI_REGISTRY=10.0.0.5:5000" in out
        # not overridden: a re-run without --registry keeps the .env value
        kept = dry(NUFI_BOX_FAKE_OS="Linux", NUFI_BOX_ENV=str(envfile), BOX_NAME="demo")
        assert "NUFI_REGISTRY=192.168.1.26:5000" in kept


def test_registry_that_looks_like_host_port_gets_marked_insecure_on_linux():
    out = dry("--registry", "10.0.0.5:5000", NUFI_BOX_FAKE_OS="Linux")
    assert "/etc/docker/daemon.json" in out
    assert "insecure-registries" in out
    assert "10.0.0.5:5000" in out
    assert "sudo systemctl restart docker" in out


def test_registry_on_macos_only_prints_the_docker_desktop_instruction():
    out = dry("--registry", "10.0.0.5:5000", NUFI_BOX_FAKE_OS="Darwin")
    assert "Docker Desktop" in out
    assert "insecure-registries" in out
    assert "/etc/docker/daemon.json" not in out


def test_default_registry_is_not_marked_insecure():
    out = dry(NUFI_BOX_FAKE_OS="Linux")
    assert "insecure-registries" not in out
    assert "/etc/docker/daemon.json" not in out


def test_registry_with_https_scheme_is_not_marked_insecure():
    out = dry("--registry", "https://10.0.0.5:5000", NUFI_BOX_FAKE_OS="Linux")
    assert "insecure-registries" not in out


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


def _installer_source():
    """install-box.sh with backslash-continuations joined, so a guard written on
    the next line still reads as one command."""
    return re.sub(r"\\\n\s*", " ", (BOX / "install-box.sh").read_text())


def test_the_steps_that_fail_on_a_re_run_or_a_locked_down_host_only_warn():
    """Three calls in this installer fail on machines it is documented to
    support, and `set -e` turned each of them into a half-finished install:

      * `npm run create-user` exits 1 when the address already exists
        (apps/chat/config/create-user.js -> silentExit(1)), which is every
        re-run;
      * `ln -sf ... /usr/local/bin` fails for a non-root user on Ubuntu;
      * `ollama pull` fails on a slow or offline network.

    A dry run cannot show this — `run` only echoes the command, so the `||`
    never executes — so the shape is pinned in the source instead. Crude, but
    it is the behaviour, and it is the behaviour that regressed.
    """
    src = _installer_source()
    assert re.search(r"npm run create-user\b[^\n]*\|\|\s*warn", src), \
        "create-user must not abort the installer when the account exists"
    assert re.search(r"run ln -sf\b[^\n]*\|\|\s*warn", src), \
        "the /usr/local/bin symlink must not abort the installer"
    pulls = [ln for ln in src.splitlines()
             if "ollama pull" in ln and not ln.lstrip().startswith("#")]
    assert len(pulls) >= 3, pulls          # native, in-container, and the fallback arm
    for ln in pulls:
        assert re.search(r"\|\|\s*warn[^\n]*\$(INFERENCE_MODEL|EMBEDDINGS_MODEL)", ln), \
            f"a failed pull must warn and name the model: {ln}"


def test_a_second_run_plans_exactly_what_the_first_one_did():
    """Re-running install-box.sh on an installed box is documented as safe, and
    that only means anything if the second run plans the same box: same
    secrets, same compose invocation, same accounts, same banner.

    A dry run prints the .env it would write instead of writing it, so the
    first run's own rendering is handed back as the file an installed box would
    already have — which is exactly the state a re-run starts from.
    """
    with tempfile.TemporaryDirectory() as tmp:
        envfile = pathlib.Path(tmp) / "box.env"
        first = dry(NUFI_BOX_FAKE_OS="Darwin", NUFI_BOX_ENV=str(envfile),
                    BOX_NAME="demo", DEPARTMENTS="legal,hr")
        # render_env's output (what DRY=1 prints instead of writing to disk) is
        # exactly the .env content, verbatim — including the OIDC key's real
        # embedded newlines. It sits between the "Writing .env" and "Rendering
        # litellm" banners, so slice it out rather than filtering line-by-line
        # (a per-line KEY=VALUE filter would truncate a multi-line PEM).
        start = first.index("Writing .env\n") + len("Writing .env\n")
        end = first.index("==>\x1b[0m Rendering litellm", start)
        end = first.rindex("\n", start, end)
        envfile.write_text(first[start:end] + "\n")

        second = dry(NUFI_BOX_FAKE_OS="Darwin", NUFI_BOX_ENV=str(envfile),
                     BOX_NAME="demo", DEPARTMENTS="legal,hr")
        third = dry(NUFI_BOX_FAKE_OS="Darwin", NUFI_BOX_ENV=str(envfile),
                    BOX_NAME="demo", DEPARTMENTS="legal,hr")
        assert second == third

        # not vacuous: the run really does reach the steps that used to abort,
        # and it kept the secrets rather than minting new ones
        assert "create-user -- admin@demo.local" in second
        assert 'NuFi box "demo" is up.' in second
        assert "restart nufi-ingest" in second
        jwt = next(ln for ln in first.splitlines() if ln.startswith("JWT_SECRET="))
        assert jwt in second


def _oidc_pem_block(out):
    """Pull the (possibly multi-line) value of OIDC_PRIVATE_KEY_PEM="..." out of
    a rendered .env. The PEM itself never contains a double quote, so the first
    one after the opening quote is always the closing one."""
    m = re.search(r'OIDC_PRIVATE_KEY_PEM="([\s\S]*?)"', out)
    assert m, "OIDC_PRIVATE_KEY_PEM not found in rendered .env"
    return m.group(1)


def test_oidc_key_is_stored_as_real_multiline_pem_not_literal_backslash_n():
    # Compose does not expand \n inside a double-quoted .env value — verified
    # with `docker compose config` on 2.39.2: X="a\nb" renders as the four
    # characters a\nb, while a real multi-line double-quoted value renders
    # with a real newline. The installer must write the second form.
    out = dry(NUFI_BOX_FAKE_OS="Darwin")
    pem = _oidc_pem_block(out)
    lines = pem.splitlines()
    assert len(lines) > 1, "PEM must span multiple real lines"
    assert lines[0] == "-----BEGIN PRIVATE KEY-----"
    assert "\\n" not in pem, "no literal backslash-n allowed in the PEM"


def test_old_one_line_oidc_key_is_healed_on_rerun_other_secrets_kept():
    with tempfile.TemporaryDirectory() as tmp:
        envfile = pathlib.Path(tmp) / "existing.env"
        old_pem = "-----BEGIN PRIVATE KEY-----\\nAAAA\\n-----END PRIVATE KEY-----\\n"
        envfile.write_text(
            "JWT_SECRET=keepme-keepme\n"
            f'OIDC_PRIVATE_KEY_PEM="{old_pem}"\n'
        )
        r = install(NUFI_BOX_FAKE_OS="Darwin", NUFI_BOX_ENV=str(envfile))
        assert r.returncode == 0, r.stderr
        assert "regenerated the console signing key" in r.stderr
        assert "old one was stored on one line" in r.stderr

        out = r.stdout
        assert "JWT_SECRET=keepme-keepme" in out  # untouched secret survives

        new_pem = _oidc_pem_block(out)
        assert new_pem != old_pem
        assert len(new_pem.splitlines()) > 1
        assert "\\n" not in new_pem


def test_jwks_check_is_in_the_plan():
    out = dry(NUFI_BOX_FAKE_OS="Darwin")
    assert "curl -fsk https://localhost:3001/.well-known/jwks.json" in out


# --- a blank machine: Docker installed by us, group not active yet ------------
# These two are the only tests that run the installer for real (not --dry-run).
# They stop inside the prerequisites block, before anything is written, because
# a stub PATH stands in for curl / sudo / sg / docker.

def _blank_linux_box(tmp, daemon="denied", groups="sun docker"):
    """A PATH where docker is absent until `curl … get.docker.com | sh` runs,
    and the docker it then installs cannot reach the daemon — the state a real
    `usermod -aG docker` leaves this shell in."""
    bin_ = pathlib.Path(tmp) / "bin"
    bin_.mkdir()

    def stub(name, body):
        p = bin_ / name
        p.write_text("#!/bin/sh\n" + body)
        p.chmod(0o755)
        return p

    # What get.docker.com's script does, in miniature: put `docker` on PATH.
    (bin_ / "docker.installer").write_text(f"cp {bin_}/docker.new {bin_}/docker\n")
    stub("docker.new",
         'case "$1 $2" in\n'
         '  "compose version") exit 0 ;;\n'          # never opens the socket
         + ('  *) echo "permission denied while trying to connect to the docker API '
            'at unix:///var/run/docker.sock" >&2; exit 1 ;;\n'
            if daemon == "denied" else '  *) exit 0 ;;\n')
         + "esac\n")
    stub("curl", f'case "$*" in *get.docker.com*) cat {bin_}/docker.installer ;; esac\nexit 0\n')
    stub("sudo", 'exit 0\n')
    stub("sg", f'echo "$@" > {bin_.parent}/sg.args\nexit 0\n')
    # `id -nG <user>` reads the group database, which usermod has just updated —
    # the whole point is that the running session's own groups have not.
    stub("id", f'echo "{groups}"\n')
    return bin_


def _install_on_blank_linux(tmp, **env):
    bin_ = _blank_linux_box(tmp, daemon=env.pop("daemon", "denied"),
                            groups=env.pop("groups", "sun docker"))
    e = dict(os.environ,
             PATH=f"{bin_}:/usr/bin:/bin",
             NUFI_BOX_FAKE_OS="Linux",
             NUFI_BOX_ENV=str(pathlib.Path(tmp) / "absent.env"),
             **env)
    r = subprocess.run([BASH, str(BOX / "install-box.sh"), "--yes", "--registry", "10.0.0.5:5000"],
                       cwd=BOX, env=e, capture_output=True, text=True)
    return r, pathlib.Path(tmp) / "sg.args"


def test_fresh_docker_install_re_execs_inside_the_docker_group():
    # usermod -aG docker only applies to the next login, so the shell that just
    # installed Docker cannot reach the socket. Without the re-exec the install
    # ran on for minutes and then died at `docker compose pull`.
    with tempfile.TemporaryDirectory() as tmp:
        r, sg_args = _install_on_blank_linux(tmp)
        assert r.returncode == 0, r.stderr
        assert "Re-running inside the new docker group" in r.stdout
        assert sg_args.exists(), "the installer never re-execed"
        args = sg_args.read_text()
        assert args.startswith("docker -c ")
        assert "install-box.sh" in args
        assert "--yes" in args and "--registry 10.0.0.5:5000" in args
        assert "Writing .env" not in r.stdout, "re-exec must replace this run, not continue it"


def test_the_re_exec_happens_once_then_says_what_to_do():
    # Second time round (NUFI_BOX_REEXEC=1) the group really should be active.
    # If it still is not, say so here rather than at the image pull.
    with tempfile.TemporaryDirectory() as tmp:
        r, sg_args = _install_on_blank_linux(tmp, NUFI_BOX_REEXEC="1")
        assert r.returncode != 0
        assert not sg_args.exists(), "must not re-exec twice"
        assert "cannot reach the Docker daemon" in r.stderr
        assert "newgrp docker" in r.stderr


def test_a_failing_image_pull_is_retried_three_times_then_explained():
    # A blank-VM install died two minutes in when one third-party image hit a
    # TLS handshake timeout at ghcr.io — every other image was already down.
    # The whole box dir is copied so the run writes its .env, config.yaml and
    # drive folders into the temp copy, not into the checkout.
    import shutil
    with tempfile.TemporaryDirectory() as tmp:
        box = pathlib.Path(tmp) / "box"
        shutil.copytree(BOX, box, ignore=shutil.ignore_patterns("data", ".env", "tests"))
        bin_ = pathlib.Path(tmp) / "bin"
        bin_.mkdir()
        tries = pathlib.Path(tmp) / "pull.attempts"
        docker = bin_ / "docker"
        # `docker compose -f … --profile linux pull`: the verb is the LAST word,
        # not $2.
        docker.write_text(
            "#!/bin/sh\n"
            'case "$*" in\n'
            f'  *" pull") echo x >> {tries}; exit 1 ;;\n'
            '  *) exit 0 ;;\n'
            "esac\n")
        docker.chmod(0o755)
        for name in ("sudo", "curl"):
            p = bin_ / name
            p.write_text("#!/bin/sh\nexit 0\n")
            p.chmod(0o755)
        e = dict(os.environ, PATH=f"{bin_}:/usr/bin:/bin", NUFI_BOX_FAKE_OS="Linux",
                 NUFI_DATA_DIR=str(pathlib.Path(tmp) / "data"),
                 NUFI_BOX_ENV=str(box / ".env"))
        r = subprocess.run([BASH, str(box / "install-box.sh"), "--yes"],
                           cwd=box, env=e, capture_output=True, text=True)
        assert r.returncode != 0
        assert tries.read_text().count("x") == 3, "the pull must be tried three times"
        assert "could not pull the images after 3 attempts" in r.stderr


def test_a_session_older_than_the_group_is_rescued_on_a_re_run_too():
    # Docker is already installed (no install branch runs), but the shell
    # predates the docker group — a re-run over an SSH session that was open
    # when the box was installed. Lima's shared connection does exactly this,
    # and the re-run died on the spot until the rescue moved out of the
    # "we just installed Docker" branch.
    with tempfile.TemporaryDirectory() as tmp:
        bin_ = _blank_linux_box(tmp)
        (bin_ / "docker").write_text(
            "#!/bin/sh\n"
            'case "$1 $2" in\n'
            '  "compose version") exit 0 ;;\n'
            '  *) echo "permission denied" >&2; exit 1 ;;\n'
            "esac\n")
        (bin_ / "docker").chmod(0o755)
        e = dict(os.environ, PATH=f"{bin_}:/usr/bin:/bin", NUFI_BOX_FAKE_OS="Linux",
                 NUFI_BOX_ENV=str(pathlib.Path(tmp) / "absent.env"))
        r = subprocess.run([BASH, str(BOX / "install-box.sh"), "--yes"],
                           cwd=BOX, env=e, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert "Re-running inside the new docker group" in r.stdout
        assert (pathlib.Path(tmp) / "sg.args").exists()


def test_a_user_who_is_not_in_the_docker_group_is_told_not_re_execed():
    # sg would just fail; say what to do instead.
    with tempfile.TemporaryDirectory() as tmp:
        r, sg_args = _install_on_blank_linux(tmp, groups="sun")
        assert r.returncode != 0
        assert not sg_args.exists()
        assert "cannot reach the Docker daemon" in r.stderr
