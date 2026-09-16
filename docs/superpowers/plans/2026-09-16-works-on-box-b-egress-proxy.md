# Works on the box — piece B: the egress proxy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `works-egress` service and a `works-sandbox` internal network in the box compose, so a sandbox created by piece A's provider has exactly one way to the world — a forward proxy that consults an allow list, refuses everything else with 403, and logs every refused hostname.

**Architecture:** tinyproxy, pinned, on two networks: `works-sandbox` (declared `internal: true`, so nothing on it has a route out) and the box's `box` network (so the proxy itself can reach the gateway, the Works server, and the internet). Its filter file is rendered at container start by a small entrypoint from three inputs — the two always-on hosts the design fixes, plus `WORKS_EGRESS_ALLOW` from `.env` — with `FilterDefaultDeny Yes`, so an empty operator list still lets a sandbox reach the model through the gateway and report to Works, and nothing else. The sandbox network is named with a compose `name:` literal, because piece A's provider hard-codes `works-sandbox` and compose would otherwise prefix it `nufi-box_`. Fail-closed is structural: if the proxy is down, a sandbox has no network at all.

**Tech Stack:** docker compose, tinyproxy 1.11.x (Alpine image, pinned by digest), POSIX sh for the entrypoint, the box's existing pytest suite (`deploy/box/tests/test_compose.py`) plus one stdlib test for the renderer. No Python runtime in the container.

**Spec:** `docs/superpowers/specs/2026-09-16-works-on-box-design.md`, section "B — the egress proxy". Piece A's provider (merged, #119) is the consumer: it sets every sandbox's `HostConfig.NetworkMode = "works-sandbox"` and `HTTPS_PROXY=http://works-egress:3128`.

## Global Constraints

- **Network name is the literal `works-sandbox`** (compose `name: works-sandbox`), `internal: true`. Piece A's `SANDBOX_NETWORK` constant is this string; the two must match or every sandbox fails to start.
- **Proxy service name is `works-egress`, port `3128`** — piece A's `DEFAULTS.egressProxy = "works-egress:3128"`.
- **Always allowed, not configurable:** `works` (port 3100) and `litellm-proxy` (port 4000). **Never allowed:** the Ollama host directly — the spec's "no proxy for the model host directly". The renderer must not accept an operator entry that names it.
- **Default deny.** `FilterDefaultDeny Yes`; the filter file lists hosts only.
- **Refusals are logged by hostname** — tinyproxy's `LogLevel Connect` to stderr, so `nufi-box logs works-egress` answers "what did that agent try to reach".
- Every image pinned by tag **and** digest, like the box's third-party images (`NUFI_RAG_IMAGE`, `NUFI_SAMBA_IMAGE` in `install-box.sh`).
- The box's house rules from `tests/test_compose.py::test_every_service_follows_the_house_rules` apply (read that test before Task 2): `restart: unless-stopped`, logging bounded, on the `box` network, healthcheck present. `test_only_caddy_publishes_web_ports` means **no `ports:`** on this service.
- `.env.example` must carry `WORKS_EGRESS_ALLOW` (`test_env_example_covers_every_variable`).
- Nothing in this plan touches `apps/agents`. Nothing here is behind `--with-works` yet — that gate is piece C's; here the service is simply present and, with no sandboxes, idle.
- Run tests with `uvx pytest@8.3.4 tests -q` from `deploy/box` (that is how this repo runs them; see the ledger from piece A for why plain `pytest` is not on the machine). Compose validity: `docker compose -f docker-compose.yml config`.
- Commit messages in English, no AI-authorship framing.

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `deploy/box/works-egress/entrypoint.sh` | render `/etc/tinyproxy/filter` and `tinyproxy.conf` from env, then exec tinyproxy | create |
| `deploy/box/works-egress/render.sh` | the pure part: allow list in → filter lines out; sourced by the entrypoint and by the test | create |
| `deploy/box/works-egress/Dockerfile` | tinyproxy image + the two scripts | create |
| `deploy/box/works-egress/test_render.py` | stdlib test of the renderer: always-on hosts, operator list, refusals | create |
| `deploy/box/docker-compose.yml` | the `works-sandbox` network, the `works-egress` service | modify |
| `deploy/box/.env.example` | `WORKS_EGRESS_ALLOW=` | modify |
| `deploy/box/tests/test_compose.py` | the network is internal and literally named; the service is on both networks; house rules | modify |
| `.github/workflows/box-images.yml` | build `nufi-works-egress` beside the other box images | modify |
| `.github/workflows/box-ci.yml` | run `test_render.py` | modify |
| `deploy/box/README.md` | a short "Works egress" paragraph under the existing routines/Works material | modify |

---

### Task 1: The renderer — allow list in, filter file out

**Files:**
- Create: `deploy/box/works-egress/render.sh`, `deploy/box/works-egress/test_render.py`
- Modify: `.github/workflows/box-ci.yml`

**Interfaces:**
- Produces: `render.sh` — a POSIX sh script that reads `WORKS_EGRESS_ALLOW` (comma-separated hostnames, may be empty or unset) from the environment and writes the filter file to stdout, one host per line, always beginning with the two fixed hosts. Exits 2 with a message on stderr if an entry is not a bare hostname, or names the model host directly.

- [ ] **Step 1: Write the failing test**

`deploy/box/works-egress/test_render.py`:

```python
#!/usr/bin/env python3
"""The egress allow list, rendered. Stdlib only; no Docker.

The proxy is the only way out of the sandbox network, so what this script
writes is the whole of what an agent may reach. Two hosts are always there and
cannot be removed -- the Works server the sandbox reports to, and the gateway
the model is reached through -- and the model host itself can never be added,
because a sandbox that reaches Ollama directly is a sandbox outside the
gateway's limits and guardrails.

Run:  python3 deploy/box/works-egress/test_render.py     (exit 0 = PASS)
"""
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
RENDER = HERE / "render.sh"


def render(allow=None):
    env = {k: v for k, v in os.environ.items() if k != "WORKS_EGRESS_ALLOW"}
    if allow is not None:
        env["WORKS_EGRESS_ALLOW"] = allow
    return subprocess.run(["/bin/sh", str(RENDER)], env=env, capture_output=True, text=True)


def lines(r):
    return [l for l in r.stdout.splitlines() if l and not l.startswith("#")]


def test_the_two_fixed_hosts_are_always_first():
    for allow in (None, "", "pypi.org"):
        r = render(allow)
        assert r.returncode == 0, r.stderr
        assert lines(r)[:2] == ["works", "litellm-proxy"], (allow, lines(r))
    print("PASS: works and litellm-proxy are always allowed, and first")


def test_the_operator_list_is_appended_trimmed_and_deduplicated():
    r = render(" pypi.org, files.pythonhosted.org ,pypi.org,")
    assert lines(r) == ["works", "litellm-proxy", "pypi.org", "files.pythonhosted.org"], lines(r)
    print("PASS: the operator list is appended, trimmed, deduplicated")


def test_an_entry_that_is_not_a_hostname_is_refused():
    for bad in ("https://pypi.org", "pypi.org/simple", "pypi.org:443", "*.pypi.org", "10.0.0.5"):
        r = render(bad)
        assert r.returncode == 2, (bad, r.returncode, r.stdout)
        assert bad in r.stderr, (bad, r.stderr)
    print("PASS: URLs, paths, ports, globs and bare addresses are refused")


def test_the_model_host_cannot_be_allowed_directly():
    """A sandbox reaches the model through the gateway or not at all."""
    for host in ("ollama", "host.docker.internal", "ollama:11434"):
        r = render(host)
        assert r.returncode == 2, (host, r.stdout)
        assert "gateway" in r.stderr.lower(), r.stderr
    print("PASS: the model host is refused; the gateway is the only route to the model")


def test_nothing_else_is_in_the_output():
    r = render("example.com")
    for l in lines(r):
        assert l in ("works", "litellm-proxy", "example.com"), l
    print("PASS: the file holds hosts and comments, nothing else")


if __name__ == "__main__":
    test_the_two_fixed_hosts_are_always_first()
    test_the_operator_list_is_appended_trimmed_and_deduplicated()
    test_an_entry_that_is_not_a_hostname_is_refused()
    test_the_model_host_cannot_be_allowed_directly()
    test_nothing_else_is_in_the_output()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 deploy/box/works-egress/test_render.py`
Expected: FAIL — `render.sh` does not exist (`FileNotFoundError` or a non-zero exit from `/bin/sh`).

- [ ] **Step 3: Implement the renderer**

`deploy/box/works-egress/render.sh`:

```sh
#!/bin/sh
# The egress allow list, rendered to stdout as tinyproxy's filter file: one
# host per line, exact-match (FilterExtended Off in the config that reads it).
#
# Two hosts are always here and are not the operator's to remove: the Works
# server the sandbox reports back to, and the gateway the model is reached
# through. Everything else comes from WORKS_EGRESS_ALLOW in .env, comma-
# separated bare hostnames -- no scheme, no path, no port, no glob, no
# address. A sandbox is a place untrusted code runs; the list of where it may
# talk to is not a place to be generous with syntax.
#
# The model host can never be added. A sandbox that reaches Ollama directly is
# a sandbox outside the gateway's rate limits, budgets and guardrails, and the
# gateway is on this list precisely so that it does not have to be.
set -eu

ALWAYS="works litellm-proxy"
# Names the model is served under on the box, in any spelling an operator
# might try. The gateway (litellm-proxy) is the way to it.
MODEL_HOSTS="ollama host.docker.internal"

echo "# rendered by works-egress/render.sh from WORKS_EGRESS_ALLOW; do not edit"
for h in $ALWAYS; do echo "$h"; done

seen=" $ALWAYS "
IFS=','
for raw in ${WORKS_EGRESS_ALLOW:-}; do
  h=$(printf '%s' "$raw" | tr -d '[:space:]')
  [ -n "$h" ] || continue
  # A hostname: labels of [a-z0-9-], joined by dots, nothing else.
  case "$h" in
    *://*|*/*|*:*|*'*'*|*'?'*)
      echo "WORKS_EGRESS_ALLOW: not a bare hostname: $raw" >&2; exit 2 ;;
  esac
  if ! printf '%s' "$h" | grep -Eq '^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$'; then
    echo "WORKS_EGRESS_ALLOW: not a bare hostname: $raw" >&2; exit 2
  fi
  if printf '%s' "$h" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "WORKS_EGRESS_ALLOW: not a bare hostname (an address): $raw" >&2; exit 2
  fi
  for m in $MODEL_HOSTS; do
    if [ "$h" = "$m" ]; then
      echo "WORKS_EGRESS_ALLOW: $raw is the model host; a sandbox reaches the model through the gateway (litellm-proxy), not directly" >&2; exit 2
    fi
  done
  case "$seen" in *" $h "*) continue ;; esac
  seen="$seen$h "
  echo "$h"
done
```

Make it executable: `chmod +x deploy/box/works-egress/render.sh`.

Note on `ollama:11434`: the `*:*` case catches it as "not a bare hostname" before the model-host check. The test accepts either message for that input — re-read `test_the_model_host_cannot_be_allowed_directly`: it asserts `"gateway" in r.stderr.lower()` for all three. So the port form must also reach the model-host message. Adjust: strip a trailing `:[0-9]+` into a separate variable *before* the syntax check, and if the remaining host is a model host, emit the gateway message; otherwise refuse the port form as not bare. Concretely, replace the `case "$h" in` block with:

```sh
  port_stripped=${h%%:*}
  for m in $MODEL_HOSTS; do
    if [ "$port_stripped" = "$m" ]; then
      echo "WORKS_EGRESS_ALLOW: $raw is the model host; a sandbox reaches the model through the gateway (litellm-proxy), not directly" >&2; exit 2
    fi
  done
  case "$h" in
    *://*|*/*|*:*|*'*'*|*'?'*)
      echo "WORKS_EGRESS_ALLOW: not a bare hostname: $raw" >&2; exit 2 ;;
  esac
```

and delete the later `for m in $MODEL_HOSTS` loop (it is now redundant).

- [ ] **Step 4: Run — pass**

Run: `python3 deploy/box/works-egress/test_render.py`
Expected: five `PASS:` lines, exit 0.

- [ ] **Step 5: Wire it into box CI**

In `.github/workflows/box-ci.yml`, next to the `nufi-cron scheduler` step:

```yaml
      - name: works-egress renderer
        run: python3 deploy/box/works-egress/test_render.py
```

- [ ] **Step 6: Commit**

```bash
git add deploy/box/works-egress/render.sh deploy/box/works-egress/test_render.py .github/workflows/box-ci.yml
git commit -m "feat(box): the egress allow list, rendered

One host per line for tinyproxy's filter. Two are always there and not the
operator's to remove -- the Works server a sandbox reports to, and the
gateway the model is reached through -- and the model host can never be
added: a sandbox that reaches Ollama directly is outside the gateway's
limits and guardrails, which is the reason the gateway is on the list.

Bare hostnames only. Where untrusted code may talk to is not a place to be
generous with syntax, so a scheme, path, port, glob or address is refused
with the offending entry named."
```

---

### Task 2: The proxy image and the compose service

**Files:**
- Create: `deploy/box/works-egress/Dockerfile`, `deploy/box/works-egress/entrypoint.sh`
- Modify: `deploy/box/docker-compose.yml`, `deploy/box/.env.example`, `deploy/box/tests/test_compose.py`, `.github/workflows/box-images.yml`

**Interfaces:**
- Consumes: `render.sh` (Task 1).
- Produces: compose network `works-sandbox` (literal name, internal); service `works-egress` on networks `box` and `works-sandbox`, listening on 3128, image `${NUFI_REGISTRY:-ghcr.io/dudaji-vn}/nufi-works-egress:${NUFI_WORKS_EGRESS_TAG:-main}`.

- [ ] **Step 1: Write the failing compose tests**

Append to `deploy/box/tests/test_compose.py` (read the file's `render()` helper and `NUFI_SERVICES` first; add `"works-egress"` to `NUFI_SERVICES` so the registry-override test covers it):

```python
def test_the_sandbox_network_is_internal_and_literally_named():
    """Piece A's provider hard-codes the network name; compose would prefix it.

    `internal: true` is the whole fail-closed argument: a sandbox on this
    network has no route out except through a member that is also on the box
    network -- and the proxy is the only such member.
    """
    cfg = render()
    net = cfg["networks"]["works-sandbox"]
    assert net.get("name") == "works-sandbox", net
    assert net.get("internal") is True, net


def test_the_egress_proxy_sits_on_both_networks_and_publishes_nothing():
    cfg = render()
    svc = cfg["services"]["works-egress"]
    assert set(svc["networks"]) == {"box", "works-sandbox"}, svc["networks"]
    assert "ports" not in svc, "the proxy is reached from the sandbox network only"
    env = svc["environment"]
    assert "WORKS_EGRESS_ALLOW" in env
    assert svc["image"].startswith("ghcr.io/dudaji-vn/nufi-works-egress:")


def test_no_other_service_is_on_the_sandbox_network():
    """The only member with a route out must be the proxy. A second member on
    both networks is a second door."""
    cfg = render()
    on_sandbox = [n for n, s in cfg["services"].items() if "works-sandbox" in (s.get("networks") or {})]
    assert on_sandbox == ["works-egress"], on_sandbox
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd deploy/box && uvx pytest@8.3.4 tests/test_compose.py -q -k "sandbox_network or egress_proxy"`
Expected: FAIL — `KeyError: 'works-sandbox'` / `'works-egress'`.

- [ ] **Step 3: The image**

`deploy/box/works-egress/Dockerfile`:

```dockerfile
# works-egress -- the one way out of the sandbox network.
#
# tinyproxy, with its filter rendered at start from WORKS_EGRESS_ALLOW. Pinned
# by digest like every third-party image the box runs.
FROM alpine:3.20@sha256:de4fe7064d8f98419ea6b49190df1abbf43450c1702eeb864fe9ced453c1cc5f
RUN apk add --no-cache tinyproxy=1.11.1-r3 \
 && mkdir -p /etc/tinyproxy /var/log/tinyproxy /run/tinyproxy \
 && chown -R tinyproxy:tinyproxy /etc/tinyproxy /var/log/tinyproxy /run/tinyproxy
COPY render.sh entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/render.sh /usr/local/bin/entrypoint.sh
USER tinyproxy
EXPOSE 3128
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
  CMD wget -qO- --proxy=on -e http_proxy=http://127.0.0.1:3128 http://litellm-proxy:4000/health/liveliness >/dev/null 2>&1 || exit 1
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
```

Before committing, resolve the two pins: `docker pull alpine:3.20` and read the digest; `docker run --rm alpine:3.20 sh -c 'apk update >/dev/null && apk policy tinyproxy'` and take the exact version string. Put the real values in.

`deploy/box/works-egress/entrypoint.sh`:

```sh
#!/bin/sh
# Render the allow list, write tinyproxy's config, start it in the foreground.
#
# Rendered at container start rather than baked in, so changing
# WORKS_EGRESS_ALLOW in .env is `nufi-box restart works-egress` and not an
# image rebuild -- the same reason nufi-cron re-reads schedules.ini.
set -eu
/usr/local/bin/render.sh > /etc/tinyproxy/filter

cat > /etc/tinyproxy/tinyproxy.conf <<EOF
User tinyproxy
Group tinyproxy
Port 3128
# Only the sandbox network may use this proxy. The box network is where the
# proxy goes OUT; nothing on it needs to come IN through here.
Listen 0.0.0.0
Timeout 600
# Refusals are the one thing this design has that Cilium's does not: an
# answer to "what did that agent try to reach". To stderr, so it lands in
# \`nufi-box logs works-egress\` and under the box's bounded log rotation.
LogFile /dev/stderr
LogLevel Connect
MaxClients 64
# The filter: exact hostnames, default deny. FilterExtended Off is what makes
# "pypi.org" match pypi.org and not evil-pypi.org.
Filter /etc/tinyproxy/filter
FilterDefaultDeny Yes
FilterExtended Off
FilterURLs Off
FilterCaseSensitive Off
# CONNECT (what HTTPS uses) only to the ports the allowed hosts actually
# serve: 443 for the world, 3100 for Works, 4000 for the gateway.
ConnectPort 443
ConnectPort 3100
ConnectPort 4000
# No Via / X-Tinyproxy headers: a sandbox does not need to learn the proxy's
# name from its own responses.
DisableViaHeader Yes
ViaProxyName "works-egress"
EOF

exec tinyproxy -d -c /etc/tinyproxy/tinyproxy.conf
```

Check tinyproxy 1.11's config keywords against the version you pinned (`docker run --rm <image> tinyproxy -h`, and the man page in the package): `FilterDefaultDeny`, `FilterExtended`, `FilterURLs`, `ConnectPort`, `DisableViaHeader` all exist in 1.11; if the pinned build lacks one, drop that line and say so in the commit.

- [ ] **Step 4: The compose service and network**

In `deploy/box/docker-compose.yml`:

Under `networks:` add:

```yaml
  # Where every Works sandbox lives. `internal: true` is the whole fail-closed
  # argument: nothing on this network has a route out unless it is also on
  # `box`, and the only member that is, is works-egress. The literal `name:`
  # matters -- the sandbox provider hard-codes "works-sandbox" (its
  # SANDBOX_NETWORK constant), and without it compose would create
  # nufi-box_works-sandbox and every sandbox would fail to start.
  works-sandbox:
    name: works-sandbox
    driver: bridge
    internal: true
```

After the `nufi-cron` service add:

```yaml
  # The one way out of the sandbox network: a forward proxy that consults an
  # allow list and refuses everything else with a 403 it logs by hostname.
  # Idle until a sandbox exists -- piece C is what puts sandboxes on this box.
  works-egress:
    image: ${NUFI_REGISTRY:-ghcr.io/dudaji-vn}/nufi-works-egress:${NUFI_WORKS_EGRESS_TAG:-main}
    restart: unless-stopped
    logging: *box-logging
    environment:
      # Bare hostnames, comma-separated, empty by default. `works` and
      # `litellm-proxy` are always allowed and the model host never is; see
      # works-egress/render.sh.
      WORKS_EGRESS_ALLOW: ${WORKS_EGRESS_ALLOW:-}
    networks: [box, works-sandbox]
```

Add the healthcheck if `test_every_service_follows_the_house_rules` requires one in compose (the Dockerfile has one; check whether the test reads `healthcheck:` from compose or accepts the image's).

In `deploy/box/.env.example`, after `NUFI_CRON_TAG=main`:

```
NUFI_WORKS_EGRESS_TAG=main
# Hostnames a Works sandbox may reach beyond the gateway and the Works server.
# Comma-separated, bare names, empty by default. The model host is never
# allowed here: sandboxes reach the model through the gateway.
WORKS_EGRESS_ALLOW=
```

- [ ] **Step 5: Run the compose tests — all of them**

Run: `cd deploy/box && docker compose -f docker-compose.yml config >/dev/null && uvx pytest@8.3.4 tests/test_compose.py -q`
Expected: PASS including the three new tests and the existing house-rules test. If `test_every_service_follows_the_house_rules` fails on the new service, read what it demands and satisfy it — do not weaken the test.

- [ ] **Step 6: Build the image locally and prove the two properties**

```bash
cd deploy/box && docker build -t nufi-works-egress:local works-egress
docker network create --internal probe-sandbox 2>/dev/null || true
docker run -d --rm --name egress-probe --network box_probe_unused 2>/dev/null; true
```

Instead of the above, use the compose stack itself — it is running on the development box:

```bash
cd deploy/box
NUFI_WORKS_EGRESS_TAG=local docker compose -f docker-compose.yml up -d works-egress
docker compose -f docker-compose.yml ps works-egress          # healthy
# 1. an allowed host, through the proxy, from the sandbox network
docker run --rm --network works-sandbox alpine:3.20 \
  sh -c 'wget -qO- -e http_proxy=http://works-egress:3128 http://litellm-proxy:4000/health/liveliness' && echo "ALLOWED: gateway reachable"
# 2. a refused host: 403, and the hostname in the proxy's log
docker run --rm --network works-sandbox alpine:3.20 \
  sh -c 'wget -qO- -e http_proxy=http://works-egress:3128 http://example.com 2>&1 | head -2'
docker compose -f docker-compose.yml logs works-egress --since 1m | grep -i example.com && echo "LOGGED: the refused hostname"
# 3. fail closed: no proxy, no route
docker run --rm --network works-sandbox alpine:3.20 \
  sh -c 'wget -T 5 -qO- http://example.com >/dev/null 2>&1 && echo "FAIL: got out without the proxy" || echo "CLOSED: no route without the proxy"'
```

Paste all three results in the commit body. Then `docker compose -f docker-compose.yml rm -sf works-egress` and unset the local tag; the merged image will come from CI.

- [ ] **Step 7: Build it in CI**

In `.github/workflows/box-images.yml`, in the matrix after `nufi-cron`:

```yaml
          - name: nufi-works-egress
            context: deploy/box/works-egress
            file: deploy/box/works-egress/Dockerfile
            tagprefix: ''
```

and add `'deploy/box/works-egress/**'` to the workflow's `paths:` list.

- [ ] **Step 8: Commit**

```bash
git add deploy/box/works-egress/Dockerfile deploy/box/works-egress/entrypoint.sh deploy/box/docker-compose.yml deploy/box/.env.example deploy/box/tests/test_compose.py .github/workflows/box-images.yml
git commit -m "feat(box): the works-sandbox network and the works-egress proxy

An internal network every Works sandbox lives on, and the one member of it
that also has a route out: tinyproxy with its allow list rendered at start
from .env, default deny, refusals logged by hostname to stderr.

The network is named with a compose literal, because the sandbox provider
hard-codes works-sandbox and compose would otherwise prefix it -- every
sandbox would then fail to start, which is the safe direction but not the
intended one. A test pins the literal, the internal flag, and that no
service but the proxy is on both networks: a second member with a route
out is a second door.

Proved on the development box: <paste the three results>"
```

---

### Task 3: `doctor`, the README, and the gate

**Files:**
- Modify: `deploy/box/nufi-box` (the `doctor` case), `deploy/box/tests/test_nufi_box.py`, `deploy/box/README.md`

**Interfaces:**
- Consumes: the `works-egress` service (Task 2).
- Produces: a doctor line `ok  works-egress refuses what it should` / `!!  works-egress …`.

- [ ] **Step 1: Write the failing test**

Append to `deploy/box/tests/test_nufi_box.py`:

```python
def test_doctor_checks_the_egress_proxy_refuses(tmp_path):
    """A proxy that lets everything through looks identical to one that
    works, from the box. Doctor asks it for a host that is not on the list
    and expects a 403 -- the one answer that proves the filter is loaded."""
    r = cli("doctor", NUFI_BOX_ENV=str(_env(tmp_path)))
    assert "works-egress" in r.stdout, r.stdout
    assert "403" in r.stdout or "refuses" in r.stdout, r.stdout
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd deploy/box && uvx pytest@8.3.4 tests/test_nufi_box.py -q -k egress`
Expected: FAIL — no `works-egress` line in doctor's dry-run plan.

- [ ] **Step 3: Add the check**

In `deploy/box/nufi-box`, in the `doctor)` case, after the `nufi.local` announce check and before `All good.`:

```sh
    # The egress proxy, asked for a host that is not on its list. A proxy that
    # lets everything through is indistinguishable from a healthy one by any
    # other check; the 403 is the one answer that proves the filter loaded.
    # Run from inside the sandbox network, which is the only place a sandbox
    # ever stands. Skipped when the service is not part of this box.
    if $COMPOSE ps --services 2>/dev/null | grep -qx works-egress; then
      if [ "$DRY" = 1 ]; then
        printf '  $ ask works-egress for a host not on the list, expect 403 (refuses)\n'
      else
        _code=$(docker run --rm --network works-sandbox alpine:3.20 \
          sh -c 'wget -S -T 5 -O /dev/null -e http_proxy=http://works-egress:3128 http://example.invalid 2>&1 | sed -n "s/.*HTTP\/[0-9.]* \([0-9]*\).*/\1/p" | head -1' 2>/dev/null)
        if [ "$_code" = "403" ]; then echo " ok  works-egress refuses a host not on the list (403)"
        else echo " !!  works-egress answered ${_code:-nothing} for a host not on the list; the filter may not be loaded — run: nufi-box logs works-egress"; fail=1; fi
      fi
    fi
```

The dry-run line contains the word `refuses`, which the test accepts.

- [ ] **Step 4: Run — pass, and the whole box suite**

Run: `cd deploy/box && uvx pytest@8.3.4 tests -q`
Expected: all green (the suite is ~180 tests and takes ~80 s).

- [ ] **Step 5: Run doctor on the live box**

Run: `cd deploy/box && ./nufi-box doctor | tail -4`
Expected: the new `ok  works-egress refuses …` line, provided Task 2's service is up from the merged image (or bring it up with the local tag for this check).

- [ ] **Step 6: README**

In `deploy/box/README.md`, after the "Running them on a clock" section, add:

```markdown
### Works sandboxes and where they may reach

A NUFI Works sandbox — the container an agent's code runs in — lives on the
`works-sandbox` network, which has no route out. The only exit is
`works-egress`, a proxy that consults an allow list and refuses everything
else with a 403 it logs by hostname:

```sh
nufi-box logs works-egress       # every refusal, with the hostname the agent tried
```

Two hosts are always allowed and are not yours to remove: the Works server the
sandbox reports to, and the gateway the model is reached through. Everything
else comes from `.env`:

```
WORKS_EGRESS_ALLOW=pypi.org,files.pythonhosted.org
```

Bare hostnames, comma-separated. A scheme, a path, a port, a glob or an
address is refused at start with the entry named, and so is the model host —
a sandbox reaches the model through the gateway or not at all, which keeps
every model call inside the same limits and guardrails as a chat.

If the proxy is down, sandboxes have no network rather than an unfiltered
one. `nufi-box doctor` asks the proxy for a host that is not on the list and
expects the 403 — the one answer that proves the filter is loaded, since a
proxy that lets everything through looks healthy by every other measure.

Nothing here runs an agent yet: the sandboxes themselves arrive with the next
piece, which installs the provider and registers the environment.
```

- [ ] **Step 7: Gate and commit**

Run from `deploy/box`: `uvx pytest@8.3.4 tests -q` and `python3 works-egress/test_render.py`, and from the repo root `docker compose -f deploy/box/docker-compose.yml config >/dev/null`. All green.

```bash
git add deploy/box/nufi-box deploy/box/tests/test_nufi_box.py deploy/box/README.md
git commit -m "feat(box): doctor proves the egress filter is loaded

A proxy that lets everything through is indistinguishable from a healthy
one by every other check. Doctor asks works-egress, from inside the sandbox
network, for a host that is not on the list and expects the 403 -- the one
answer that proves the filter loaded. Skipped on a box without the
service. The README says where a sandbox may reach and how to widen it."
```

Do not open the PR; the controller does.

---

## Self-review

**Spec coverage.** Section B: "tinyproxy, on both networks, config rendered at start from an allow list" — Task 2. "Only member of the sandbox network that also has a route out" — Task 2's `test_no_other_service_is_on_the_sandbox_network`. The allow-list table: `works:3100` and `litellm-proxy:4000` always (Task 1's `ALWAYS`, Task 2's `ConnectPort`s), operator list from `WORKS_EGRESS_ALLOW` (Task 1). "Refused with 403 and logged by hostname" — `FilterDefaultDeny` + `LogLevel Connect` to stderr, proved in Task 2 Step 6 and checked by doctor in Task 3. "No proxy for the model host directly" — Task 1's `MODEL_HOSTS` refusal and test. "Fail closed is structural" — `internal: true` pinned by test, proved in Task 2 Step 6 part 3. Testing section B: "a rendered config is asserted from an allow list… one renderer, no second copy" — Task 1 (render.sh is the one renderer; the entrypoint and the test both call it); "on a box, an allowed host gets through, an unlisted one gets 403, with the proxy stopped nothing gets out" — Task 2 Step 6. Covered.

**Placeholders.** Two pins (`alpine` digest, `tinyproxy` version) are marked to be resolved by running the named commands — a verification instruction with the exact command, not a deferral. The commit body's `<paste the three results>` is filled by Step 6's output. No other placeholders.

**Type consistency.** Network `works-sandbox` (Task 2 compose `name:`) = piece A's `SANDBOX_NETWORK`. Service `works-egress`, port `3128` = piece A's `DEFAULTS.egressProxy`. `WORKS_EGRESS_ALLOW` is the same variable in `render.sh`, compose `environment`, `.env.example`, and the README. `NUFI_SERVICES` gains `"works-egress"` so the registry-override test covers the new image name `nufi-works-egress`, which matches the box-images matrix entry.
