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
INGEST = {"nufi-ingest"}
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
    cfg = render()
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
    text = "\n".join((BOX / f).read_text() for f in ("docker-compose.yml", "docker-compose.linux.yml")
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
