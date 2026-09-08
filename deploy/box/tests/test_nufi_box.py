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
