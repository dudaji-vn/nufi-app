"""Renders deploy/box compose files and asserts the topology rules.

No Docker daemon needed: `docker compose config` only needs the CLI.
Run: cd deploy/box && python3 -m pytest tests -q
"""
import json
import os
import pathlib
import re
import subprocess

import pytest

BOX = pathlib.Path(__file__).resolve().parents[1]
CORE = {"caddy", "postgres", "mongodb", "litellm-proxy", "librechat", "rag_api"}
SSO = {"console", "admin-panel", "studio"}
LINUX = {"ollama", "samba"}


def render(*files, profiles=()):
    env = dict(os.environ)
    env.update({
        "BOX_HOST": "nufi.local", "BOX_IP": "192.168.1.10", "BOX_NAME": "nufi",
        "NUFI_DATA_DIR": "./data", "NUFI_MODEL": "qwen2.5-7b",
        "INFERENCE_MODEL": "qwen2.5:7b", "INFERENCE_BASE_URL": "http://host.docker.internal:11434/v1",
        "INFERENCE_API_KEY": "ollama", "OLLAMA_BASE_URL": "http://host.docker.internal:11434",
        "EMBEDDINGS_MODEL": "bge-m3", "JWT_SECRET": "x", "JWT_REFRESH_SECRET": "x",
        "CREDS_KEY": "x", "CREDS_IV": "x", "LITELLM_MASTER_KEY": "sk-x", "LITELLM_SALT_KEY": "x",
        "POSTGRES_PASSWORD": "x", "MONGO_PASSWORD": "x", "ADMIN_EMAIL": "a@b.c",
        "INGEST_EMAIL": "ingest@box", "INGEST_PASSWORD": "x", "DEPARTMENTS": "legal,hr",
        "OIDC_PRIVATE_KEY_PEM": "x", "LANGFLOW_SECRET_KEY": "x", "STUDIO_SUPERUSER_PASSWORD": "x",
        "SAMBA_PASSWORD": "x", "ADMIN_SESSION_SECRET": "x" * 40,
        "NUFI_RAG_IMAGE": "ghcr.io/danny-avila/librechat-rag-api-dev-lite@sha256:0000000000000000000000000000000000000000000000000000000000000000",
        "NUFI_CHAT_TAG": "main", "NUFI_CONSOLE_TAG": "main", "NUFI_ADMIN_TAG": "main",
        "NUFI_STUDIO_TAG": "box-main", "NUFI_LITELLM_TAG": "main", "NUFI_INGEST_TAG": "main",
    })
    cmd = ["docker", "compose", "--project-directory", str(BOX)]
    for f in files or ("docker-compose.yml",):
        cmd += ["-f", str(BOX / f)]
    for p in profiles:
        cmd += ["--profile", p]
    cmd += ["config", "--format", "json"]
    out = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_core_services_present_and_named():
    cfg = render()
    assert cfg["name"] == "nufi-box"
    assert CORE <= set(cfg["services"])


def test_every_service_follows_the_house_rules():
    cfg = render("docker-compose.yml", "docker-compose.linux.yml", "docker-compose.gpu.yml",
                 profiles=("linux", "gpu"))
    for name, svc in cfg["services"].items():
        assert svc.get("restart") == "unless-stopped", name
        assert "healthcheck" in svc, name
        assert list(svc.get("networks", {}).keys()) == ["box"], name
        image = svc.get("image", "")
        assert not image.endswith(":latest"), f"{name} pins :latest"


def test_only_caddy_publishes_web_ports():
    cfg = render()
    published = {}
    for name, svc in cfg["services"].items():
        for p in svc.get("ports", []) or []:
            published.setdefault(name, set()).add(int(p["published"]))
    assert published["caddy"] >= {80, 3080, 4000}
    assert set(published) == {"caddy"}, published


def test_env_example_covers_every_variable():
    text = "\n".join((BOX / f).read_text()
                     for f in ("docker-compose.yml", "docker-compose.linux.yml", "docker-compose.gpu.yml")
                     if (BOX / f).exists())
    used = set(re.findall(r"\$\{([A-Z0-9_]+)(?::-[^}]*)?\}", text))
    declared = set(re.findall(r"^([A-Z0-9_]+)=", (BOX / ".env.example").read_text(), re.M))
    missing = used - declared
    assert not missing, f"used in compose but absent from .env.example: {sorted(missing)}"


def test_litellm_mounts_box_config_and_policy():
    svc = render()["services"]["litellm-proxy"]
    targets = {v["target"] for v in svc["volumes"]}
    assert "/app/config.yaml" in targets
    assert "/app/guardrails/policy.yaml" in targets


def test_rag_api_uses_local_embeddings():
    env = render()["services"]["rag_api"]["environment"]
    assert env["EMBEDDINGS_PROVIDER"] == "ollama"
    assert env["EMBEDDINGS_MODEL"] == "bge-m3"
    assert "RAG_GOOGLE_API_KEY" not in env


def test_sso_services_share_one_hostname():
    svcs = render()["services"]
    assert SSO <= set(svcs)
    console = svcs["console"]["environment"]
    assert console["CHAT_BASE_URL"] == "http://librechat:3080"
    assert console["CHAT_PUBLIC_URL"] == "https://nufi.local:3080"
    assert console["OIDC_ISSUER"] == "https://nufi.local:3001"
    assert console["STUDIO_URL"] == "https://nufi.local:7860"
    assert console["IDENTITY_COOKIE_DOMAIN"] == ""
    assert "AGENT_ENTITLEMENTS" not in console
    studio = svcs["studio"]["environment"]
    assert studio["LANGFLOW_EXTERNAL_AUTH_JWKS_URL"] == "https://nufi.local:3001/.well-known/jwks.json"
    assert studio["LANGFLOW_EXTERNAL_AUTH_ISSUER"] == console["OIDC_ISSUER"]
    assert studio["LANGFLOW_EXTERNAL_AUTH_AUDIENCE"] == "nufi-studio"
    assert studio["LANGFLOW_EXTERNAL_AUTH_TOKEN_COOKIE"] == "nufi_id"
    assert studio["SSL_CERT_FILE"] == "/etc/ssl/certs/ca-certificates.crt"
    admin = svcs["admin-panel"]["environment"]
    assert admin["API_SERVER_URL"] == "http://librechat:3080"
    assert admin["VITE_API_BASE_URL"] == "https://nufi.local:3080"


def test_ingest_watches_the_drives_read_only():
    svc = render()["services"]["nufi-ingest"]
    mount = [v for v in svc["volumes"] if v["target"] == "/drives"][0]
    assert mount["read_only"] is True


def test_linux_profile_adds_ollama_and_samba():
    cfg = render("docker-compose.yml", "docker-compose.linux.yml", profiles=("linux",))
    assert LINUX <= set(cfg["services"])
    assert cfg["services"]["samba"]["ports"][0]["published"] == "445"
    assert "11434" not in json.dumps(cfg["services"]["ollama"].get("ports", []))
    # Without docker-compose.gpu.yml, a CPU-only Linux host never sees the nvidia
    # device reservation — it would make `docker compose up` fail without the
    # NVIDIA Container Toolkit installed.
    assert "deploy" not in cfg["services"]["ollama"]


def test_gpu_profile_adds_the_device_reservation_to_ollama():
    cfg = render("docker-compose.yml", "docker-compose.linux.yml", "docker-compose.gpu.yml",
                 profiles=("linux", "gpu"))
    devices = cfg["services"]["ollama"]["deploy"]["resources"]["reservations"]["devices"]
    assert any(d.get("driver") == "nvidia" for d in devices)


def test_emulate_layer_only_marks_the_images_published_amd64_only():
    svcs = render("docker-compose.yml", "docker-compose.emulate.yml")["services"]
    assert svcs["librechat"]["platform"] == "linux/amd64"
    assert svcs["admin-panel"]["platform"] == "linux/amd64"
    for name in set(svcs) - {"librechat", "admin-panel"}:
        assert "platform" not in svcs[name], name


def test_studio_may_reach_the_box_model_host():
    """Langflow refuses any hostname that resolves to a private address, and
    every model host a box has is one: host.docker.internal on macOS (native
    Ollama behind the Docker gateway), the `ollama` container on Linux.
    Without this allowlist, running any flow on a default macOS box dies with
    "SSRF Protection: Hostname host.docker.internal resolves to blocked IP
    address(es)" — Studio cannot reach the box's own model."""
    allowed = render()["services"]["studio"]["environment"]["LANGFLOW_SSRF_ALLOWED_HOSTS"]
    hosts = [h.strip() for h in allowed.split(",")]
    assert "host.docker.internal" in hosts, allowed
    assert "ollama" in hosts, allowed
