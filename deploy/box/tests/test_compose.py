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
# Every service whose image is a NuFi-built one, i.e. must follow
# ${NUFI_REGISTRY:-ghcr.io/dudaji-vn}/<name>:<tag>. Everything else (caddy,
# postgres, mongodb, rag_api, and the linux-profile ollama/samba, plus any
# future tailscale sidecar) is a third-party image and must be untouched.
NUFI_SERVICES = {"litellm-proxy", "librechat", "console", "admin-panel", "studio", "nufi-ingest"}


def render(*files, profiles=(), **extra_env):
    env = dict(os.environ)
    # Deterministic default: a real shell might export NUFI_REGISTRY (e.g. a
    # developer testing against their own LAN registry); the "default render"
    # tests must see the compose file's own ${NUFI_REGISTRY:-ghcr.io/dudaji-vn}
    # fallback, not whatever happens to be in the ambient environment.
    env.pop("NUFI_REGISTRY", None)
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
    env.update(extra_env)
    cmd = ["docker", "compose", "--project-directory", str(BOX)]
    for f in files or ("docker-compose.yml",):
        cmd += ["-f", str(BOX / f)]
    for p in profiles:
        cmd += ["--profile", p]
    cmd += ["config", "--format", "json"]
    out = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_images_come_from_the_configured_registry():
    """A customer box (and the Ubuntu VM test that follows) cannot log in to
    GHCR, so every NuFi-built image must be pullable from any registry."""
    cfg = render("docker-compose.yml", "docker-compose.linux.yml", "docker-compose.gpu.yml",
                 profiles=("linux", "gpu"), NUFI_REGISTRY="10.0.0.5:5000")
    for name in NUFI_SERVICES:
        image = cfg["services"][name]["image"]
        assert image.startswith("10.0.0.5:5000/"), (name, image)
    for name, svc in cfg["services"].items():
        if name in NUFI_SERVICES:
            continue
        image = svc.get("image", "")
        assert not image.startswith("10.0.0.5:5000/"), (name, image)

    # Unset (the default on every box today): falls back to ghcr.io/dudaji-vn.
    default_cfg = render()
    for name in NUFI_SERVICES:
        image = default_cfg["services"][name]["image"]
        assert image.startswith("ghcr.io/dudaji-vn/"), (name, image)
    for name in {"caddy", "postgres", "mongodb", "rag_api"}:
        image = default_cfg["services"][name]["image"]
        assert not image.startswith("ghcr.io/dudaji-vn/"), (name, image)


def test_core_services_present_and_named():
    cfg = render()
    assert cfg["name"] == "nufi-box"
    assert CORE <= set(cfg["services"])


def test_every_service_follows_the_house_rules():
    cfg = render("docker-compose.yml", "docker-compose.linux.yml", "docker-compose.gpu.yml",
                 "docker-compose.mesh.yml", profiles=("linux", "gpu", "mesh"))
    for name, svc in cfg["services"].items():
        assert svc.get("restart") == "unless-stopped", name
        assert "healthcheck" in svc, name
        # Every service sits on the `box` bridge, except the one that cannot:
        # tailscaled has to own the host's namespace to give the host a mesh
        # address at all. `network_mode` and `networks` are mutually exclusive
        # in compose, so that is still an explicit, single answer per service.
        if "network_mode" in svc:
            assert svc["network_mode"] == "host", name
            assert not svc.get("networks"), name
        else:
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
                     for f in ("docker-compose.yml", "docker-compose.linux.yml",
                               "docker-compose.gpu.yml", "docker-compose.mesh.yml")
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


# --- Task 6: the box as a mesh node ------------------------------------------

def test_the_mesh_profile_adds_the_tailscale_node():
    """`nufi-box mesh up` layers docker-compose.mesh.yml and starts one extra
    container. It needs the host's own network namespace (so Caddy's published
    ports answer on the mesh address and Samba's 445 with them), a TUN device
    and NET_ADMIN for kernel-mode tailscaled, and a pinned image like every
    other service."""
    svc = render("docker-compose.yml", "docker-compose.mesh.yml",
                 profiles=("mesh",))["services"]["tailscale"]
    assert svc["network_mode"] == "host"
    assert "NET_ADMIN" in svc["cap_add"]
    assert any(d["source"] == "/dev/net/tun" for d in svc["devices"]), svc["devices"]
    assert svc["image"].startswith("tailscale/tailscale:v"), svc["image"]
    assert not svc["image"].endswith(":latest")
    assert svc["restart"] == "unless-stopped"
    # `tailscale status` talks to the local tailscaled socket and exits 0 only
    # once the backend is up; --peers=false keeps it cheap on a busy tailnet.
    assert "tailscale status --peers=false" in json.dumps(svc["healthcheck"]["test"])


def test_the_tailscale_node_logs_in_with_the_preauth_key_and_the_box_name():
    env = render("docker-compose.yml", "docker-compose.mesh.yml",
                 profiles=("mesh",), MESH_AUTH_KEY="tskey-auth-test",
                 MESH_SERVER_URL="https://mesh.example")["services"]["tailscale"]["environment"]
    assert env["TS_AUTHKEY"] == "tskey-auth-test"
    assert "--login-server=https://mesh.example" in env["TS_EXTRA_ARGS"]
    assert "--hostname=nufi" in env["TS_EXTRA_ARGS"]
    # headscale v0.29.3 rejects RequestTags on ANY pre-auth-key registration
    # ("requested tags [tag:box] are invalid or not permitted", confirmed live
    # against the lab coordinator) — tag:box comes from the key's own aclTags.
    assert "--advertise-tags" not in env["TS_EXTRA_ARGS"], env["TS_EXTRA_ARGS"]


def test_the_base_box_has_no_tailscale_container():
    """A box that never joined a mesh must not gain a container, and even with
    the file layered the `mesh` profile is what turns it on."""
    assert "tailscale" not in render()["services"]
    assert "tailscale" not in render("docker-compose.yml", "docker-compose.mesh.yml")["services"]


def test_caddy_can_read_the_generated_mesh_sites():
    """The Caddyfile imports caddy/mesh*.caddy, which Caddy resolves relative
    to the config file — so ./caddy has to be inside /etc/caddy."""
    targets = {v["target"] for v in render()["services"]["caddy"]["volumes"]}
    assert "/etc/caddy/caddy" in targets, targets


# --- the department routines read the drives (Task 8) ---

def test_studio_mounts_the_department_drives_read_only():
    """The routines answer from the same folders Samba shares. Read-only: a
    flow is authored by a person, and a person editing a flow must not be able
    to rewrite the department's documents through it."""
    vols = {v["target"]: v for v in render()["services"]["studio"]["volumes"]}
    assert "/drives" in vols, sorted(vols)
    drives = vols["/drives"]
    assert drives["source"].endswith("/drives"), drives["source"]
    assert drives["read_only"] is True, drives


def test_studio_is_allowed_to_read_the_drives_and_nothing_else():
    """The mount alone is not enough. The Directory component confines itself
    to its working directory plus this allow-list, so without it every routine
    fails with "Directory path escapes the allowed root" — the failure a live
    run on a box without this env var actually produced."""
    env = render()["services"]["studio"]["environment"]
    assert env["LANGFLOW_DIRECTORY_COMPONENT_ALLOWED_ROOTS"] == "/drives"


def test_the_drives_reach_studio_and_ingest_from_the_same_place():
    """One folder, two readers: what a person drops on the drive has to be the
    same bytes the routine reads and the ingest daemon indexes."""
    svcs = render()["services"]
    studio = next(v["source"] for v in svcs["studio"]["volumes"] if v["target"] == "/drives")
    ingest = next(v["source"] for v in svcs["nufi-ingest"]["volumes"] if v["target"] == "/drives")
    assert studio == ingest, (studio, ingest)
