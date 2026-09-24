"""The LAN-registry Makefile targets, read with `make -n` (nothing is executed).

Run: cd deploy/box && python3 -m pytest tests -q
"""
import os
import pathlib
import re
import subprocess
import tempfile

BOX = pathlib.Path(__file__).resolve().parents[1]
# Every NuFi image docker-compose.yml names, read from the file rather than
# listed here: the mirror was "the NuFi six" for a month after nufi-cron made it
# seven, and a box behind a LAN registry found out at pull time.
NUFI_IMAGES = tuple(sorted(
    set(re.findall(r"NUFI_REGISTRY:-ghcr\.io/dudaji-vn\}/([a-z0-9-]+):",
                   (BOX / "docker-compose.yml").read_text()))
    # …plus the one image the box pulls outside compose: the sandbox image,
    # registered as the Works environment's image by digest (install-box.sh
    # --with-works). Not a service, so compose never names it.
    | set(re.findall(r"nufi-sandbox(?=:\$\{NUFI_SANDBOX_TAG)",
                     (BOX / "install-box.sh").read_text()))))
# The .env key each image's tag comes from, as docker-compose.yml reads it.
TAG_KEY = {"nufichat": "NUFI_CHAT_TAG", "nufichat-admin-panel": "NUFI_ADMIN_TAG",
           "nufi-console": "NUFI_CONSOLE_TAG", "nufi-litellm": "NUFI_LITELLM_TAG",
           "nufi-ingest": "NUFI_INGEST_TAG", "nufi-studio": "NUFI_STUDIO_TAG",
           "nufi-cron": "NUFI_CRON_TAG", "nufi-works-egress": "NUFI_WORKS_EGRESS_TAG",
           "nufi-sandbox": "NUFI_SANDBOX_TAG", "nufi-works": "NUFI_WORKS_TAG"}


def test_the_compose_file_names_every_image_the_mirror_knows():
    """The two lists above must agree, or a new image is mirrored under no tag."""
    assert set(NUFI_IMAGES) == set(TAG_KEY), (sorted(NUFI_IMAGES), sorted(TAG_KEY))


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


def test_registry_push_pushes_every_nufi_image_over_loopback():
    # The push goes to localhost, not to REGISTRY: Docker trusts loopback
    # without an insecure-registries entry, so serving the images from a Mac
    # needs no Docker Desktop change. Same container, same stored images.
    out = make_n("registry-push", REGISTRY="172.10.10.30:5001")
    for image in NUFI_IMAGES:
        assert f"docker push localhost:5001/{image}:" in out, image
    # every NuFi image plus the three ghcr-hosted third-party ones
    # (RAG, Samba, and — for a self-hosted coordinator — headscale)
    assert out.count("docker push ") == len(NUFI_IMAGES) + 3
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
    # a --self-host-coordinator box also pulls headscale (deploy/coordinator)
    # from ghcr, so it is mirrored next to RAG/Samba
    assert "docker push localhost:5001/headscale:main" in out
    # pinned upstream, tagged in the mirror
    assert "librechat-rag-api-dev-lite@sha256:" in out
    assert "ghcr.io/servercontainers/samba:a3.24.1-s4.23.8-r0" in out
    assert "ghcr.io/juanfont/headscale:v0.29.3" in out


# --- offline-media bundle: `make save` (a site with NO LAN registry at all) ---

def test_save_bundles_every_nufi_image_at_the_dest_tag_a_default_install_pulls():
    # Same source->dest as registry-push: the box asks for what its .env names
    # (main, box-main for studio), so the saved ref must be that, not the build tag.
    out = make_n("save")
    for image, tag in _tags_a_default_install_pulls().items():
        assert f"ghcr.io/dudaji-vn/{image}:{tag}" in out, f"{image}:{tag}"


def test_save_covers_every_nufi_image_the_mirror_covers():
    # Pin `save` to the same compose-derived list as registry-push, so a new
    # NuFi image cannot be mirrored-but-not-bundled (or vice versa).
    out = make_n("save")
    for image in NUFI_IMAGES:
        assert f"ghcr.io/dudaji-vn/{image}:" in out, image


def test_save_retags_the_build_tags_like_registry_push():
    out = make_n("save")
    assert "docker tag ghcr.io/dudaji-vn/nufichat:arm64-dev ghcr.io/dudaji-vn/nufichat:main" in out
    assert "docker tag ghcr.io/dudaji-vn/nufichat-admin-panel:arm64-dev ghcr.io/dudaji-vn/nufichat-admin-panel:main" in out
    assert "docker tag ghcr.io/dudaji-vn/nufi-studio:box-main ghcr.io/dudaji-vn/nufi-studio:box-main" in out


def test_save_writes_one_tarball_by_default():
    out = make_n("save")
    assert "docker save -o nufi-box-images.tar" in out
    assert out.count("docker save") == 1          # single tarball, not per-image


def test_save_tar_path_is_overridable():
    assert "docker save -o /mnt/usb/box.tar" in make_n("save", SAVE_TAR="/mnt/usb/box.tar")


def test_save_includes_third_party_at_their_compose_default_refs():
    out = make_n("save")
    assert "caddy:2.10.0-alpine" in out
    assert "mongo:4.4" in out
    assert "pgvector/pgvector:pg16" in out
    assert "ollama/ollama:0.33.3" in out
    assert "ghcr.io/servercontainers/samba:a3.24.1-s4.23.8-r0" in out
    assert "ghcr.io/juanfont/headscale:v0.29.3" in out          # self-host coordinator
    assert "librechat-rag-api-dev-lite@sha256:" in out          # RAG pinned by digest on the way in


def test_save_carries_rag_loadable_by_tag():
    # A plain digest ref does not survive `docker load` on the box's image store,
    # so RAG is retagged to a :main alias of the pinned digest and that is saved.
    out = make_n("save")
    assert "docker tag ghcr.io/danny-avila/librechat-rag-api-dev-lite@sha256:" in out
    assert "ghcr.io/danny-avila/librechat-rag-api-dev-lite:main" in out


def test_save_never_pushes_or_rewrites_to_a_registry():
    # `save` is fully offline: it must not push, and must not rename third-party
    # images under $(NUFI_REGISTRY)/... the way the mirror does.
    out = make_n("save", REGISTRY="172.10.10.30:5001")
    assert "docker push" not in out
    assert "172.10.10.30:5001" not in out


def test_third_party_pins_match_the_compose_defaults():
    # Anti-drift: the Makefile pins can't fall behind the compose files.
    compose = ((BOX / "docker-compose.yml").read_text()
               + (BOX / "docker-compose.linux.yml").read_text())
    for ref in ("caddy:2.10.0-alpine", "mongo:4.4",
                "pgvector/pgvector:pg16", "ollama/ollama:0.33.3"):
        assert ref in compose, ref                 # still the compose default
        assert ref in make_n("save"), ref          # and the bundle carries it


def test_load_reads_the_default_tarball_and_honors_the_override():
    assert "docker load -i nufi-box-images.tar" in make_n("load")
    assert "docker load -i /mnt/usb/box.tar" in make_n("load", SAVE_TAR="/mnt/usb/box.tar")
