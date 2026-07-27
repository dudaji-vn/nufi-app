# Derived LiteLLM image with the NUFI guardrail package baked in, so the same
# artifact runs on the on-prem compose stack and on the production gateway.
#
# Pinned rather than :main-stable, per the project's "pin every image" rule.
# v1.83.10 is the version platform-ci.yml already installs for the Python
# tests, so the image and the test environment agree. Verified present on GHCR
# 2026-07-27.
#
# There is deliberately NO `pip install` here. The guardrail package's only
# third-party imports -- httpx, prometheus_client, yaml -- are already
# dependencies of litellm itself. Verified by running this exact base image:
#
#     httpx              0.28.1   (litellm pins this at the top level)
#     prometheus-client  0.20.0
#     PyYAML             6.0.3
#     litellm            1.83.10
#
# All three conflict with litellm/requirements.txt (0.27.2 / 0.21.1 / 6.0.2),
# and httpx is a hard `==` pin of litellm's own. Installing that file over this
# image downgrades httpx underneath the proxy and prints only a resolver
# warning -- a build step that reports success while degrading a dependency the
# whole proxy runs on. litellm/requirements.txt exists for the CI/test venv
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
COPY guardrails /app/guardrails
COPY callbacks /app/callbacks
COPY config.yaml /app/config.yaml
