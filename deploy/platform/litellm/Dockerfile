# Derived LiteLLM image with the NUFI guardrail package baked in, so the same
# artifact runs on the on-prem compose stack and on the production gateway.
#
# Pinned rather than :main-stable, per the project's "pin every image" rule.
# v1.83.10 is the version platform-ci.yml already installs for the Python
# tests, so the image and the test environment agree. Verified present on GHCR
# 2026-07-27.
#
# NOTHING IS EVER INSTALLED INTO THE RUNTIME IMAGE'S OWN ENVIRONMENT, and that
# rule has not changed. The guardrail package's own third-party imports --
# httpx, prometheus_client, yaml -- are already dependencies of litellm itself,
# chosen by litellm. Measured by running this exact base image, before and
# after the vendoring stage below:
#
#                        before      after
#     httpx              0.28.1      0.28.1
#     prometheus-client  0.20.0      0.20.0
#     PyYAML             6.0.3       6.0.3
#     litellm            1.83.10     1.83.10
#     cryptography       46.0.7      46.0.7
#
# The reason for that rule is a real incident: litellm/requirements.txt once
# pinned httpx==0.27.2 against litellm's own top-level httpx==0.28.1, and
# installing it over this image downgraded httpx underneath the proxy while
# reporting only a resolver warning -- a build step that succeeds while
# degrading a dependency the whole proxy runs on. So the rule is not "no new
# code in the image", it is "NO RESOLVER EVER RUNS AGAINST THIS IMAGE'S
# DEPENDENCY SET". A resolver is the thing that can silently move a pin.
#
# G1 needs a second, independent detector (docs/2026-07-29-nufi-security-
# integration.md §7 step 1), and it is a Python package. The builder stage
# below installs it at a pinned COMMIT, with --no-deps, into an empty
# directory, and the runtime stage COPYs the result. No pip, no resolver and
# no dependency metadata ever touch the runtime image -- which is also the
# only way it could be done here: this base image is Wolfi and ships neither
# pip nor git (verified: `pip: not found`, `git: not found`,
# `No module named pip`). A literal `RUN pip install ...` in the runtime stage
# would not build.
#
# --no-deps is safe to assert rather than hope: nufi-security declares exactly
# two runtime dependencies, `PyYAML>=6.0` and `cryptography>=41.0`, and the
# table above shows the image already carries 6.0.3 and 46.0.7. Both
# constraints are satisfied by what litellm already chose, so there is nothing
# for a resolver to do -- and with --no-deps there is no resolver to do it.
#
# litellm/requirements.txt is for the CI/test venv
# (.github/workflows/platform-ci.yml), never for this image.

# Vendoring stage. Pinned to a COMMIT, never a branch: nufi-security is
# v0.10.0 with an API declared stable through `nufi/__init__.py`'s `__all__`,
# but it is a young internal package and a branch pin would let its behaviour
# change under a rebuild -- including the regex patterns G1 now enforces on
# user spans with.
#
# The repository is public: verified with an unauthenticated
# `GIT_TERMINAL_PROMPT=0 git clone` and an unauthenticated API call, so no
# build credential is needed and none is plumbed in.
FROM python:3.13.13-bookworm AS nufi-security
ARG NUFI_SECURITY_COMMIT=5eb9a027cbdd9c5d3142d4609782110a737c67e0
RUN pip install --no-cache-dir --no-deps --target /opt/nufi-security \
    "git+https://github.com/dudaji/nufi-security@${NUFI_SECURITY_COMMIT}"

FROM ghcr.io/berriai/litellm:v1.83.10-stable

WORKDIR /app

# WORKDIR matters for imports, not just for COPY targets. LiteLLM loads
# guardrails/entrypoints.py by file path (get_instance_fn -> dirname(config) +
# module path), which does NOT register the parent package, so entrypoints.py's
# own `from guardrails import audit` needs the package's parent directory on
# sys.path. litellm/proxy/proxy_cli.py:24 does `sys.path.append(os.getcwd())`,
# which supplies exactly that -- and appends, so nothing here shadows an
# installed distribution. Do not set `working_dir:` on this service in compose.
#
# Do NOT "fix" this with `ENV PYTHONPATH=/app`. Verified by running this image:
# PYTHONPATH lands ahead of site-packages, so `import litellm` then resolves to
# /app/litellm -- the raw source tree the base image ships alongside the venv --
# instead of the installed litellm==1.83.10. Same failure shape as the pip
# install above: a change that looks like hardening while quietly swapping out
# what the proxy runs on.
COPY guardrails /app/guardrails
COPY callbacks /app/callbacks
COPY config.yaml /app/config.yaml

# nufi-security lands in /app for exactly the reason `guardrails` does: it is
# the import path this image already has, and it is APPENDED to sys.path, so
# nothing here can shadow an installed distribution. Copying into
# /app/.venv/lib/python3.13/site-packages would have worked too, and was
# rejected: it hardcodes the interpreter's minor version into a path, so a base
# image that moved to 3.14 would silently create a directory nothing reads.
#
# `import nufi` pulls `egress_audit`, `enforcement` and `gateway` (its
# `__init__` imports from all three), so the whole install tree is copied
# rather than a hand-picked subset -- a partial copy is a package whose own
# imports may or may not resolve, decided by which functions get called.
#
# If this copy is ever missing or broken, the proxy does not start: G1
# constructs NufiInjectionScanner at import time and its constructor proves the
# detector fires on a known attack and stays quiet on a known benign sentence
# (guardrails/scanners/nufi_injection.py). A detector that cannot do its job
# must not be able to return a value that looks like success.
COPY --from=nufi-security /opt/nufi-security /app
