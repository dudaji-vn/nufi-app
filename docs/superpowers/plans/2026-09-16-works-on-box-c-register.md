# Works on the box — piece C: the box runs Works and registers the Docker environment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A box installed with `install-box.sh --with-works` runs NUFI Works behind `https://<box>:3003`, and every agent run on it lands in a gVisor sandbox on the internal network behind the egress proxy — registered by the box itself, with no human step and no change to `apps/agents`.

**Architecture:** Four box-side pieces. (1) A sandbox image the box builds and publishes (`nufi-sandbox`). (2) Compose wiring behind profile `works`: the `works` service (upstream's image, Docker socket, uid 1000 + docker group), Caddy's sixth port, the console's Works door, the box's own adapter file. (3) `install-box.sh --with-works`, which installs a pinned `runsc` as a Docker runtime and turns the profile on. (4) `nufi-box works install`, a bash wrapper around a stdlib Python registrar that signs in as the box admin through the same SSO path a browser takes, claims first admin, mints a board key and a LiteLLM virtual key, installs the provider plugin, creates the box's company and the Docker environment, makes it the instance default and archives `Local`. `doctor` checks all of it; the Ubuntu VM acceptance runs `uname -r` inside a sandbox and expects gVisor.

**Tech Stack:** docker compose profiles, bash 3.2 (`nufi-box`, `install-box.sh`), Python 3 stdlib (`register_works.py`, run inside the box network via `docker compose run`), gVisor `runsc` release tarball, the box's pytest suite (`uvx pytest@8.3.4 tests -q` from `deploy/box`), stdlib fake-API tests in the shape of `deploy/platform/adapters/nufi-cron/test_nufi_cron.py`.

**Spec:** `docs/superpowers/specs/2026-09-16-works-on-box-design.md` — section "C — the box registers the Docker environment", "On the box", "Testing", and the **Addendum** (the six decisions this plan implements). Pieces A (#119, the provider at `apps/agents/packages/plugins/sandbox-providers/docker/`) and B (#120, `works-egress` + `works-sandbox`) are merged.

## Global Constraints

- **Nothing under `apps/agents` changes.** The provider's config contract is fixed by A: `config.provider = "docker"`, `config.image` must be a pinned reference, `egressProxy` defaults to `works-egress:3128`. The plugin's package name is `@nufi/plugin-docker-sandbox`, its path in the Works image is `/app/packages/plugins/sandbox-providers/docker`, its manifest `driverKey` is `docker`.
- **Profile `works`.** `works` and `works-egress` carry `profiles: [works]`; `nufi-box` and `install-box.sh` add `--profile works` when `NUFI_WORKS=1` is in `.env`. A box without `--with-works` renders the same services it renders today.
- **Ubuntu only.** `--with-works` on Darwin dies with a message naming Docker Desktop; it never installs `runsc` there.
- **gVisor pinned:** release `20260907`, tarball `https://storage.googleapis.com/gvisor/releases/release/20260907/<ARCH>/gvisor.tar.bz2`, sha512 (of the tarball) `x86_64 c38cc38ee709d862501e55eebd99f5bd105899cbc7cf3fa1f620493fa127364c5b74c7361d231bd8b9523be48918ea3820dd40b28c61c2b2cb644edbf10261fb`, `aarch64 fce113699d2e722785e0f66718def9b287cfeef92bd5694da5830ec0c2107d26da94d050e9e6ce68ae65212c437b4eb8f64b67b34add7b04637f4dd12befa2f4`; the member to extract is `runsc` at the tarball root; installed at `/usr/local/bin/runsc`; `daemon.json` gains `runtimes.runsc.path` by a merge (the `insecure-registries` precedent at `install-box.sh:455`), then `systemctl restart docker`.
- **Works env is fixed:** `PAPERCLIP_DEPLOYMENT_MODE=authenticated`, `PAPERCLIP_DEPLOYMENT_EXPOSURE=private`, `PAPERCLIP_PUBLIC_URL=https://${BOX_HOST}:3003`, `PAPERCLIP_AUTH_DISABLE_SIGN_UP=true`, `PAPERCLIP_DISABLE_PLUGIN_AUTOBUILD=1`, `NUFI_OIDC_ISSUER=https://${BOX_HOST}:3001`, `NUFI_OIDC_CLIENT_ID=nufi-works`, `NODE_EXTRA_CA_CERTS=/caddy/caddy/pki/authorities/local/root.crt`. Runs as `user: "1000:1000"` with `group_add: ["${DOCKER_GID}"]`. Only `works` mounts `/var/run/docker.sock`.
- **Registration is idempotent by lookup, never by count:** plugin by `packageName`, company by "any exists", environment by `driver == "sandbox" && config.provider == "docker"`, `Local` by `driver == "local" && status == "active"`. A second run creates nothing and exits 0.
- **Secrets never appear in a process argument.** `ADMIN_PASSWORD`, `LITELLM_MASTER_KEY`, `WORKS_BOX_KEY` reach the registrar through the environment (`docker compose run -e`); minted keys come back on stdout as `KEY=VALUE` lines the wrapper writes with `envfile_set`.
- **The sandbox image is registered by digest** (`WORKS_SANDBOX_IMAGE` in `.env`, e.g. `ghcr.io/dudaji-vn/nufi-sandbox@sha256:…`), resolved from `docker image inspect` after the installer pulls the tag.
- Every new third-party base is pinned by digest. Tests run with `uvx pytest@8.3.4 tests -q` from `deploy/box`; compose validity with `docker compose --project-directory deploy/box -f deploy/box/docker-compose.yml --profile works config >/dev/null`. Commit messages in English, no AI-authorship framing.
- The mesh Caddy stamp: `MESH_CADDY_REV` goes `3 → 4` in `lib/mesh.sh` **and** `caddy/mesh.caddy.empty` (`tests/test_caddyfile.py:74-78` pins that they agree).

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `deploy/box/sandbox/Dockerfile` | the image a sandbox runs: Ubuntu 24.04, GNU coreutils, Node 22, git, the three harness CLIs, uid 1000, `/workspace` | create |
| `.github/workflows/box-images.yml` | build+push `nufi-sandbox` (multi-arch) | modify |
| `.github/workflows/box-ci.yml` | a job that builds the sandbox image and asserts GNU `timeout`, uid 1000, the CLIs | modify |
| `deploy/box/works/adapters.json` | the box's adapter registry: every enabled adapter reaches only `litellm-proxy:4000` | create |
| `deploy/box/works/test_adapters.py` | stdlib: the gateway invariant on the box's file | create |
| `deploy/box/works/register_works.py` | the registrar (stdlib; runs inside the box network) | create |
| `deploy/box/works/test_register_works.py` | fake chat + console + Works + LiteLLM on one `http.server`; first run registers, second run creates nothing | create |
| `deploy/box/lib/works.sh` | `works_install`, `works_status`: wait for Works, ensure the DB, run the registrar, write minted keys to `.env`, recreate `works` when the model key is new | create |
| `deploy/box/docker-compose.yml` | `works` service, `works` profile on both services, `works-data` volume, console env, Caddy `:3003` port | modify |
| `deploy/box/docker-compose.emulate.yml` | `works: platform: linux/amd64` (the Works image is amd64-only) | modify |
| `deploy/box/Caddyfile`, `deploy/box/lib/mesh.sh`, `deploy/box/caddy/mesh.caddy.empty` | the sixth product port, on the LAN and the mesh; rev 4 | modify |
| `deploy/box/scripts/postgres-init.sh` | `nufi_works` on a fresh box | modify |
| `deploy/box/.env.example` | the new keys | modify |
| `deploy/box/nufi-box` | `--profile works` in `$COMPOSE`; `works install|status` verbs; three doctor checks | modify |
| `deploy/box/install-box.sh` | `--with-works`: refuse on Darwin, install `runsc`, `DOCKER_GID`, secrets, `NUFI_WORKS=1`, pull + pin the sandbox image, delegate to `nufi-box works install` | modify |
| `deploy/box/tests/test_compose.py`, `test_caddyfile.py`, `test_install.py`, `test_nufi_box.py` | the tests named in each task | modify |
| `.github/workflows/gvisor-probe.yml` | one `docker run` with A's exact HostConfig under runsc | modify |
| `deploy/box/tests/vm/verify-ubuntu-box.sh` | a Works step on a `--with-works` box: `uname -r` in a sandbox says gvisor | modify |
| `deploy/box/README.md`, `apps/docs/content/docs/box/works.mdx`, `apps/docs/content/docs/box/meta.json` | docs | modify / create |

---

### Task 1: The sandbox image

**Files:**
- Create: `deploy/box/sandbox/Dockerfile`
- Modify: `.github/workflows/box-images.yml`, `.github/workflows/box-ci.yml`

**Interfaces:**
- Produces: `ghcr.io/dudaji-vn/nufi-sandbox:main` (amd64 + arm64), user `1000:1000`, `WORKDIR /workspace`, GNU coreutils `timeout` on PATH, `codex`, `claude`, `opencode`, `git`, `node` on PATH. Task 4 pulls it; Task 5 registers its digest.

- [ ] **Step 1: Write the failing CI check**

In `.github/workflows/box-ci.yml`, add a second job after `tests:`:

```yaml
  sandbox-image:
    name: Sandbox image
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      # Built here, for this runner's platform only; box-images publishes the
      # multi-arch one. What is asserted is the contract piece A's provider
      # relies on and nothing else in CI would notice going missing:
      # GNU coreutils' timeout (busybox's cannot signal a process group the
      # way the exec wrapper needs), the harness CLIs on PATH, uid 1000.
      - name: Build
        run: docker build -t nufi-sandbox:ci deploy/box/sandbox
      - name: The image keeps the sandbox contract
        run: |
          set -euo pipefail
          docker run --rm nufi-sandbox:ci timeout --version | head -1 | grep -q 'GNU coreutils'
          docker run --rm nufi-sandbox:ci sh -c 'id -u' | grep -qx 1000
          docker run --rm nufi-sandbox:ci sh -c 'pwd' | grep -qx /workspace
          for cli in codex claude opencode git node; do
            docker run --rm nufi-sandbox:ci sh -c "command -v $cli" >/dev/null || { echo "$cli not on PATH"; exit 1; }
          done
          echo "PASS: GNU timeout, uid 1000, /workspace, codex claude opencode git node"
```

- [ ] **Step 2: Verify it fails**

Run: `docker build -t nufi-sandbox:ci deploy/box/sandbox` from the repo root.
Expected: FAIL — `deploy/box/sandbox` does not exist.

- [ ] **Step 3: Write the Dockerfile**

`deploy/box/sandbox/Dockerfile`:

```dockerfile
# nufi-sandbox -- what an agent's code runs in on the box.
#
# One image for every coding harness the box's adapter file enables, because
# the Docker provider (apps/agents/packages/plugins/sandbox-providers/docker)
# takes one image per environment. Upstream's per-adapter runtime images are
# Ubuntu + Node + one CLI each; this is the union, on the box's own base.
#
# Ubuntu, not Alpine, on purpose: the provider wraps every exec in GNU
# coreutils' `timeout -s KILL`, and busybox's timeout cannot signal the way
# the deadline needs (see the provider's README, "The deadline").
FROM ubuntu:24.04@sha256:69cecf4bbf72d2d44a9eef1b71fb98c7fb973d78af11399deccef19beb008ad9

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg git ripgrep python3 \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# The three harnesses the box enables (works/adapters.json). Exact versions:
# a sandbox that pulls "latest" at build time is a sandbox nobody can
# reproduce. Bump on purpose.
RUN npm install -g --omit=dev \
      @openai/codex@0.154.0 \
      @anthropic-ai/claude-code@2.1.273 \
      opencode-ai@1.18.31 \
 && npm cache clean --force

# ubuntu:24.04 ships uid 1000 as `ubuntu`; the provider runs the container as
# whatever the image says, and A's spec says not root.
RUN mkdir -p /workspace && chown 1000:1000 /workspace
USER 1000:1000
WORKDIR /workspace
# The provider sets Cmd to `sleep infinity` and execs into the container; this
# is only what a bare `docker run` of the image does.
CMD ["sleep", "infinity"]
```

- [ ] **Step 4: Build and run the check locally**

Run from the repo root: `docker build -t nufi-sandbox:ci deploy/box/sandbox` then the five-line check from Step 1 verbatim.
Expected: `PASS: GNU timeout, uid 1000, /workspace, codex claude opencode git node`.

- [ ] **Step 5: Publish it from box-images**

In `.github/workflows/box-images.yml`: add `'deploy/box/sandbox/**'` to `paths:`, and in the matrix after `nufi-works-egress`:

```yaml
          - name: nufi-sandbox
            context: deploy/box/sandbox
            file: deploy/box/sandbox/Dockerfile
            tagprefix: ''
```

- [ ] **Step 6: Commit**

```bash
git add deploy/box/sandbox/Dockerfile .github/workflows/box-images.yml .github/workflows/box-ci.yml
git commit -m "feat(box): the sandbox image an agent's code runs in

Ubuntu 24.04 with GNU coreutils -- the provider's exec deadline needs
GNU timeout, not busybox's -- Node 22, git, and the three coding
harnesses the box's adapter file enables, at exact versions. Runs as
uid 1000 in /workspace. Built for amd64 and arm64 by box-images; CI
builds it for the runner and asserts the contract the provider relies
on, which nothing else would notice going missing."
```

---

### Task 2: The box's adapter file

**Files:**
- Create: `deploy/box/works/adapters.json`, `deploy/box/works/test_adapters.py`
- Modify: `.github/workflows/box-ci.yml`

**Interfaces:**
- Produces: `deploy/box/works/adapters.json`, mounted by Task 3 at `/box/adapters.json` (`PAPERCLIP_ADAPTERS_FILE`). Same shape as `apps/agents/nufi/adapters.json`; the registry has replace semantics, so this file is the complete set the box offers.

- [ ] **Step 1: Write the failing test**

`deploy/box/works/test_adapters.py`:

```python
#!/usr/bin/env python3
"""The box's adapter registry keeps every model call on the box's gateway.

apps/agents/nufi/adapters.json does this for the cloud (api.codechi.me);
this is the same invariant for a box, where the gateway is the litellm-proxy
service and nothing else is a model. The registry has replace semantics, so
an adapter absent here is unavailable, not defaulted -- which is why the two
disabled ones are still listed.

Run:  python3 deploy/box/works/test_adapters.py     (exit 0 = PASS)
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
GATEWAY = "http://litellm-proxy:4000"
CLOUD = (HERE / ".." / ".." / ".." / "apps" / "agents" / "nufi" / "adapters.json").resolve()


def load():
    return json.loads((HERE / "adapters.json").read_text())


def test_every_enabled_harness_reaches_only_the_box_gateway():
    for a in load():
        if not a.get("enabled") or a["adapterType"] == "nufi_agent":
            continue
        assert a["allowFqdns"] == ["litellm-proxy"], (a["adapterType"], a.get("allowFqdns"))
        for k, v in a["defaultEnv"].items():
            assert v.startswith(GATEWAY), (a["adapterType"], k, v)
    print("PASS: every enabled harness reaches only litellm-proxy")


def test_the_box_lists_the_same_adapters_as_the_cloud():
    """Same set, same enabled flags: the box offers what the cloud offers, on
    its own gateway. A harness turned on here and not there was never gated."""
    box = {a["adapterType"]: a.get("enabled", False) for a in load()}
    cloud = {a["adapterType"]: a.get("enabled", False) for a in json.loads(CLOUD.read_text())}
    assert set(box) == set(cloud), (sorted(box), sorted(cloud))
    # pi is not in the sandbox image; a harness the image cannot run is not
    # offered, whatever the cloud does.
    assert box.get("pi_local") is False, box.get("pi_local")
    for name in set(box) - {"pi_local"}:
        assert box[name] == cloud[name], (name, box[name], cloud[name])
    print("PASS: the box's adapter set matches the cloud's, pi excepted")


def test_the_probe_commands_name_binaries_the_sandbox_image_has():
    have = {"codex", "claude", "opencode"}
    for a in load():
        if a.get("enabled") and "probeCommand" in a:
            assert a["probeCommand"][0] in have, a["probeCommand"]
    print("PASS: every probe command is a binary the sandbox image installs")


if __name__ == "__main__":
    test_every_enabled_harness_reaches_only_the_box_gateway()
    test_the_box_lists_the_same_adapters_as_the_cloud()
    test_the_probe_commands_name_binaries_the_sandbox_image_has()
```

- [ ] **Step 2: Verify it fails**

Run: `python3 deploy/box/works/test_adapters.py`
Expected: FAIL — `adapters.json` missing.

- [ ] **Step 3: Write the file**

First read `apps/agents/nufi/adapters.json` in full — the box's file must list exactly the same `adapterType`s with the same `enabled` values (the second test pins this; the cloud file has `pi_local` enabled and `cursor_local`/`gemini_local` present but disabled, if it does — copy what is there). `deploy/box/works/adapters.json`:

```json
[
  {
    "adapterType": "claude_local",
    "enabled": true,
    "envKeys": ["ANTHROPIC_API_KEY"],
    "allowFqdns": ["litellm-proxy"],
    "probeCommand": ["claude", "--version"],
    "defaultEnv": { "ANTHROPIC_BASE_URL": "http://litellm-proxy:4000" }
  },
  {
    "adapterType": "codex_local",
    "enabled": true,
    "envKeys": ["OPENAI_API_KEY"],
    "allowFqdns": ["litellm-proxy"],
    "probeCommand": ["codex", "--version"],
    "defaultEnv": { "OPENAI_BASE_URL": "http://litellm-proxy:4000/v1" }
  },
  {
    "adapterType": "opencode_local",
    "enabled": true,
    "envKeys": ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"],
    "allowFqdns": ["litellm-proxy"],
    "probeCommand": ["opencode", "--version"],
    "defaultEnv": {
      "ANTHROPIC_BASE_URL": "http://litellm-proxy:4000",
      "OPENAI_BASE_URL": "http://litellm-proxy:4000/v1"
    }
  },
  {
    "adapterType": "pi_local",
    "enabled": false,
    "allowFqdns": ["litellm-proxy"]
  },
  {
    "adapterType": "nufi_agent",
    "enabled": true
  }
]
```

Then reconcile with the cloud file: every adapter the cloud file lists appears here with the same `enabled`, except `pi_local`, which is **disabled** on the box because the sandbox image does not ship `pi` (Task 1). If the cloud file lists adapters this draft does not (e.g. `cursor_local`, `gemini_local`, disabled), add them here with the same flag and `"allowFqdns": ["litellm-proxy"]`. Do not add `pi` to the image.

- [ ] **Step 4: Run — pass; wire CI**

Run: `python3 deploy/box/works/test_adapters.py` → three `PASS:` lines.
In `.github/workflows/box-ci.yml`, next to `works-egress renderer`: `- name: works adapter file` / `run: python3 deploy/box/works/test_adapters.py`.

- [ ] **Step 5: Commit**

```bash
git add deploy/box/works/adapters.json deploy/box/works/test_adapters.py .github/workflows/box-ci.yml
git commit -m "feat(box): the adapter registry for Works on a box

The cloud's file keeps every harness on api.codechi.me; this one keeps
it on litellm-proxy, the box's gateway, where the guardrails run. Same
adapters, same enabled flags, except pi, which the sandbox image does
not ship. A test pins the invariant and the parity."
```

---

### Task 3: The `works` service, the profile, the sixth port

**Files:**
- Modify: `deploy/box/docker-compose.yml`, `deploy/box/docker-compose.emulate.yml`, `deploy/box/Caddyfile`, `deploy/box/lib/mesh.sh`, `deploy/box/caddy/mesh.caddy.empty`, `deploy/box/scripts/postgres-init.sh`, `deploy/box/.env.example`, `deploy/box/nufi-box` (the `$COMPOSE` assembly only), `deploy/box/tests/test_compose.py`, `deploy/box/tests/test_caddyfile.py`

**Interfaces:**
- Consumes: Task 2's `works/adapters.json`.
- Produces: service `works` (profile `works`, port 3100 internal, `https://${BOX_HOST}:3003` outside), volume `works-data`, env keys `NUFI_WORKS`, `NUFI_WORKS_TAG`, `NUFI_SANDBOX_TAG`, `WORKS_AUTH_SECRET`, `WORKS_OIDC_SECRET`, `WORKS_PUBLIC_URL`, `WORKS_MODEL_KEY`, `WORKS_BOX_KEY`, `WORKS_SANDBOX_IMAGE`, `DOCKER_GID`. `nufi-box`'s `$COMPOSE` carries `--profile works` when `NUFI_WORKS=1`.

- [ ] **Step 1: Write the failing compose tests**

In `deploy/box/tests/test_compose.py`: add `"works"` to `NUFI_SERVICES`; change the three piece-B tests (`test_the_sandbox_network_is_internal_and_literally_named`, `test_the_egress_proxy_sits_on_both_networks_and_publishes_nothing`, `test_no_other_service_is_on_the_sandbox_network`) to `render(profiles=("works",))`; in `test_every_service_follows_the_house_rules` add `"works"` to the profiles tuple; in `test_images_come_from_the_configured_registry` add `"works"` to the profiles of both renders. Then append:

```python
def test_works_and_its_proxy_exist_only_behind_the_works_profile():
    """A box installed without --with-works is byte-for-byte the box that
    ships today: neither the Works server nor the egress proxy."""
    plain = render()["services"]
    assert "works" not in plain and "works-egress" not in plain, sorted(plain)
    with_works = render(profiles=("works",))["services"]
    assert "works" in with_works and "works-egress" in with_works


def test_only_works_holds_the_docker_socket():
    """The socket is root on the box. One service has it, on purpose, and it
    is the one that creates sandboxes as sibling containers."""
    cfg = render("docker-compose.yml", "docker-compose.linux.yml", "docker-compose.gpu.yml",
                 "docker-compose.mesh.yml", profiles=("linux", "gpu", "mesh", "works"))
    holders = sorted(n for n, s in cfg["services"].items()
                     if any(v.get("source") == "/var/run/docker.sock" for v in s.get("volumes") or []))
    assert holders == ["works"], holders


def test_works_runs_as_uid_1000_in_the_docker_group():
    """Upstream's entrypoint drops root with gosu, and gosu resets the
    supplementary groups group_add gave the container. Starting as 1000 makes
    the entrypoint exec directly, and the docker group survives to the plugin
    worker that opens the socket."""
    svc = render(profiles=("works",), DOCKER_GID="988")["services"]["works"]
    assert svc["user"] == "1000:1000", svc.get("user")
    assert svc["group_add"] == ["988"], svc.get("group_add")


def test_works_is_wired_to_the_box_and_nothing_else():
    svc = render(profiles=("works",))["services"]["works"]
    env = svc["environment"]
    assert env["PAPERCLIP_DEPLOYMENT_MODE"] == "authenticated"
    assert env["PAPERCLIP_DEPLOYMENT_EXPOSURE"] == "private"
    assert env["PAPERCLIP_PUBLIC_URL"] == "https://nufi.local:3003"
    assert env["NUFI_OIDC_ISSUER"] == "https://nufi.local:3001"
    assert env["NUFI_OIDC_CLIENT_ID"] == "nufi-works"
    assert env["PAPERCLIP_AUTH_DISABLE_SIGN_UP"] == "true"
    assert env["PAPERCLIP_DISABLE_PLUGIN_AUTOBUILD"] == "1"
    assert env["PAPERCLIP_ADAPTERS_FILE"] == "/box/adapters.json"
    assert env["NODE_EXTRA_CA_CERTS"] == "/caddy/caddy/pki/authorities/local/root.crt"
    assert env["DATABASE_URL"].endswith("@postgres:5432/nufi_works")
    targets = {v["target"]: v for v in svc["volumes"]}
    assert targets["/box/adapters.json"]["read_only"] is True
    assert targets["/caddy"]["read_only"] is True
    assert targets["/paperclip"]["type"] == "volume"
    assert "ports" not in svc
    assert list(svc["networks"]) == ["box"]


def test_the_model_key_in_the_works_env_is_never_the_master_key():
    """That env reaches every sandbox, and litellm-proxy is on the egress
    allow list. A master key there is the gateway's admin API from inside
    untrusted code."""
    text = (BOX / "docker-compose.yml").read_text()
    works = text[text.index("  works:\n"):text.index("  works-egress:\n")]
    assert "LITELLM_MASTER_KEY" not in works
    env = render(profiles=("works",), WORKS_MODEL_KEY="sk-virtual")["services"]["works"]["environment"]
    for k in ("NUFI_MODEL_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        assert env[k] == "sk-virtual", k


def test_the_console_opens_the_works_door_only_when_the_box_has_one():
    plain = render()["services"]["console"]["environment"]
    assert plain["PUBLIC_WORKS_URL"] == ""
    on = render(WORKS_PUBLIC_URL="https://nufi.local:3003")["services"]["console"]["environment"]
    assert on["PUBLIC_WORKS_URL"] == "https://nufi.local:3003"
    clients = json.loads(on["OIDC_CLIENTS"])
    (works,) = [c for c in clients if c["clientId"] == "nufi-works"]
    assert works["product"] == "works"
    assert works["redirectUris"] == ["https://nufi.local:3003/api/auth/oauth2/callback/nufi"]


def test_caddy_publishes_the_works_port():
    ports = {int(p["published"]) for p in render()["services"]["caddy"]["ports"]}
    assert 3003 in ports, ports
```

In `deploy/box/tests/test_caddyfile.py`: change both `(3080, 3001, 3002, 7860, 4000)` tuples to `(3080, 3001, 3002, 3003, 7860, 4000)`, the mesh test's `== 5` to `== 6` and its comment "Five blocks" → "Six blocks", and rename `test_mesh_caddy_serves_the_five_product_ports_on_both_mesh_addresses` → `..._six_...`. Also check `test_caddyfile.py:162` ("all six ports down") still reads right — it counts `:80` plus five; make it "all seven ports".

- [ ] **Step 2: Verify they fail**

Run: `cd deploy/box && uvx pytest@8.3.4 tests/test_compose.py tests/test_caddyfile.py -q`
Expected: the new tests fail (`KeyError: 'works'`, missing 3003); the three piece-B tests fail until the profile exists.

- [ ] **Step 3: The compose changes**

`deploy/box/docker-compose.yml`:

Under `volumes:` add `works-data:` with the comment `# Works' instance state (PAPERCLIP_HOME): plugin records, adapter registrations, logs.`

On `works-egress`, add `profiles: [works]` as its first key and change its comment's last line from `# Idle until a sandbox exists -- piece C is what puts sandboxes on this box.` to `# Behind the works profile with the server it serves; a box without --with-works has neither.`

Before `works-egress`, add:

```yaml
  # NUFI Works: the server behind :3003, and the one service on the box that
  # holds the Docker socket -- it creates every sandbox as a sibling container
  # under runsc on the works-sandbox network, and never runs agent code itself
  # (its upstream Local environment is archived by `nufi-box works install`).
  # The socket is a real grant: whoever holds it can start any container on
  # the box as root. It is accepted here because there is no other way for a
  # container to create sibling containers, and it is stated in the README.
  works:
    profiles: [works]
    image: ${NUFI_REGISTRY:-ghcr.io/dudaji-vn}/nufi-works:${NUFI_WORKS_TAG:-main}
    restart: unless-stopped
    logging: *box-logging
    # uid 1000 from the start, not root-then-gosu: upstream's entrypoint drops
    # privileges with gosu, and gosu resets supplementary groups -- the docker
    # group group_add hands the container would not reach the plugin worker
    # that opens the socket. As 1000 the entrypoint execs directly and the
    # group survives. DOCKER_GID is read from the socket by install-box.sh.
    user: "1000:1000"
    group_add: ["${DOCKER_GID:-999}"]
    depends_on:
      postgres:
        condition: service_healthy
      console:
        condition: service_healthy
      caddy:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://nufi:${POSTGRES_PASSWORD}@postgres:5432/nufi_works
      BETTER_AUTH_SECRET: ${WORKS_AUTH_SECRET}
      PAPERCLIP_DEPLOYMENT_MODE: authenticated
      # private: the first signed-in browser session may claim instance admin.
      # `nufi-box works install` is that session -- signed in as the box admin
      # through the console, exactly as a browser would be.
      PAPERCLIP_DEPLOYMENT_EXPOSURE: private
      PAPERCLIP_PUBLIC_URL: https://${BOX_HOST}:3003
      # The box's own registry (works/adapters.json): every harness on
      # litellm-proxy. Replace semantics -- what is not in the file is not
      # offered.
      PAPERCLIP_ADAPTERS_FILE: /box/adapters.json
      # The provider ships built in the image; a plugin install must never
      # reach for npm from inside a box.
      PAPERCLIP_DISABLE_PLUGIN_AUTOBUILD: "1"
      # Members arrive through the console (SSO). No password sign-ups: on a
      # LAN box, a password account registered under a colleague's address
      # before that colleague first signs in would be theirs to keep.
      PAPERCLIP_AUTH_DISABLE_SIGN_UP: "true"
      NUFI_OIDC_ISSUER: https://${BOX_HOST}:3001
      NUFI_OIDC_CLIENT_ID: nufi-works
      NUFI_OIDC_CLIENT_SECRET: ${WORKS_OIDC_SECRET}
      # The OIDC token exchange goes to the console through Caddy's internal
      # CA (the container resolves ${BOX_HOST} to caddy).
      NODE_EXTRA_CA_CERTS: /caddy/caddy/pki/authorities/local/root.crt
      # A LiteLLM virtual key minted by `nufi-box works install`, under the
      # three names the adapters read. Never the master key: this env reaches
      # every sandbox, and litellm-proxy is on the egress allow list.
      NUFI_MODEL_API_KEY: ${WORKS_MODEL_KEY:-}
      OPENAI_API_KEY: ${WORKS_MODEL_KEY:-}
      ANTHROPIC_API_KEY: ${WORKS_MODEL_KEY:-}
    volumes:
      - works-data:/paperclip
      - ./works/adapters.json:/box/adapters.json:ro
      - caddy-data:/caddy:ro
      - /var/run/docker.sock:/var/run/docker.sock
    healthcheck:
      test: ["CMD-SHELL", "curl -fs http://127.0.0.1:3100/api/health >/dev/null || exit 1"]
      interval: 20s
      timeout: 5s
      retries: 5
      start_period: 60s
    networks: [box]
```

On `console`'s `environment:`, replace the two lines `# Runtime public URLs (Task 2). No Works on the box.` / `PUBLIC_WORKS_URL: ""` with:

```yaml
      # Runtime public URLs. PUBLIC_WORKS_URL is empty on a box without Works;
      # install-box.sh --with-works sets WORKS_PUBLIC_URL and the chooser gets
      # its third door.
      PUBLIC_WORKS_URL: ${WORKS_PUBLIC_URL:-}
      # Works is an OIDC client of this console, the same way it is in the
      # cloud (deploy/railway/agents.md). Registered on every box -- the secret
      # is generated by the installer whether or not Works is installed -- so a
      # box that turns Works on later needs no console change.
      OIDC_CLIENTS: '[{"clientId":"nufi-works","clientSecret":"${WORKS_OIDC_SECRET}","redirectUris":["https://${BOX_HOST}:3003/api/auth/oauth2/callback/nufi"],"product":"works"}]'
```

On `caddy`'s `ports:`, add `- "3003:3003"` after `"3002:3002"`.

In `test_compose.py::test_emulate_layer_only_marks_the_images_published_amd64_only`, render with `profiles=("works",)` as well, assert `svcs["works"]["platform"] == "linux/amd64"`, and add `"works"` to the exclusion set.

`deploy/box/docker-compose.emulate.yml`: append

```yaml
  # nufi-works is published for amd64 only (agents-image.yml). Sandboxes still
  # cannot run on a Mac -- Docker Desktop has no runsc -- so this is for the
  # server alone, on a developer's machine.
  works:
    platform: linux/amd64
```

`deploy/box/scripts/postgres-init.sh`: add `CREATE DATABASE nufi_works;` and `GRANT ALL PRIVILEGES ON DATABASE nufi_works TO ${POSTGRES_USER};` beside the `nufi_studio` lines, and extend the header comment: `NUFI Works gets nufi_works`.

`deploy/box/.env.example`, after `WORKS_EGRESS_ALLOW=`:

```
# ---- NUFI Works on the box (install-box.sh --with-works; Ubuntu only) ----
NUFI_WORKS=0                      # 1 = the works profile is part of this box's stack
NUFI_WORKS_TAG=main
NUFI_SANDBOX_TAG=main
WORKS_AUTH_SECRET=replace-me      # better-auth; generated by the installer on every box
WORKS_OIDC_SECRET=replace-me      # the console's nufi-works client secret; generated on every box
WORKS_PUBLIC_URL=                 # https://<BOX_HOST>:3003 when Works is installed; the chooser's third door
WORKS_SANDBOX_IMAGE=              # ghcr.io/dudaji-vn/nufi-sandbox@sha256:... registered by nufi-box works install
WORKS_MODEL_KEY=                  # LiteLLM virtual key minted by nufi-box works install; never the master key
WORKS_BOX_KEY=                    # Works board API key minted by nufi-box works install (the box admin's)
DOCKER_GID=                       # gid of /var/run/docker.sock, read by the installer
```

`deploy/box/nufi-box`, in the `$COMPOSE` assembly after the mesh line:

```sh
# Works and its egress proxy are one profile, switched on by the installer's
# --with-works (NUFI_WORKS=1). Without this line a works box's `restart` would
# bring up everything but the two services the flag was for.
[ "${NUFI_WORKS:-0}" = "1" ] && COMPOSE="$COMPOSE --profile works"
```

- [ ] **Step 4: Caddy, LAN and mesh**

`deploy/box/Caddyfile`, after the admin-panel site:

```
# NUFI Works. Its OIDC callback and every better-auth POST are checked
# against PAPERCLIP_PUBLIC_URL (https://{$BOX_HOST}:3003), so the chooser
# links Works by name; the IP and localhost forms answer for curl and doctor.
{$BOX_HOST}:3003, {$BOX_IP}:3003, localhost:3003 {
	import box_tls
	reverse_proxy works:3100
}
```

`deploy/box/lib/mesh.sh`: `MESH_CADDY_REV=4`; in `mesh_render_caddy`'s heredoc add after the `:3002` block:

```
$host:3003, $ip:3003 {
	import box_tls
	reverse_proxy works:3100
}
```

and change the comment "the box's five TLS sites" (line ~482) to "six". `deploy/box/caddy/mesh.caddy.empty`: first line `# nufi-box mesh.caddy rev 4`, and "five real site blocks" → "six".

- [ ] **Step 5: Run — all green**

Run: `cd deploy/box && docker compose --project-directory . -f docker-compose.yml --profile works config >/dev/null && uvx pytest@8.3.4 tests -q`
Expected: green. If `test_env_example_covers_every_variable` names a key, add it to `.env.example`. If `test_mesh.py` pins rev 3 anywhere, update it to 4 with the same reasoning.

- [ ] **Step 6: Commit**

```bash
git add deploy/box/docker-compose.yml deploy/box/docker-compose.emulate.yml deploy/box/Caddyfile deploy/box/lib/mesh.sh deploy/box/caddy/mesh.caddy.empty deploy/box/scripts/postgres-init.sh deploy/box/.env.example deploy/box/nufi-box deploy/box/tests/test_compose.py deploy/box/tests/test_caddyfile.py
git commit -m "feat(box): the works service, behind a profile, on the sixth port

NUFI Works on the box: upstream's image as uid 1000 with the docker
group, the socket it needs to create sibling sandboxes, the box's own
adapter file, the console as its OIDC issuer through Caddy's CA, and a
LiteLLM virtual key -- never the master key -- as the model credential
its sandboxes inherit. It and the egress proxy sit behind the works
profile, so a box installed without --with-works renders exactly the
services it renders today; a test says so. Caddy gets :3003 on the LAN
and on the mesh (rev 4), and the console opens its third door only
when WORKS_PUBLIC_URL is set."
```

---

### Task 4: `install-box.sh --with-works` — runsc, the profile, the sandbox image

**Files:**
- Modify: `deploy/box/install-box.sh`, `deploy/box/tests/test_install.py`, `.github/workflows/gvisor-probe.yml`

**Interfaces:**
- Consumes: Task 3's env keys and profile; Task 1's image.
- Produces: `.env` with `NUFI_WORKS=1`, `WORKS_PUBLIC_URL=https://<BOX_HOST>:3003`, `DOCKER_GID=<gid>`, `WORKS_SANDBOX_IMAGE=<digest ref>` (after the pull); `WORKS_AUTH_SECRET`/`WORKS_OIDC_SECRET` on every box; `runsc` at `/usr/local/bin/runsc` registered in `daemon.json`; the stack started with `--profile works`; a call to `nufi-box works install` (Task 5) at the end. Every step has a dry-run line.

- [ ] **Step 1: Write the failing tests**

Append to `deploy/box/tests/test_install.py`:

```python
GVISOR = "https://storage.googleapis.com/gvisor/releases/release/20260907/x86_64/gvisor.tar.bz2"
GVISOR_SHA = "c38cc38ee709d862501e55eebd99f5bd105899cbc7cf3fa1f620493fa127364c5b74c7361d231bd8b9523be48918ea3820dd40b28c61c2b2cb644edbf10261fb"


def test_with_works_refuses_a_mac_and_says_why():
    """Sandboxes run under gVisor, and Docker Desktop cannot host a runtime.
    Refuse before anything is written, and name the reason."""
    r = install("--with-works", NUFI_BOX_FAKE_OS="Darwin")
    assert r.returncode != 0
    assert "Docker Desktop" in r.stderr, r.stderr
    assert ".env written" not in r.stdout


def test_with_works_installs_a_pinned_runsc_and_registers_it():
    out = dry("--with-works", NUFI_BOX_FAKE_OS="Linux")
    assert GVISOR in out, out
    assert GVISOR_SHA in out, "the tarball's checksum is verified, not just downloaded"
    assert "tar -xjf" in out and "runsc" in out
    assert "/usr/local/bin/runsc" in out
    assert '"runtimes"' in out or "runtimes" in out, "daemon.json gains the runtime by a merge"
    assert "systemctl restart docker" in out


def test_with_works_turns_the_profile_on_and_records_it():
    out = dry("--with-works", NUFI_BOX_FAKE_OS="Linux")
    assert "--profile works" in out
    assert "NUFI_WORKS=1" in out
    assert "WORKS_PUBLIC_URL=https://nufi.local:3003" in out
    assert "DOCKER_GID=" in out
    assert "nufi-sandbox:main" in out, "the sandbox image is pulled with the stack"
    assert "WORKS_SANDBOX_IMAGE" in out, "and registered by digest"
    assert "works install" in out, "registration is delegated to nufi-box works install"


def test_without_the_flag_the_box_is_the_box_that_ships_today():
    out = dry(NUFI_BOX_FAKE_OS="Linux")
    for absent in ("--profile works", "gvisor", "runsc", "nufi-sandbox", "works install"):
        assert absent not in out, absent
    assert "NUFI_WORKS=0" in out
    assert "WORKS_PUBLIC_URL=\n" in out or "WORKS_PUBLIC_URL=" in out


def test_the_works_secrets_exist_on_every_box():
    """The console registers Works as an OIDC client on every box, so the
    secret must exist whether or not Works does; a box that adds Works later
    then needs no console change."""
    out = dry(NUFI_BOX_FAKE_OS="Linux")
    for key in ("WORKS_AUTH_SECRET=", "WORKS_OIDC_SECRET="):
        line = next(l for l in out.splitlines() if l.startswith(key))
        assert len(line.split("=", 1)[1]) >= 32, line
        assert "replace-me" not in line


def test_a_rerun_keeps_works_on_without_the_flag(tmp_path):
    envf = tmp_path / ".env"
    envf.write_text("NUFI_WORKS=1\nBOX_HOST=nufi.local\nWORKS_PUBLIC_URL=https://nufi.local:3003\n")
    out = dry(NUFI_BOX_FAKE_OS="Linux", NUFI_BOX_ENV=str(envf))
    assert "--profile works" in out
    assert "NUFI_WORKS=1" in out
```

- [ ] **Step 2: Verify they fail**

Run: `cd deploy/box && uvx pytest@8.3.4 tests/test_install.py -q -k "works or ships_today"`
Expected: FAIL — `--with-works` is an unknown flag (the installer dies on it).

- [ ] **Step 3: The flag, the refusal, the secrets, the profile**

In `deploy/box/install-box.sh`:

Usage header (lines 2–32): add `--with-works` to the synopsis and an option line: `#   --with-works     NUFI Works on this box (Ubuntu only): installs gVisor as a` / `#                    Docker runtime and starts Works behind https://<box>:3003.`

Arg parse: `--with-works) WITH_WORKS=1 ;;` and initialise `WITH_WORKS=0` with the other flags.

Right after `say "Checking prerequisites on $OS/$ARCH"` and its existing checks, add:

```sh
# Works on the box means agent code in gVisor sandboxes, and gVisor is a Docker
# runtime -- something Docker Desktop's VM-hosted daemon cannot be given. Refuse
# before a byte is written, and say so in the words the person will search for.
if [ "$WITH_WORKS" = 1 ] && [ "$OS" != "Linux" ]; then
  die "--with-works needs Ubuntu: Works sandboxes run under gVisor, which Docker Desktop cannot host. Install the box without it here, or with it on the Linux machine that will be the box."
fi
```

In the secrets block after `sec ADMIN_SESSION_SECRET …`: `sec WORKS_AUTH_SECRET "gen_hex 32"; sec WORKS_OIDC_SECRET "gen_hex 32"`.

After `INGEST_EMAIL`/`INGEST_PASSWORD` resolution, add:

```sh
# Works: on when this run asked for it, or when a previous run did (a re-run
# without the flag must not switch a department's Works off).
NUFI_WORKS="${NUFI_WORKS:-0}"; [ "$WITH_WORKS" = 1 ] && NUFI_WORKS=1
if [ "$NUFI_WORKS" = 1 ]; then
  WORKS_PUBLIC_URL="https://$BOX_HOST:3003"
  # The gid that owns the socket, so the works container's uid 1000 can open
  # it. Read from the socket itself: the docker group's number is not the
  # same on every distribution.
  if [ "$DRY" = 1 ]; then DOCKER_GID="${DOCKER_GID:-999}"; else DOCKER_GID="$(stat -c %g /var/run/docker.sock)"; fi
else
  WORKS_PUBLIC_URL=""
fi
```

In `render_env`, after `NUFI_CRON_TAG=…`:

```
NUFI_WORKS=$NUFI_WORKS
NUFI_WORKS_TAG=${NUFI_WORKS_TAG:-main}
NUFI_SANDBOX_TAG=${NUFI_SANDBOX_TAG:-main}
WORKS_AUTH_SECRET=$WORKS_AUTH_SECRET
WORKS_OIDC_SECRET=$WORKS_OIDC_SECRET
WORKS_PUBLIC_URL=$WORKS_PUBLIC_URL
WORKS_SANDBOX_IMAGE=${WORKS_SANDBOX_IMAGE:-}
WORKS_MODEL_KEY=${WORKS_MODEL_KEY:-}
WORKS_BOX_KEY=${WORKS_BOX_KEY:-}
DOCKER_GID=${DOCKER_GID:-}
```

In the `# ---------- start` compose assembly, inside the `if [ "$OS" = "Linux" ]` block after the mesh line: `[ "$NUFI_WORKS" = 1 ] && COMPOSE="$COMPOSE --profile works"`.

- [ ] **Step 4: runsc**

Before the `# ---------- rendered files` section, add:

```sh
# ---------- gVisor -----------------------------------------------------------------
# The kernel boundary every Works sandbox runs behind. runsc is one static
# binary registered with the daemon as a runtime; Docker calls it directly and
# needs no containerd shim (the gvisor-probe workflow found the shim is not
# even published at the path the docs name). Pinned to a release and its
# checksum: a sandbox runtime that tracks "latest" is a boundary that changes
# under the box without a commit.
GVISOR_RELEASE=20260907
gvisor_sha() { case "$1" in
  x86_64)  echo c38cc38ee709d862501e55eebd99f5bd105899cbc7cf3fa1f620493fa127364c5b74c7361d231bd8b9523be48918ea3820dd40b28c61c2b2cb644edbf10261fb ;;
  aarch64) echo fce113699d2e722785e0f66718def9b287cfeef92bd5694da5830ec0c2107d26da94d050e9e6ce68ae65212c437b4eb8f64b67b34add7b04637f4dd12befa2f4 ;;
  *) echo "" ;; esac; }
if [ "$NUFI_WORKS" = 1 ]; then
  say "Installing gVisor $GVISOR_RELEASE (runsc) as a Docker runtime"
  GVISOR_ARCH="$ARCH"; [ "$ARCH" = "arm64" ] && GVISOR_ARCH=aarch64
  GVISOR_URL="https://storage.googleapis.com/gvisor/releases/release/$GVISOR_RELEASE/$GVISOR_ARCH/gvisor.tar.bz2"
  GVISOR_SHA="$(gvisor_sha "$GVISOR_ARCH")"
  [ -n "$GVISOR_SHA" ] || die "no gVisor build is pinned for $GVISOR_ARCH"
  if [ "$DRY" = 1 ]; then
    printf '  $ curl -fsSL -o gvisor.tar.bz2 %s\n' "$GVISOR_URL"
    printf '  $ echo "%s  gvisor.tar.bz2" | sha512sum -c -\n' "$GVISOR_SHA"
    printf '  $ tar -xjf gvisor.tar.bz2 runsc && sudo install -m 0755 runsc /usr/local/bin/runsc\n'
    printf '  $ python3 - <<PY   # merge into /etc/docker/daemon.json\n{"runtimes": {"runsc": {"path": "/usr/local/bin/runsc"}}}\nPY\n'
    printf '  $ sudo systemctl restart docker\n'
  elif /usr/local/bin/runsc --version 2>/dev/null | grep -q "release-$GVISOR_RELEASE" \
       && docker info --format '{{range $k,$v := .Runtimes}}{{$k}} {{end}}' | grep -qw runsc; then
    ok "runsc $GVISOR_RELEASE is already a Docker runtime"
  else
    _gv="$(mktemp -d)"
    curl -fsSL -o "$_gv/gvisor.tar.bz2" "$GVISOR_URL" || die "could not download $GVISOR_URL"
    ( cd "$_gv" && echo "$GVISOR_SHA  gvisor.tar.bz2" | sha512sum -c - >/dev/null ) \
      || die "gvisor.tar.bz2 does not match the pinned checksum; not installing it"
    tar -xjf "$_gv/gvisor.tar.bz2" -C "$_gv" runsc
    sudo install -m 0755 "$_gv/runsc" /usr/local/bin/runsc
    rm -rf "$_gv"
    sudo python3 - /etc/docker/daemon.json <<'PYEOF'
import json, sys
path = sys.argv[1]
try:
    with open(path) as f:
        cfg = json.load(f)
except (FileNotFoundError, ValueError):
    cfg = {}
cfg.setdefault("runtimes", {})["runsc"] = {"path": "/usr/local/bin/runsc"}
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PYEOF
    sudo systemctl restart docker || die "could not restart docker to load the runsc runtime"
    docker info --format '{{range $k,$v := .Runtimes}}{{$k}} {{end}}' | grep -qw runsc \
      || die "docker does not list runsc after the restart; check /etc/docker/daemon.json"
    ok "runsc $GVISOR_RELEASE is a Docker runtime"
  fi
fi
```

Check the `runsc --version` output format on the pinned release in a throwaway: `docker run --rm -v /path/to/runsc:/runsc:ro alpine:3.20 /runsc --version` (it is a static binary) — adjust the `grep -q "release-$GVISOR_RELEASE"` pattern to what it prints (it is `runsc version release-20260907.0` or similar; match the digits).

- [ ] **Step 5: The sandbox image, pinned; the delegation; the banner**

After the pull loop (`[ "$pull_ok" = 1 ] || die …`), add:

```sh
# The image a sandbox runs in, pulled with the stack and then pinned by digest
# in .env: the environment `nufi-box works install` registers must name an
# immutable reference (the provider refuses anything else), and a tag is not
# one.
if [ "$NUFI_WORKS" = 1 ] && [ "$NO_PULL" = 0 ]; then
  SANDBOX_REF="${NUFI_REGISTRY:-ghcr.io/dudaji-vn}/nufi-sandbox:${NUFI_SANDBOX_TAG:-main}"
  run docker pull "$SANDBOX_REF" || die "could not pull $SANDBOX_REF"
  if [ "$DRY" = 1 ]; then
    printf '  $ WORKS_SANDBOX_IMAGE=$(docker image inspect --format {{index .RepoDigests 0}} %s)  # written to .env\n' "$SANDBOX_REF"
  else
    WORKS_SANDBOX_IMAGE="$(docker image inspect --format '{{index .RepoDigests 0}}' "$SANDBOX_REF")"
    [ -n "$WORKS_SANDBOX_IMAGE" ] || die "$SANDBOX_REF has no repo digest after the pull"
    . "$BOX_HOME/lib/envfile.sh"
    envfile_set "$NUFI_BOX_ENV" WORKS_SANDBOX_IMAGE "$WORKS_SANDBOX_IMAGE"
  fi
fi
```

After the flows-install block (before the mesh block), add, in the same shape as flows:

```sh
# ---------- Works ---------------------------------------------------------------------
# Same delegation as the routines: registering the Docker environment is
# day-two work too (`nufi-box works install` re-runs after an upgrade), and two
# copies of "sign in, claim, install the provider, register" would drift.
if [ "$NUFI_WORKS" = 1 ]; then
  say "Registering the sandbox environment in Works"
  if [ "$DRY" = 1 ]; then
    _works_env="$(mktemp)"
    render_env > "$_works_env"
    NUFI_BOX_DRY_RUN=1 NUFI_BOX_FAKE_OS="$OS" NUFI_BOX_ENV="$_works_env" "$BOX_HOME/nufi-box" works install || true
    rm -f "$_works_env"
  else
    "$BOX_HOME/nufi-box" works install || warn "Works is up but not registered yet; run: nufi-box works install"
  fi
fi
```

In the banner, after the `Routines:` paragraph, when `NUFI_WORKS=1`:

```sh
$( [ "$NUFI_WORKS" = 1 ] && printf '\n  Works:       https://%s:3003  → enter it from the Agents page as %s.\n               Every agent run lands in a gVisor sandbox with no network\n               except the box gateway (README "NUFI Works on the box").\n' "$BOX_HOST" "$ADMIN_EMAIL" )
```

- [ ] **Step 6: The probe gains A's exact HostConfig**

In `.github/workflows/gvisor-probe.yml`, before "Does it survive being told there is no route out?", add:

```yaml
      - name: The provider's exact container shape under runsc (piece A's HostConfig)
        run: |
          set -eux
          docker run --rm --runtime=runsc --init --read-only --cap-drop ALL \
            --security-opt no-new-privileges --tmpfs /tmp:noexec,nosuid \
            --memory 512m --cpus 1 --pids-limit 256 --network none \
            alpine:3.20 sh -c 'uname -r; dmesg | grep -qi gvisor && echo "PASS: A'"'"'s HostConfig starts under gVisor"'
```

- [ ] **Step 7: Run — pass; commit**

Run: `cd deploy/box && uvx pytest@8.3.4 tests -q` → green (the whole suite; `test_dry_run_creates_nothing` must still hold — the dry path writes nothing).

```bash
git add deploy/box/install-box.sh deploy/box/tests/test_install.py .github/workflows/gvisor-probe.yml
git commit -m "feat(box): install-box.sh --with-works

Ubuntu only -- it refuses a Mac by name, because gVisor is a Docker
runtime and Docker Desktop cannot be given one. Installs runsc from a
pinned release with its checksum verified, registers it in daemon.json
by a merge, restarts the daemon and refuses to continue if the runtime
is not listed. Turns the works profile on, reads the socket's gid for
the works container, pulls the sandbox image and pins its digest in
.env, and hands registration to nufi-box works install. A re-run
without the flag keeps Works on. The Works secrets exist on every box,
so the console's client registration never has to change."
```

---

### Task 5: `nufi-box works install` — the registrar

**Files:**
- Create: `deploy/box/works/register_works.py`, `deploy/box/works/test_register_works.py`, `deploy/box/lib/works.sh`
- Modify: `deploy/box/nufi-box` (the `works` verb, `usage`), `deploy/box/tests/test_nufi_box.py`, `.github/workflows/box-ci.yml`

**Interfaces:**
- Consumes: `.env` keys from Task 3/4 (`BOX_HOST`, `BOX_NAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `LITELLM_MASTER_KEY`, `WORKS_SANDBOX_IMAGE`, `WORKS_BOX_KEY`, `WORKS_MODEL_KEY`, `NUFI_WORKS`), the `works` service, `lib/envfile.sh`.
- Produces: `register_works.py` CLI — `--works URL --chat URL --litellm URL --cacert FILE --login EMAIL --company NAME --image REF [--plugin-path P] [--check]`; env in: `ADMIN_PASSWORD`, `WORKS_BOX_KEY`, `WORKS_MODEL_KEY`, `LITELLM_MASTER_KEY`; stdout: `WORKS_BOX_KEY=…` / `WORKS_MODEL_KEY=…` lines for anything it minted; stderr: progress; exit 0 registered, 1 an HTTP step failed, 3 the instance is claimed by someone else. `--check` performs only reads with `WORKS_BOX_KEY` and exits 0 when the plugin is ready, the instance default is the docker environment and `Local` is archived, else 1 with each missing item on stderr (Task 6's doctor uses it). Bash: `works_install`, `works_status`, `works_check`.

- [ ] **Step 1: Write the failing test**

`deploy/box/works/test_register_works.py`:

```python
#!/usr/bin/env python3
"""The registrar against a fake box: chat, console, Works and LiteLLM on one
http.server. What is asserted is the calls it makes, in the shape the real
services answer -- and that a second run makes none of the ones that create.

Run:  python3 deploy/box/works/test_register_works.py     (exit 0 = PASS)
"""
import http.server
import json
import os
import pathlib
import subprocess
import sys
import threading
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "register_works.py"
ADMIN = "admin@nufi.local"
PLUGIN = "@nufi/plugin-docker-sandbox"


def fresh_state():
    return {
        "calls": [],
        "claimed_by": None,           # None | "me" | "other"
        "plugins": [],                # {id, packageName, status}
        "companies": [],              # {id, name}
        "environments": [{"id": "env-local", "name": "Local", "driver": "local",
                          "status": "active", "config": {}}],
        "default_env": None,
        "keys_minted": 0,
        "plugin_polls": 0,
        "chat_logins": 0,
    }


class Fake(http.server.BaseHTTPRequestHandler):
    state = fresh_state()

    def log_message(self, *a):
        pass

    # -- helpers --
    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def send(self, code, obj=None, headers=()):
        data = json.dumps(obj if obj is not None else {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def cookie(self, name):
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            k, _, v = part.strip().partition("=")
            if k == name:
                return v
        return None

    def bearer(self):
        a = self.headers.get("Authorization") or ""
        return a[7:] if a.lower().startswith("bearer ") else None

    def as_admin(self):
        st = Fake.state
        if self.bearer() == "bk-1":
            return st["claimed_by"] == "me"
        if self.cookie("session") == "sess-1":
            return st["claimed_by"] == "me"
        return False

    def record(self):
        Fake.state["calls"].append((self.command, urllib.parse.urlparse(self.path).path))

    # -- routes --
    def do_GET(self):
        self.record()
        st = Fake.state
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/oidc/authorize":                       # the console
            assert self.cookie("refreshToken") == "rt-1", "no chat session at the console"
            assert q["client_id"] == ["nufi-works"]
            target = q["redirect_uri"][0] + "?code=code-1&state=" + q["state"][0]
            self.send_response(302); self.send_header("Location", target); self.end_headers(); return
        if u.path == "/api/auth/oauth2/callback/nufi":         # Works, the far end of SSO
            assert self.cookie("better-auth.state") == "st-1", "state cookie did not travel"
            assert q["code"] == ["code-1"]
            self.send_response(302); self.send_header("Set-Cookie", "session=sess-1; Path=/")
            self.send_header("Location", "/"); self.end_headers(); return
        if u.path == "/":
            self.send(200, {"ok": True}); return
        if u.path == "/api/auth/get-session":
            if self.cookie("session") != "sess-1":
                self.send(200, None); return
            self.send(200, {"user": {"email": ADMIN, "id": "u-1"}}); return
        if u.path == "/api/health":
            self.send(200, {"status": "ok"}); return
        if u.path == "/api/instance/settings":
            if not self.as_admin():
                self.send(403, {"error": "Instance admin access required"}); return
            self.send(200, {"defaultEnvironmentId": st["default_env"]}); return
        if u.path == "/api/plugins":
            if not self.bearer() == "bk-1": self.send(401); return
            st["plugin_polls"] += 1
            # The worker takes a moment after install: first listing says
            # installed, the next says ready. The registrar must wait for ready.
            for p in st["plugins"]:
                if p["status"] == "installed" and st["plugin_polls"] > p["installed_at_poll"]:
                    p["status"] = "ready"
            self.send(200, st["plugins"]); return
        if u.path == "/api/companies":
            self.send(200, st["companies"]); return
        if u.path.startswith("/api/companies/") and u.path.endswith("/environments"):
            self.send(200, st["environments"]); return
        self.send(404, {"error": "no route " + u.path})

    def do_POST(self):
        self.record()
        st = Fake.state
        u = urllib.parse.urlparse(self.path)
        b = self.body()
        if u.path == "/api/auth/login":                          # chat
            assert "Mozilla" in (self.headers.get("User-Agent") or ""), "chat needs a browser UA"
            assert b == {"email": ADMIN, "password": "pw-1"}, b
            st["chat_logins"] += 1
            self.send(200, {"user": {"email": ADMIN}}, [("Set-Cookie", "refreshToken=rt-1; Path=/; HttpOnly")]); return
        if u.path == "/api/auth/sign-in/oauth2":                 # Works starts SSO
            assert self.headers.get("Origin") == self.works_origin(), self.headers.get("Origin")
            assert b["providerId"] == "nufi"
            url = (self.works_origin() + "/oidc/authorize?client_id=nufi-works&state=st-1&redirect_uri="
                   + urllib.parse.quote(self.works_origin() + "/api/auth/oauth2/callback/nufi", safe=""))
            self.send(200, {"url": url, "redirect": True}, [("Set-Cookie", "better-auth.state=st-1; Path=/")]); return
        if u.path == "/api/bootstrap/claim":
            assert self.cookie("session") == "sess-1"
            assert self.headers.get("Origin") == self.works_origin()
            if st["claimed_by"] is None:
                st["claimed_by"] = "me"; self.send(200, {"claimed": True}); return
            self.send(409, {"error": "Someone else has already claimed this instance"}); return
        if u.path == "/api/board-api-keys":
            assert self.cookie("session") == "sess-1" and st["claimed_by"] == "me"
            st["keys_minted"] += 1
            self.send(201, {"id": "k-1", "name": b["name"], "token": "bk-1"}); return
        if u.path == "/key/generate":                            # LiteLLM, not Works: master key, no session
            assert self.bearer() == "sk-master", "the virtual key is minted with the master key"
            self.send(200, {"key": "sk-virtual-1"}); return
        if not self.as_admin():
            self.send(403, {"error": "Instance admin required"}); return
        if u.path == "/api/plugins/install":
            assert b == {"packageName": "/app/packages/plugins/sandbox-providers/docker", "isLocalPath": True}, b
            st["plugins"].append({"id": "p-1", "packageName": PLUGIN, "status": "installed",
                                  "installed_at_poll": st["plugin_polls"]})
            self.send(201, st["plugins"][-1]); return
        if u.path == "/api/companies":
            st["companies"].append({"id": "c-1", "name": b["name"]}); self.send(201, st["companies"][-1]); return
        if u.path == "/api/companies/c-1/environments":
            assert b["driver"] == "sandbox" and b["config"]["provider"] == "docker", b
            env = {"id": "env-docker", "name": b["name"], "driver": "sandbox", "status": "active", "config": b["config"]}
            st["environments"].append(env); self.send(201, env); return
        self.send(404, {"error": "no route " + u.path})

    def do_PATCH(self):
        self.record()
        st = Fake.state
        u = urllib.parse.urlparse(self.path)
        b = self.body()
        if not self.as_admin():
            self.send(403); return
        if u.path == "/api/instance/settings":
            st["default_env"] = b["defaultEnvironmentId"]; self.send(200, {"defaultEnvironmentId": st["default_env"]}); return
        if u.path.startswith("/api/environments/"):
            env_id = u.path.rsplit("/", 1)[1]
            (env,) = [e for e in st["environments"] if e["id"] == env_id]
            env.update(b); self.send(200, env); return
        self.send(404)

    def works_origin(self):
        return "http://127.0.0.1:%d" % self.server.server_address[1]


def serve():
    srv = http.server.HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


def run(base, **env_extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("WORKS_") and k not in ("ADMIN_PASSWORD", "LITELLM_MASTER_KEY")}
    env.update({"ADMIN_PASSWORD": "pw-1", "LITELLM_MASTER_KEY": "sk-master"})
    env.update(env_extra)
    return subprocess.run([sys.executable, str(SCRIPT), "--works", base, "--chat", base, "--litellm", base,
                           "--login", ADMIN, "--company", "nufi", "--image", "ghcr.io/dudaji-vn/nufi-sandbox@sha256:" + "0" * 64],
                          env=env, capture_output=True, text=True, timeout=60)


def keys(stdout):
    return dict(l.split("=", 1) for l in stdout.splitlines() if l and l[0].isupper() and "=" in l)


def test_first_run_signs_in_as_the_admin_claims_and_registers_everything():
    Fake.state = fresh_state()
    srv, base = serve()
    try:
        r = run(base)
        assert r.returncode == 0, r.stderr
        st = Fake.state
        assert st["chat_logins"] == 1, "signed in to chat once, with the admin's password"
        assert st["claimed_by"] == "me", "the admin's SSO session claimed first admin"
        assert keys(r.stdout) == {"WORKS_BOX_KEY": "bk-1", "WORKS_MODEL_KEY": "sk-virtual-1"}, r.stdout
        assert [p["packageName"] for p in st["plugins"]] == [PLUGIN]
        assert st["plugins"][0]["status"] == "ready", "waited for the worker"
        assert [c["name"] for c in st["companies"]] == ["nufi"]
        docker = [e for e in st["environments"] if e["driver"] == "sandbox"]
        assert len(docker) == 1 and docker[0]["config"]["image"].startswith("ghcr.io/dudaji-vn/nufi-sandbox@sha256:")
        assert st["default_env"] == "env-docker", "the docker environment is the instance default"
        local = [e for e in st["environments"] if e["driver"] == "local"][0]
        assert local["status"] == "archived", "upstream's Local -- plain Docker, no gVisor -- is archived"
        print("PASS: first run signs in as the admin, claims, installs, registers, pins, archives Local")
    finally:
        srv.shutdown()


def test_second_run_with_the_keys_creates_nothing_and_never_signs_in():
    Fake.state = fresh_state()
    srv, base = serve()
    try:
        first = run(base)
        assert first.returncode == 0, first.stderr
        Fake.state["calls"].clear()
        r = run(base, WORKS_BOX_KEY="bk-1", WORKS_MODEL_KEY="sk-virtual-1")
        assert r.returncode == 0, r.stderr
        writes = [c for c in Fake.state["calls"] if c[0] in ("POST", "PATCH")]
        assert writes == [], writes
        assert Fake.state["chat_logins"] == 1, "a working box key means no second sign-in"
        assert keys(r.stdout) == {}, "nothing minted, nothing printed"
        print("PASS: a second run is reads only")
    finally:
        srv.shutdown()


def test_an_instance_claimed_by_someone_else_is_named_not_worked_around():
    Fake.state = fresh_state()
    Fake.state["claimed_by"] = "other"
    srv, base = serve()
    try:
        r = run(base)
        assert r.returncode == 3, (r.returncode, r.stderr)
        assert "claimed" in r.stderr and "promote" in r.stderr, r.stderr
        assert not [c for c in Fake.state["calls"] if c[1] in ("/api/plugins/install", "/api/companies") and c[0] == "POST"]
        print("PASS: someone else's instance is reported with the fix, not taken over")
    finally:
        srv.shutdown()


def test_a_new_image_digest_repins_the_existing_environment():
    Fake.state = fresh_state()
    Fake.state["companies"] = [{"id": "c-1", "name": "nufi"}]
    Fake.state["environments"].append({"id": "env-docker", "name": "Box sandboxes", "driver": "sandbox",
                                       "status": "active", "config": {"provider": "docker", "image": "ghcr.io/dudaji-vn/nufi-sandbox@sha256:" + "f" * 64}})
    Fake.state["plugins"] = [{"id": "p-1", "packageName": PLUGIN, "status": "ready", "installed_at_poll": 0}]
    Fake.state["claimed_by"] = "me"
    Fake.state["default_env"] = "env-docker"
    srv, base = serve()
    try:
        r = run(base, WORKS_BOX_KEY="bk-1", WORKS_MODEL_KEY="x")
        assert r.returncode == 0, r.stderr
        (env,) = [e for e in Fake.state["environments"] if e["driver"] == "sandbox"]
        assert env["config"]["image"].endswith("0" * 64), env
        posts = [c for c in Fake.state["calls"] if c[0] == "POST"]
        assert posts == [], posts
        print("PASS: an installer that pulled a new digest re-pins the environment in place")
    finally:
        srv.shutdown()


def test_check_mode_reads_only_and_says_what_is_missing():
    Fake.state = fresh_state()
    Fake.state["claimed_by"] = "me"
    Fake.state["companies"] = [{"id": "c-1", "name": "nufi"}]
    srv, base = serve()
    try:
        env = dict(os.environ, WORKS_BOX_KEY="bk-1")
        r = subprocess.run([sys.executable, str(SCRIPT), "--works", base, "--check", "--image", "x@sha256:" + "0" * 64],
                           env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode == 1, (r.returncode, r.stderr)
        for missing in ("plugin", "default", "Local"):
            assert missing in r.stderr, (missing, r.stderr)
        assert not [c for c in Fake.state["calls"] if c[0] != "GET"]
        print("PASS: --check is reads only and names each missing piece")
    finally:
        srv.shutdown()


if __name__ == "__main__":
    test_first_run_signs_in_as_the_admin_claims_and_registers_everything()
    test_second_run_with_the_keys_creates_nothing_and_never_signs_in()
    test_an_instance_claimed_by_someone_else_is_named_not_worked_around()
    test_a_new_image_digest_repins_the_existing_environment()
    test_check_mode_reads_only_and_says_what_is_missing()
```

- [ ] **Step 2: Verify it fails**

Run: `python3 deploy/box/works/test_register_works.py`
Expected: FAIL — `register_works.py` does not exist.

- [ ] **Step 3: The registrar**

`deploy/box/works/register_works.py`:

```python
#!/usr/bin/env python3
"""Register the box's Docker sandbox environment in NUFI Works.

Runs inside the box network (`nufi-box works install` starts it with
`docker compose run`), where the box's name resolves to Caddy and the box's CA
is on the volume. Stdlib only.

How it gets to be an instance admin without a human step: it signs in AS THE
BOX ADMIN through the same door a browser takes -- the chat login, then the
console's /oidc/authorize, then Works' OAuth callback -- and that session
claims first admin (Works is in private exposure) and mints one board API key.
Every later run uses the key and never signs in again. There is no service
account and no database write, and the admin's own browser lands on the same
account, because it is the same identity.

Exit codes: 0 registered (or already so); 1 a step failed (the response is on
stderr); 3 the instance was claimed by someone else -- say who to promote.

Secrets arrive in the environment, never in an argument:
  ADMIN_PASSWORD, LITELLM_MASTER_KEY, and the two this script may mint and
  prints back on stdout as KEY=VALUE for the caller to keep: WORKS_BOX_KEY,
  WORKS_MODEL_KEY.
"""
import argparse
import http.cookiejar
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PLUGIN_PACKAGE = "@nufi/plugin-docker-sandbox"
PLUGIN_PATH = "/app/packages/plugins/sandbox-providers/docker"
ENV_NAME = "Box sandboxes"
ENV_DESC = "Every run on this box: a gVisor container on the works-sandbox network, behind the egress proxy."
# LibreChat's user-agent parser rejects unknown callers; the ingest daemon
# carries the same disguise for the same reason.
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def say(msg):
    print("works: " + msg, file=sys.stderr, flush=True)


class Box:
    def __init__(self, works, cacert):
        self.works = works.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        handlers = [urllib.request.HTTPCookieProcessor(self.jar)]
        if cacert:
            handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=cacert)))
        self.opener = urllib.request.build_opener(*handlers)
        self.token = None

    def call(self, method, url, body=None, token=None, origin=False, ua=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if token or self.token:
            req.add_header("Authorization", "Bearer " + (token or self.token))
        if origin:
            # better-auth and the board-mutation guard check Origin on a
            # session-authenticated POST; a bearer key needs none.
            req.add_header("Origin", self.works)
        req.add_header("User-Agent", ua or "nufi-box/register_works")
        try:
            with self.opener.open(req, timeout=60) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw.strip() else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw.decode(errors="replace")

    def must(self, method, path, body=None, ok=(200, 201), **kw):
        status, out = self.call(method, self.works + path, body, **kw)
        if status not in ok:
            say("%s %s -> %s %s" % (method, path, status, json.dumps(out)[:400] if not isinstance(out, str) else out[:400]))
            sys.exit(1)
        return out


def sign_in_as_admin(box, chat, login, password):
    """The browser's path, without the browser."""
    status, out = box.call("POST", chat.rstrip("/") + "/api/auth/login", {"email": login, "password": password}, ua=UA)
    if status != 200:
        say("chat login as %s failed: %s %s" % (login, status, out)); sys.exit(1)
    out = box.must("POST", "/api/auth/sign-in/oauth2", {"providerId": "nufi", "callbackURL": "/"}, origin=True)
    url = out.get("url") if isinstance(out, dict) else None
    if not url:
        say("Works did not return an SSO redirect: %s" % json.dumps(out)[:300]); sys.exit(1)
    # Console -> code -> Works callback -> session cookie; urllib follows the
    # redirects and the jar carries the chat cookie, the state and the session.
    status, _ = box.call("GET", url)
    if status != 200:
        say("the SSO round trip ended with %s (is the console's OIDC_CLIENTS carrying nufi-works, and PAPERCLIP_PUBLIC_URL the name the box announces?)" % status)
        sys.exit(1)
    session = box.must("GET", "/api/auth/get-session")
    email = ((session or {}).get("user") or {}).get("email", "")
    if email.lower() != login.lower():
        say("signed in as %r, expected %s" % (email, login)); sys.exit(1)
    say("signed in to Works as %s through the console" % login)


def claim_or_confirm(box):
    status, out = box.call("POST", box.works + "/api/bootstrap/claim", {}, origin=True)
    if status == 200:
        say("claimed instance admin")
    elif status != 409:
        say("bootstrap claim -> %s %s" % (status, out)); sys.exit(1)
    status, _ = box.call("GET", box.works + "/api/instance/settings")
    if status != 200:
        say("this Works instance was claimed by someone else, and %s is not an instance admin." % "the box admin")
        say("In Works: Instance access -> promote the box admin to instance admin, then run: nufi-box works install")
        sys.exit(3)


def stored_key_works(box, existing):
    """A key from an earlier run means no sign-in at all this time."""
    if not existing:
        return False
    status, _ = box.call("GET", box.works + "/api/instance/settings", token=existing)
    if status == 200:
        box.token = existing
        return True
    say("the stored WORKS_BOX_KEY no longer works; signing in to mint a new one")
    return False


def mint_key(box):
    """Needs the admin's session (a bearer key cannot mint another)."""
    out = box.must("POST", "/api/board-api-keys", {"name": "nufi-box"}, origin=True)
    box.token = out["token"]
    say("minted a board API key for the box")
    return out["token"]


def plugin_ready(box, path, wait_s=90):
    def find():
        for p in box.must("GET", "/api/plugins"):
            if p.get("packageName") == PLUGIN_PACKAGE and p.get("status") != "uninstalled":
                return p
        return None
    p = find()
    if p is None:
        box.must("POST", "/api/plugins/install", {"packageName": path, "isLocalPath": True})
        say("installed the Docker sandbox provider from %s" % path)
    deadline = time.time() + wait_s
    while True:
        p = find()
        if p and p.get("status") == "ready":
            return p
        if time.time() > deadline:
            say("the provider plugin is %s, not ready, after %ss -- check: nufi-box logs works" % (p and p.get("status"), wait_s))
            sys.exit(1)
        time.sleep(2)


def company(box, name):
    companies = box.must("GET", "/api/companies")
    if companies:
        return companies[0]
    c = box.must("POST", "/api/companies", {"name": name})
    say("created the company %r; the box admin is its owner" % name)
    return c


def environment(box, company_id, image):
    envs = box.must("GET", "/api/companies/%s/environments" % company_id)
    docker = [e for e in envs if e.get("driver") == "sandbox" and (e.get("config") or {}).get("provider") == "docker"]
    if docker:
        env = docker[0]
        if (env.get("config") or {}).get("image") != image:
            cfg = dict(env.get("config") or {}); cfg["image"] = image
            env = box.must("PATCH", "/api/environments/%s" % env["id"], {"config": cfg})
            say("re-pinned the sandbox image to %s" % image)
    else:
        env = box.must("POST", "/api/companies/%s/environments" % company_id, {
            "name": ENV_NAME, "description": ENV_DESC, "driver": "sandbox",
            "config": {"provider": "docker", "image": image}})
        say("registered the Docker sandbox environment (%s)" % image)
    settings = box.must("GET", "/api/instance/settings")
    if settings.get("defaultEnvironmentId") != env["id"]:
        box.must("PATCH", "/api/instance/settings", {"defaultEnvironmentId": env["id"]})
        say("made it the instance default")
    for e in envs:
        if e.get("driver") == "local" and e.get("status") == "active":
            box.must("PATCH", "/api/environments/%s" % e["id"], {"status": "archived"})
            say("archived %r: it would run agent code inside the works container under plain Docker" % e.get("name"))
    return env


def model_key(box, litellm, existing, master):
    if existing:
        return None
    if not master:
        say("no LITELLM_MASTER_KEY in the environment; cannot mint the model key"); sys.exit(1)
    status, out = box.call("POST", litellm.rstrip("/") + "/key/generate",
                           {"key_alias": "works-box-%d" % int(time.time()), "metadata": {"box": "works"}}, token=master)
    if status != 200 or not isinstance(out, dict) or not out.get("key"):
        say("LiteLLM /key/generate -> %s %s" % (status, out)); sys.exit(1)
    say("minted a LiteLLM virtual key for Works; the master key never reaches a sandbox")
    return out["key"]


def check(box, image):
    """Reads only. Exit 0 when the box is registered as `install` leaves it."""
    box.token = os.environ.get("WORKS_BOX_KEY") or None
    if not box.token:
        say("no WORKS_BOX_KEY -- run: nufi-box works install"); sys.exit(1)
    missing = []
    plugins = box.must("GET", "/api/plugins")
    if not any(p.get("packageName") == PLUGIN_PACKAGE and p.get("status") == "ready" for p in plugins):
        missing.append("the Docker sandbox provider plugin is not ready")
    companies = box.must("GET", "/api/companies")
    if not companies:
        missing.append("no company yet (works install creates the box's)")
    envs = box.must("GET", "/api/companies/%s/environments" % companies[0]["id"]) if companies else []
    settings = box.must("GET", "/api/instance/settings")
    default = next((e for e in envs if e.get("id") == settings.get("defaultEnvironmentId")), None)
    if not default or (default.get("config") or {}).get("provider") != "docker":
        missing.append("the instance default environment is not the Docker sandbox one")
    elif image and (default.get("config") or {}).get("image") != image:
        missing.append("the default environment's image is not the pinned %s" % image)
    if any(e.get("driver") == "local" and e.get("status") == "active" for e in envs):
        missing.append("upstream's Local environment is still active")
    for m in missing:
        say("missing: " + m)
    sys.exit(1 if missing else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--works", required=True)
    ap.add_argument("--chat")
    ap.add_argument("--litellm")
    ap.add_argument("--cacert")
    ap.add_argument("--login")
    ap.add_argument("--company", default="nufi")
    ap.add_argument("--image", required=True)
    ap.add_argument("--plugin-path", default=PLUGIN_PATH)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    box = Box(a.works, a.cacert)
    if a.check:
        check(box, a.image)
    minted = {}
    if not stored_key_works(box, os.environ.get("WORKS_BOX_KEY") or None):
        if not (a.chat and a.login and os.environ.get("ADMIN_PASSWORD")):
            say("no working WORKS_BOX_KEY and no way to sign in (--chat, --login, ADMIN_PASSWORD)"); sys.exit(1)
        sign_in_as_admin(box, a.chat, a.login, os.environ["ADMIN_PASSWORD"])
        claim_or_confirm(box)
        minted["WORKS_BOX_KEY"] = mint_key(box)
    plugin_ready(box, a.plugin_path)
    c = company(box, a.company)
    environment(box, c["id"], a.image)
    if a.litellm:
        mk = model_key(box, a.litellm, os.environ.get("WORKS_MODEL_KEY"), os.environ.get("LITELLM_MASTER_KEY"))
        if mk:
            minted["WORKS_MODEL_KEY"] = mk
    for k, v in minted.items():
        print("%s=%s" % (k, v))
    say("registered")


if __name__ == "__main__":
    main()
```

Note for the implementer: `stored_key_works` → (else) sign in → claim → `mint_key` is the whole credential story; the second test pins that a working stored key means zero POSTs and zero chat logins.

- [ ] **Step 4: Run — pass**

Run: `python3 deploy/box/works/test_register_works.py` → five `PASS:` lines. Wire into `.github/workflows/box-ci.yml` beside the adapter file step: `- name: works registrar` / `run: python3 deploy/box/works/test_register_works.py`.

- [ ] **Step 5: The bash side — failing tests first**

Append to `deploy/box/tests/test_nufi_box.py`:

```python
def _works_env(tmp_path, **extra):
    return _env(tmp_path, NUFI_WORKS="1", ADMIN_EMAIL="admin@nufi.local", ADMIN_PASSWORD="pw",
                LITELLM_MASTER_KEY="sk-master", BOX_NAME="nufi",
                WORKS_SANDBOX_IMAGE="ghcr.io/dudaji-vn/nufi-sandbox@sha256:" + "0" * 64, **extra)


def test_works_needs_a_subcommand(tmp_path):
    envf = _works_env(tmp_path)
    r = cli("works", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 2 and "install or status" in r.stderr
    assert cli("works", "frobnicate", NUFI_BOX_ENV=str(envf)).returncode == 2


def test_works_install_runs_the_registrar_inside_the_box_network(tmp_path):
    """The registrar must reach the box by the name the certificate carries and
    trust the box's CA, and inside the network both are already true: the name
    resolves to Caddy and the CA is a file. So it runs there, via compose run,
    with the secrets in the environment and never in an argument."""
    envf = _works_env(tmp_path)
    r = cli("works", "install", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "compose" in out and "run --rm --no-deps" in out and "nufi-cron" in out, out
    assert "register_works.py" in out
    for arg in ("--works https://nufi.local:3003", "--chat https://nufi.local:3080",
                "--litellm http://litellm-proxy:4000", "--login admin@nufi.local", "--company nufi",
                "--image ghcr.io/dudaji-vn/nufi-sandbox@sha256:"):
        assert arg in out, (arg, out)
    for secret in ("pw", "sk-master"):
        assert " %s " % secret not in out and "=%s" % secret not in out, secret
    for passed in ("-e ADMIN_PASSWORD", "-e LITELLM_MASTER_KEY", "-e WORKS_BOX_KEY", "-e WORKS_MODEL_KEY"):
        assert passed in out, passed
    assert "--profile works" in out


def test_works_install_refuses_a_box_installed_without_works(tmp_path):
    envf = _env(tmp_path, NUFI_WORKS="0")
    r = cli("works", "install", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 2
    assert "--with-works" in r.stderr


def test_works_install_needs_the_pinned_image(tmp_path):
    envf = _works_env(tmp_path, WORKS_SANDBOX_IMAGE="")
    r = cli("works", "install", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 2
    assert "WORKS_SANDBOX_IMAGE" in r.stderr


def test_works_status_plans_the_read_only_check(tmp_path):
    envf = _works_env(tmp_path, WORKS_BOX_KEY="bk")
    r = cli("works", "status", NUFI_BOX_ENV=str(envf))
    assert r.returncode == 0, r.stderr
    assert "--check" in r.stdout and "register_works.py" in r.stdout
    assert "bk" not in r.stdout.replace("WORKS_BOX_KEY", "")
```

Run: `cd deploy/box && uvx pytest@8.3.4 tests/test_nufi_box.py -q -k works` → FAIL (no `works` verb).

- [ ] **Step 6: `lib/works.sh` and the verb**

`deploy/box/lib/works.sh`:

```bash
#!/bin/bash
# lib/works.sh — NUFI Works on the box: register the Docker sandbox
# environment, and say whether it is registered. bash 3.2 compatible; sourced
# by nufi-box (uses its $HERE, $ENVF, $DRY, $COMPOSE, $run and the exported
# .env), not executed.
#
# The work is done by works/register_works.py, and it runs INSIDE the box
# network through `compose run`: there the box's name resolves to Caddy (the
# alias every container has) and the CA is a file on the caddy volume, so the
# SSO round trip -- chat login, console authorize, Works callback -- goes over
# the exact URLs a browser would use, TLS verified. From the host that would
# need mDNS to resolve the name and a trusted CA, neither of which a fresh
# Ubuntu box has.
#
# Secrets never appear in an argument: `-e NAME` passes them from this shell's
# environment (nufi-box has exported .env), and what the registrar mints comes
# back on stdout as KEY=VALUE lines that are written to .env here.

WORKS_DATA="${NUFI_DATA_DIR:-$HERE/data}"
WORKS_CA="$WORKS_DATA/nufi-box-ca.crt"
WORKS_REGISTRAR="$HERE/works/register_works.py"
WORKS_URL="https://${BOX_HOST:-nufi.local}:3003"

works_guard() {
  [ "${NUFI_WORKS:-0}" = 1 ] || {
    echo "works: this box was installed without Works — re-run install-box.sh --with-works (Ubuntu only)" >&2; return 2; }
  [ -f "$WORKS_REGISTRAR" ] || {
    echo "works: the registrar is missing ($WORKS_REGISTRAR); deploy/box/works ships with the box" >&2; return 2; }
}

# works_run ARGS… — the registrar, inside the network. `-T`: no tty, so the
# KEY=VALUE lines come back clean. `--no-deps`: nufi-cron's own dependency
# (Studio healthy) is not this call's concern.
works_run() {
  run $COMPOSE run --rm --no-deps -T \
    -v "$WORKS_REGISTRAR:/register_works.py:ro" \
    -v "$WORKS_CA:/ca.crt:ro" \
    -e ADMIN_PASSWORD -e LITELLM_MASTER_KEY -e WORKS_BOX_KEY -e WORKS_MODEL_KEY \
    nufi-cron python3 /register_works.py --works "$WORKS_URL" --cacert /ca.crt "$@"
}

works_wait() {
  local i
  for i in $(seq 1 36); do
    curl -fsk "https://localhost:3003/api/health" >/dev/null 2>&1 && return 0
    sleep 5
  done
  return 1
}

# The database Works migrates into. postgres-init.sh creates it on a fresh box;
# a box installed before Works existed has to get it here.
works_ensure_db() {
  if [ "$DRY" = 1 ]; then printf '  $ psql: CREATE DATABASE nufi_works  # unless it exists\n'; return 0; fi
  if ! $COMPOSE exec -T postgres psql -U "${POSTGRES_USER:-nufi}" -d postgres -tAc \
       "SELECT 1 FROM pg_database WHERE datname='nufi_works'" 2>/dev/null | grep -qx 1; then
    $COMPOSE exec -T postgres psql -U "${POSTGRES_USER:-nufi}" -d postgres -c "CREATE DATABASE nufi_works" >/dev/null
  fi
}

works_install() {
  works_guard || return $?
  [ -n "${WORKS_SANDBOX_IMAGE:-}" ] || {
    echo "works: no WORKS_SANDBOX_IMAGE in .env — the installer pins the sandbox image by digest; run install-box.sh --with-works" >&2; return 2; }
  works_ensure_db
  if [ "$DRY" = 1 ]; then
    works_run --chat "https://${BOX_HOST:-nufi.local}:3080" --litellm "http://litellm-proxy:4000" \
      --login "${ADMIN_EMAIL:-admin@nufi.local}" --company "${BOX_NAME:-nufi}" --image "$WORKS_SANDBOX_IMAGE"
    return 0
  fi
  $COMPOSE up -d works >/dev/null
  works_wait || { echo "works: Works is not answering at $WORKS_URL — check: nufi-box logs works" >&2; return 1; }
  local out; out="$(mktemp)"
  works_run --chat "https://${BOX_HOST:-nufi.local}:3080" --litellm "http://litellm-proxy:4000" \
    --login "${ADMIN_EMAIL:-admin@nufi.local}" --company "${BOX_NAME:-nufi}" --image "$WORKS_SANDBOX_IMAGE" \
    > "$out" || { rm -f "$out"; return 1; }
  . "$HERE/lib/envfile.sh"
  local line new_model_key=0
  while IFS= read -r line; do
    case "$line" in
      WORKS_BOX_KEY=*|WORKS_MODEL_KEY=*)
        envfile_set "$ENVF" "${line%%=*}" "${line#*=}"
        [ "${line%%=*}" = WORKS_MODEL_KEY ] && new_model_key=1 ;;
    esac
  done < "$out"
  rm -f "$out"
  # The model key is read by the works container at creation; a key minted
  # just now is not in the running one. Recreate it, once, with the new .env.
  if [ "$new_model_key" = 1 ]; then
    set -a; . "$ENVF"; set +a
    $COMPOSE up -d works >/dev/null
    works_wait || { echo "works: Works did not come back after the model key was set — check: nufi-box logs works" >&2; return 1; }
  fi
  echo "Works is at $WORKS_URL — enter it from https://${BOX_HOST:-nufi.local}:3001/choose as ${ADMIN_EMAIL:-the box admin}"
}

# works_check — reads only; 0 when registered as install leaves it. Used by
# doctor, and by `works status`.
works_check() {
  works_guard || return $?
  works_run --check --image "${WORKS_SANDBOX_IMAGE:-}"
}

works_status() {
  if [ "$DRY" = 1 ]; then works_check; return $?; fi
  if works_check 2>&1; then echo "Works is registered: $WORKS_URL"; else
    echo "Works is not fully registered — run: nufi-box works install" >&2; return 1; fi
}
```

In `deploy/box/nufi-box`, next to the `flows)` arm:

```sh
  works)
    shift
    case "${1:-}" in
      install|status) WORKS_VERB="$1" ;;
      "") echo "works: say what to do — install or status" >&2; usage; exit 2 ;;
      *) echo "works: unknown subcommand: $1 (use install or status)" >&2; exit 2 ;;
    esac
    . "$HERE/lib/works.sh"
    "works_$WORKS_VERB" ;;
```

and in `usage`/`--help` text add `works install | status`, with one line: `works install — register the Docker sandbox environment in Works (the installer does this; re-run after an upgrade)`.

- [ ] **Step 7: Run — pass; commit**

Run: `cd deploy/box && uvx pytest@8.3.4 tests -q && python3 works/test_register_works.py` → green.

```bash
git add deploy/box/works/register_works.py deploy/box/works/test_register_works.py deploy/box/lib/works.sh deploy/box/nufi-box deploy/box/tests/test_nufi_box.py .github/workflows/box-ci.yml
git commit -m "feat(box): nufi-box works install registers the sandbox environment

The registrar signs in as the box admin through the door a browser
takes -- chat login, the console's authorize, Works' OAuth callback --
so the session that claims first admin is the admin's own; it mints one
board key for every later run and a LiteLLM virtual key for the
sandboxes, installs the provider plugin shipped in the image, creates
the box's company when there is none, registers the Docker environment
pinned to the pulled digest, makes it the instance default and archives
upstream's Local. Every step is a lookup first: a second run makes no
writes and never signs in. It runs inside the box network, where the
box's name resolves and the CA is a file; secrets travel in the
environment. A fake box in one http.server asserts the calls, the
idempotency, the someone-else-claimed case, the re-pin, and --check."
```

---

### Task 6: `doctor` knows a Works box

**Files:**
- Modify: `deploy/box/nufi-box` (the `doctor)` arm), `deploy/box/tests/test_nufi_box.py`

**Interfaces:**
- Consumes: `works_check` (Task 5), `NUFI_WORKS`.
- Produces: three doctor lines on a Works box — `runsc` is a Docker runtime; Works answers `/api/health`; the registration holds (`works_check`) — and nothing on a box without Works.

- [ ] **Step 1: Failing tests**

```python
def test_doctor_checks_a_works_box_three_ways(tmp_path):
    r = cli("doctor", NUFI_BOX_ENV=str(_works_env(tmp_path)))
    out = r.stdout
    assert "runsc" in out, "the runtime the sandboxes depend on"
    assert "3003/api/health" in out
    assert "--check" in out and "register_works.py" in out, "the registration, read-only"


def test_doctor_says_nothing_about_works_on_a_box_without_it(tmp_path):
    r = cli("doctor", NUFI_BOX_ENV=str(_env(tmp_path)))
    for absent in ("runsc", "3003", "register_works"):
        assert absent not in r.stdout, absent
```

Run: `cd deploy/box && uvx pytest@8.3.4 tests/test_nufi_box.py -q -k doctor_checks_a_works or doctor_says_nothing` → FAIL.

- [ ] **Step 2: The checks**

In the `doctor)` arm, after the works-egress block and before `All good.`:

```sh
    # A Works box, three ways: the kernel boundary is a runtime the daemon
    # lists (a box whose daemon.json lost the stanza silently runs sandboxes
    # under runc); the server answers; and the registration holds -- provider
    # ready, the Docker environment the instance default, Local archived.
    # Each can fail on its own, and the third is asked of Works itself rather
    # than inferred from .env.
    if [ "${NUFI_WORKS:-0}" = 1 ]; then
      if [ "$DRY" = 1 ]; then
        printf '  $ docker info: runsc among the runtimes\n'
      elif docker info --format '{{range $k,$v := .Runtimes}}{{$k}} {{end}}' 2>/dev/null | grep -qw runsc; then
        echo " ok  runsc is a Docker runtime"
      else
        echo " !!  runsc is not a Docker runtime — sandboxes would run on the host kernel; run: install-box.sh --with-works"; fail=1
      fi
      chk curl -fsk "https://localhost:3003/api/health"
      . "$HERE/lib/works.sh"
      if [ "$DRY" = 1 ]; then
        works_check
      elif works_check >/dev/null 2>&1; then
        echo " ok  Works is registered: provider ready, Docker environment is the default, Local archived"
      else
        echo " !!  Works is not registered as installed — run: nufi-box works install"; fail=1
      fi
    fi
```

- [ ] **Step 3: Run — pass; commit**

Run: `cd deploy/box && uvx pytest@8.3.4 tests -q` → green.

```bash
git add deploy/box/nufi-box deploy/box/tests/test_nufi_box.py
git commit -m "feat(box): doctor checks a Works box three ways

The runtime the daemon lists (a lost daemon.json stanza runs sandboxes
under runc with nothing to say so), the server's health, and the
registration asked of Works itself: provider ready, the Docker
environment the instance default, Local archived. Nothing on a box
without Works."
```

---

### Task 7: The Ubuntu acceptance, and the docs

**Files:**
- Modify: `deploy/box/tests/vm/verify-ubuntu-box.sh`, `deploy/box/tests/vm/run-ubuntu-install.sh`, `deploy/box/README.md`, `apps/docs/content/docs/box/meta.json`
- Create: `apps/docs/content/docs/box/works.mdx`

**Interfaces:**
- Consumes: everything above.
- Produces: `WITH_WORKS=1 deploy/box/tests/vm/run-ubuntu-install.sh` installs with `--with-works`; `verify-ubuntu-box.sh` gains step 4 on such a box.

- [ ] **Step 1: The VM harness**

`run-ubuntu-install.sh`: where it runs `./install-box.sh --yes --registry '$REGISTRY'`, append `${WITH_WORKS:+--with-works}` (a `WITH_WORKS=1` environment on the Mac side adds the flag). Add one comment line: `# WITH_WORKS=1 installs Works too; verify-ubuntu-box.sh then runs its fourth step.`

`verify-ubuntu-box.sh`, after step 3, add:

```sh
# ---------- 4. Works, on a box installed with it ---------------------------------
# The probe's own test, performed on the product's own pieces: the runtime the
# installer registered, the image it pinned, the network the proxy guards --
# `uname -r` inside a sandbox-shaped container says gVisor, not the host. Then
# doctor, which asks Works itself whether the registration holds. An agent run
# end to end is not asserted here: it needs a model that can drive a coding
# harness, and the VM installs the smallest one the box offers.
if vm 'grep -qx NUFI_WORKS=1 $HOME/deploy/box/.env'; then
  say "Works: a sandbox-shaped container under runsc on the sandbox network"
  IMAGE="$(vm 'sed -n "s/^WORKS_SANDBOX_IMAGE=//p" $HOME/deploy/box/.env')"
  [ -n "$IMAGE" ] || die "no WORKS_SANDBOX_IMAGE in the box's .env"
  KERNEL="$(vm "sg docker -c 'docker run --rm --runtime=runsc --init --read-only --cap-drop ALL --network works-sandbox $IMAGE uname -r'")"
  say "kernel inside the sandbox: $KERNEL (host: $(vm 'uname -r'))"
  case "$KERNEL" in *gvisor*) ;; *) die "the sandbox reports the host kernel ($KERNEL); runsc is not in effect" ;; esac
  say "Works answers on :3003 and doctor agrees"
  CODE=$(curl -s --cacert "$WORK/ca.crt" --resolve "nufi.local:3003:$IP" -o /dev/null -w '%{http_code}' https://nufi.local:3003/api/health)
  [ "$CODE" = 200 ] || die "https://nufi.local:3003/api/health answered $CODE"
  vm 'cd $HOME/deploy/box && sg docker -c "./nufi-box doctor"' | tee "$WORK/doctor.txt"
  grep -q "ok  Works is registered" "$WORK/doctor.txt" || die "doctor does not report Works as registered"
else
  say "Works: not installed on this box (WITH_WORKS=1 on run-ubuntu-install.sh to include it)"
fi
```

Check how step 1 does its `--resolve`/CA curl (line ~60) and match its exact form.

- [ ] **Step 2: README**

In `deploy/box/README.md`, after the "Works sandboxes and where they may reach" subsection, add:

```markdown
### NUFI Works on the box

`install-box.sh --with-works` (Ubuntu only) adds NUFI Works at
`https://<box>:3003`, entered from the Agents page like Studio. Every agent
run on it lands in a **gVisor** sandbox: a container under the `runsc`
runtime the installer registers, on the `works-sandbox` network, with no
route out except the egress proxy above. The box registers this itself —
`nufi-box works install` signs in as the box admin through the console,
claims the instance, installs the sandbox provider, registers the
environment pinned to the image the installer pulled, makes it the default
and archives the upstream `Local` environment (which would have run agent
code inside the Works container under plain Docker).

Two things to know:

- **The Works container holds the Docker socket.** That is how it creates
  sandboxes as sibling containers, and it is the only service that has it.
  Whoever can run code *in the Works container* can start containers on the
  box as root; nothing in a sandbox can.
- **A sandbox's model key is a LiteLLM virtual key** (`WORKS_MODEL_KEY`),
  never the master key: the key reaches the sandbox, and the gateway is on
  the allow list.

`nufi-box doctor` checks the runtime, the server and the registration.
`nufi-box works status` asks Works whether the registration still holds; run
`nufi-box works install` again after an upgrade. Hiring a coding agent
(codex, claude, opencode) works as in the cloud; a NuFi knowledge agent needs
its `gatewayUrl` set to `http://litellm-proxy:4000/v1` and a model the box
serves.
```

- [ ] **Step 3: The docs page**

`apps/docs/content/docs/box/works.mdx` — same voice and frontmatter shape as `routines.mdx` (read it first). Sections: what you get (Works at :3003, entered from Agents), what a run is (a gVisor sandbox on a network with one exit), installing (`--with-works`, Ubuntu only, the one banner line), first sign-in (the admin is already instance admin and owner of the box's company; invite members from Works), what to reach beyond the gateway (`WORKS_EGRESS_ALLOW`, one example), checking it (`nufi-box doctor`, `nufi-box works status`), and honest limits (Ubuntu only; a NuFi knowledge agent's gateway URL is set per agent; the smallest box models cannot drive a coding harness). Add `"works"` to `meta.json` under `---Operate---` after `routines`. Build check: `cd apps/docs && bun run build` (see the docs-build memory: a missing screenshot fails the build — this page has none).

- [ ] **Step 4: Gate and commit**

`cd deploy/box && uvx pytest@8.3.4 tests -q`; `bash -n deploy/box/tests/vm/verify-ubuntu-box.sh`; `cd apps/docs && bun run build`.

```bash
git add deploy/box/tests/vm/verify-ubuntu-box.sh deploy/box/tests/vm/run-ubuntu-install.sh deploy/box/README.md apps/docs/content/docs/box/works.mdx apps/docs/content/docs/box/meta.json
git commit -m "docs(box): Works on the box, and the Ubuntu acceptance's fourth step

The VM run proves what the probe proved, on the product's own pieces:
uname -r inside a sandbox-shaped container under the registered runtime
on the guarded network says gVisor, Works answers, and doctor reports
the registration. The README says what the socket grant means and why
the model key is a virtual one; the docs page says how a box gets
Works and what a run is."
```

Do not open the PR; the controller does.

---

## Self-review

**Spec coverage.** Section C: `nufi-box works install` called by `install-box.sh --with-works` (T4→T5) signs in with the box's credentials (Addendum 1: the admin's, via SSO), installs the provider from its local path (T5 `plugin_ready`), creates one environment `{driver: sandbox, config: {provider: docker, image}}` idempotently (T5 `environment`), sets it as the instance default (T5), archives `Local` (T5), doctor checks both (T6 via `--check`). "On the box": compose gains `works` (T3), `works-egress` (B) and the network (B); `install-box.sh --with-works` installs runsc (T4: one binary, one daemon.json stanza, one restart), enables the two services (T3/T4 profile); doctor gains runsc + proxy answers (T6, B); Caddy port 3003 on LAN and mesh (T3); console gains Works on `/choose` (T3 `PUBLIC_WORKS_URL`). "Testing" C: dry-run asserts the planned calls (T5 bash tests) and a fake Works API asserts idempotency (T5 second test); Box: `verify-ubuntu-box.sh` gains a Works step (T7 — the sandbox-shaped `uname -r`, doctor; an agent run end to end is stated as not asserted and why). Addendum 3 (sandbox image by digest): T1 + T4 pin + T5 register/re-pin. Addendum 4 (virtual key): T3 env + T5 mint. Addendum 5 (profile): T3. Addendum 6 (uid 1000 + docker gid, Ubuntu-only): T3 + T4. Left out, stated: `pi_local` disabled on the box (image does not ship `pi`); the `nufi_agent` gateway URL is per-agent config (README says so).

**Placeholders.** None: every step has its code. Two things the implementer must resolve by running: the `runsc --version` output pattern (T4 Step 4 names the command), and the exact `--resolve`/CA curl form in `verify-ubuntu-box.sh` (T7 Step 1 says to match step 1's).

**Type consistency.** `WORKS_SANDBOX_IMAGE`, `WORKS_BOX_KEY`, `WORKS_MODEL_KEY`, `NUFI_WORKS`, `DOCKER_GID`, `WORKS_PUBLIC_URL`, `WORKS_AUTH_SECRET`, `WORKS_OIDC_SECRET` are the same names in `.env.example` (T3), `render_env` (T4), compose (T3), `lib/works.sh` (T5), tests (T4–T6). The registrar's flags in `works_run` (T5 bash) match `argparse` (T5 python) and the bash test's expectations. `works_check` is defined in T5 and called in T6. The plugin path `/app/packages/plugins/sandbox-providers/docker` is the same in the registrar default and the fake's assertion. The environment lookup key `config.provider == "docker"` matches A's `driverKey`. Ports: 3003 in compose, Caddyfile, mesh renderer, console client redirect, `PAPERCLIP_PUBLIC_URL`, `works_wait`, doctor, the VM step.
