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
