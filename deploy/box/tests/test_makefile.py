"""The LAN-registry Makefile targets, read with `make -n` (nothing is executed).

Run: cd deploy/box && python3 -m pytest tests -q
"""
import os
import pathlib
import subprocess
import tempfile

BOX = pathlib.Path(__file__).resolve().parents[1]
NUFI_IMAGES = ("nufichat", "nufichat-admin-panel", "nufi-console",
               "nufi-litellm", "nufi-ingest", "nufi-studio")
# The .env key each image's tag comes from, as docker-compose.yml reads it.
TAG_KEY = {"nufichat": "NUFI_CHAT_TAG", "nufichat-admin-panel": "NUFI_ADMIN_TAG",
           "nufi-console": "NUFI_CONSOLE_TAG", "nufi-litellm": "NUFI_LITELLM_TAG",
           "nufi-ingest": "NUFI_INGEST_TAG", "nufi-studio": "NUFI_STUDIO_TAG"}


def make_n(target, **variables):
    cmd = ["make", "-n", target] + [f"{k}={v}" for k, v in variables.items()]
    out = subprocess.run(cmd, cwd=BOX, capture_output=True, text=True, check=True)
    return out.stdout


def test_registry_up_publishes_the_port_named_in_registry():
    # macOS holds 5000 (AirPlay Receiver), so a Mac serving the images runs the
    # registry on another port; `registry-up` has to follow REGISTRY there
    # instead of always publishing 5000.
    assert "-p 5001:5000" in make_n("registry-up", REGISTRY="172.10.10.30:5001")


def test_registry_up_defaults_to_5000():
    assert "-p 5000:5000" in make_n("registry-up")


def test_registry_up_survives_a_registry_without_a_port():
    assert "-p 5000:5000" in make_n("registry-up", REGISTRY="registry.lan")


def test_registry_push_pushes_all_six_nufi_images_over_loopback():
    # The push goes to localhost, not to REGISTRY: Docker trusts loopback
    # without an insecure-registries entry, so serving the images from a Mac
    # needs no Docker Desktop change. Same container, same stored images.
    out = make_n("registry-push", REGISTRY="172.10.10.30:5001")
    for image in NUFI_IMAGES:
        assert f"docker push localhost:5001/{image}:" in out, image
    # the six NuFi images plus the two ghcr-hosted third-party ones
    assert out.count("docker push ") == len(NUFI_IMAGES) + 2
    assert "docker push 172.10.10.30:5001" not in out


def test_registry_push_can_be_pointed_at_a_registry_elsewhere():
    out = make_n("registry-push", PUSH_REGISTRY="registry.example:5000")
    # arm64-dev in, main out: the source tag is this machine's, the
    # destination tag is the one a box asks for.
    assert "docker tag ghcr.io/dudaji-vn/nufichat:arm64-dev " \
           "registry.example:5000/nufichat:main" in out
    assert "docker push registry.example:5000/nufichat:main" in out


def _tags_a_default_install_pulls():
    """The NUFI_*_TAG values install-box.sh writes into a fresh .env."""
    with tempfile.TemporaryDirectory() as tmp:
        e = dict(os.environ, NUFI_BOX_DRY_RUN="1", NUFI_BOX_FAKE_OS="Linux",
                 NUFI_BOX_ENV=str(pathlib.Path(tmp) / "absent.env"))
        out = subprocess.run(["/bin/bash", str(BOX / "install-box.sh"), "--dry-run", "--yes"],
                             cwd=BOX, env=e, capture_output=True, text=True, check=True).stdout
    env = dict(line.split("=", 1) for line in out.splitlines() if line[:5].isupper() and "=" in line)
    return {image: env[key] for image, key in TAG_KEY.items()}


def test_registry_push_publishes_the_tags_a_default_install_pulls():
    # The Mac's images can be tagged anything (a native arm64 build is
    # `arm64-dev`); the box asks for what its own .env says. Pushing the source
    # tag is what made the first blank-VM install die on
    # `nufichat-admin-panel:main: not found`, so the two are pinned together
    # here rather than trusted to stay in step.
    out = make_n("registry-push", REGISTRY="172.10.10.30:5001")
    for image, tag in _tags_a_default_install_pulls().items():
        assert f"docker push localhost:5001/{image}:{tag}" in out, f"{image}:{tag}"


def test_registry_push_also_mirrors_the_ghcr_hosted_third_party_images():
    out = make_n("registry-push", REGISTRY="172.10.10.30:5001")
    assert "docker push localhost:5001/librechat-rag-api-dev-lite:main" in out
    assert "docker push localhost:5001/samba:main" in out
    # pinned upstream, tagged in the mirror
    assert "librechat-rag-api-dev-lite@sha256:" in out
    assert "ghcr.io/servercontainers/samba:a3.24.1-s4.23.8-r0" in out
