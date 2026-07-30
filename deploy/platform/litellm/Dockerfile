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
# integration.md §7 step 1), and it is a Python package. It arrives as a
# VENDORED SOURCE SNAPSHOT at nufi-security/, recorded in
# nufi-security.provenance.md, and is copied in as plain files. No pip, no
# resolver and no dependency metadata ever touch the runtime image -- which is
# also the only way it could be done here: this base image is Wolfi and ships
# neither pip nor git (verified: `pip: not found`, `git: not found`,
# `No module named pip`). A literal `RUN pip install ...` in the runtime stage
# would not build.
#
# A builder stage used to `pip install --no-deps` the package from GitHub at a
# pinned commit. That is gone, and DELIBERATELY: this build must not reach the
# network for it. Two reasons, both measured, both in the provenance file --
# a fix to their code needed a pull request into a repository we do not own,
# and pip never delivered the root VERSION file, so the library reported
# `__version__ == '0.0.0'` inside a running container while actually being
# 0.10.0.
#
# The dependency argument the builder stage relied on still holds and is why
# copying source is safe: nufi-security declares exactly two runtime
# dependencies, `PyYAML>=6.0` and `cryptography>=41.0`, and the table above
# shows the image already carries 6.0.3 and 46.0.7. Both constraints are
# satisfied by what litellm already chose. Now there is no resolver at all.
#
# litellm/requirements.txt is for the CI/test venv
# (.github/workflows/platform-ci.yml), never for this image.

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
# This also ships guardrails/nufi_patterns.yaml, and that is not incidental.
# `pip install nufi-egress` delivers the library's Python packages but NOT its
# `config/` directory -- the distribution names seven packages and no data
# directory -- so `DetectionPipeline()` raises FileNotFoundError looking for
# `<site-packages>/config/patterns.yaml`. The Korean PII rules are therefore
# vendored into this repo, byte-identical to the pinned commit's
# `config/patterns.yaml` (digest and source commit are asserted by
# tests/test_nufi_pii_scanner.py against the ARG below), and ride in on this
# line. `guardrails/scanners/nufi_pii.py` resolves them to an absolute path off
# its own location and passes that explicitly.
#
# Deliberately NOT copied to /app/config, which is exactly where the library's
# own discovery would find it given that nufi-security lands in /app. Leaving
# their discovery unable to succeed means the explicit path is the only thing
# that works, in the image as well as in CI -- their resolution is relative to
# `egress_audit/__file__`'s grandparent and was measured to depend on how the
# process was started, so it must never be the mechanism anything relies on.
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
# `__init__` imports from all three), so every package the distribution
# declares is copied rather than a hand-picked subset -- a partial copy is a
# package whose own imports may or may not resolve, decided by which functions
# get called. The list below is exactly `[tool.setuptools] packages` from
# nufi-security/pyproject.toml, and tests/test_nufi_pii_scanner.py asserts the
# two have not drifted apart.
#
# The REST of the snapshot -- its tests, docs, benchmarks, its own Dockerfile
# and Helm chart -- deliberately does not ship. It is 4.5 MB of things a
# gateway does not run.
COPY nufi-security/nufi /app/nufi
COPY nufi-security/enforcement /app/enforcement
COPY nufi-security/egress_audit /app/egress_audit
COPY nufi-security/capture /app/capture
COPY nufi-security/nufi_client /app/nufi_client
COPY nufi-security/gateway /app/gateway

# Not incidental, and not covered by the package list above. `nufi/__init__.py`
# reads `__version__` from this file and falls back to "0.0.0" if it is absent.
# The distribution declares seven packages and no data files, so the previous
# pip-based build never delivered it and the running container reported
# `nufi.__version__ == '0.0.0'` for a 0.10.0 library -- measured, not inferred.
# `enforcement/` resolves the same file by several different relative paths.
COPY nufi-security/VERSION /app/VERSION

# If any of the copies above is missing or broken, the proxy does not start: G1
# constructs NufiInjectionScanner at import time and its constructor proves the
# detector fires on a known attack and stays quiet on a known benign sentence
# (guardrails/scanners/nufi_injection.py). A detector that cannot do its job
# must not be able to return a value that looks like success.
