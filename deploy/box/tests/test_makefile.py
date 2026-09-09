"""The LAN-registry Makefile targets, read with `make -n` (nothing is executed).

Run: cd deploy/box && python3 -m pytest tests -q
"""
import pathlib
import subprocess

BOX = pathlib.Path(__file__).resolve().parents[1]
NUFI_IMAGES = ("nufichat", "nufichat-admin-panel", "nufi-console",
               "nufi-litellm", "nufi-ingest", "nufi-studio")


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


def test_registry_push_pushes_all_six_nufi_images_to_the_registry():
    out = make_n("registry-push", REGISTRY="172.10.10.30:5001")
    for image in NUFI_IMAGES:
        assert f"docker push 172.10.10.30:5001/{image}:" in out, image
    assert out.count("docker push ") == len(NUFI_IMAGES)
