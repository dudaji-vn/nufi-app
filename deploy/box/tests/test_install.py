"""install-box.sh --dry-run must plan the right steps for each OS without touching anything."""
import os
import pathlib
import subprocess

BOX = pathlib.Path(__file__).resolve().parents[1]
BASH = "/bin/bash"   # macOS ships 3.2 here; the script must run under it


def dry(**env):
    e = dict(os.environ, NUFI_BOX_DRY_RUN="1", **env)
    r = subprocess.run([BASH, str(BOX / "install-box.sh"), "--dry-run", "--yes"],
                       cwd=BOX, env=e, capture_output=True, text=True)
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
    dry(NUFI_BOX_FAKE_OS="Linux")
    after = set(p.name for p in BOX.iterdir())
    assert before == after
    assert not (BOX / ".env").exists()


def test_department_names_with_dashes_get_sanitized_env_keys():
    out = dry(NUFI_BOX_FAKE_OS="Linux", DEPARTMENTS="legal,back-office")
    assert 'SAMBA_VOLUME_CONFIG_back_office="[back-office]; path=/shares/back-office;' in out
