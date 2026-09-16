# Works on the box — piece A: the Docker+gVisor sandbox provider — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A seventh sandbox provider plugin, `docker`, that runs agent code in a Docker container under gVisor (`--runtime=runsc`) on an internal network, so a NuFi box can run NUFI Works without Kubernetes.

**Architecture:** A new package beside the six existing providers, implementing the same ten plugin hooks (read from the SDK's `protocol.ts`) and mapping each to one Docker Engine API call over the socket via `dockerode`. Every sandbox is created with the runtime, network, proxy environment, resource limits and read-only root the design fixes; none of those is configurable from the environment config. Tests run against a fake Docker Engine over HTTP so the calls the provider makes are asserted, not mocked away — the same shape as `test_ingest.py` and `test_nufi_cron.py` in `deploy/platform`.

**Tech Stack:** TypeScript, `@paperclipai/plugin-sdk` (workspace), `dockerode` (new, this package only), vitest. The package is **outside** the pnpm workspace (`pnpm-workspace.yaml` line 7 excludes `packages/plugins/sandbox-providers/**`), so it installs and tests on its own, exactly like `e2b`.

**Spec:** `docs/superpowers/specs/2026-09-16-works-on-box-design.md`, section "A — the Docker provider". Read it first; the "What every sandbox gets, and cannot change" list is the contract this plan enforces.

## Global Constraints

- **Provider key is the literal `docker`.** The manifest's `driverKey`, the config's `provider`, and piece C's registration all use this string.
- **`--runtime=runsc` is not configurable** (spec). The provider refuses to be healthy without it and never creates a container with any other runtime.
- **Every sandbox**: network `works-sandbox`, env `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`, `--memory`/`--cpus`/`--pids-limit` (defaults 2g / 2 / 512), read-only root with writable `/workspace` volume and `/tmp` tmpfs, **no** Docker socket (spec).
- **`apps/agents` is a guarded fork.** `nufi/check-fork-diff.sh` diffs every path under `apps/agents/` against upstream; a new package is a changed path. The new package directory **must be allowlisted in Task 1** or CI is red on the first commit.
- **CI runs no provider tests today** (`agents-ci.yml` has no step for `sandbox-providers/`). Task 7 adds one; until then green-locally is unverified, per the repo's own memory.
- Node built-ins and `dockerode` only. No shelling out to a `docker` binary — the `works` container will not have one.
- Run everything from `apps/agents/packages/plugins/sandbox-providers/docker/`. Install: `pnpm install`. Test: `pnpm test`. Typecheck: `pnpm typecheck`.
- Commit messages in English; no AI-authorship framing.

---

## File structure

All new, under `apps/agents/packages/plugins/sandbox-providers/docker/`:

| File | Responsibility |
|---|---|
| `package.json`, `tsconfig.json`, `vitest.config.ts` | copied from `../e2b/` with the name, description and dependency changed |
| `src/manifest.ts` | the plugin manifest: id, `driverKey: "docker"`, the config schema an operator sees |
| `src/config.ts` | parse + validate the environment config into a typed `DockerProviderConfig`; the defaults live here and nowhere else |
| `src/container-spec.ts` | pure: `DockerProviderConfig` + lease params → the exact `ContainerCreateOptions` sent to Docker. **This is where the non-negotiables are enforced.** |
| `src/docker.ts` | the thin `dockerode` wrapper the plugin calls: `health()`, `create()`, `start()`, `inspect()`, `stop()`, `remove()`, `exec()` |
| `src/plugin.ts` | the ten hooks, each a few lines that call the two files above |
| `src/worker.ts`, `src/index.ts` | identical to e2b's |
| `src/fake-docker.ts` | test-only: an HTTP server speaking enough of the Engine API to record what the provider asked for |
| `src/*.test.ts` | one test file per source file above |
| `README.md` | what it is, what every sandbox gets, the socket grant, how to run the tests |

Modified:

| File | Change |
|---|---|
| `apps/agents/nufi/check-fork-diff.sh` | add `"packages/plugins/sandbox-providers/docker/"` to `ALLOWLIST` |
| `.github/workflows/agents-ci.yml` | a job that installs and tests the new package |

---

### Task 1: The package exists, is allowlisted, and CI knows it

**Files:**
- Create: `apps/agents/packages/plugins/sandbox-providers/docker/{package.json,tsconfig.json,vitest.config.ts,src/index.ts,src/worker.ts,src/manifest.ts,src/manifest.test.ts}`
- Modify: `apps/agents/nufi/check-fork-diff.sh` (the `ALLOWLIST=(` array)
- Modify: `.github/workflows/agents-ci.yml`

**Interfaces:**
- Produces: the package `@nufi/plugin-docker-sandbox` with manifest `driverKey: "docker"`, `kind: "sandbox_provider"`. Later tasks add files to `src/`.

- [ ] **Step 1: Write the failing manifest test**

`src/manifest.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import manifest from "./manifest.js";

describe("manifest", () => {
  it("registers exactly one sandbox provider, keyed docker", () => {
    expect(manifest.capabilities).toContain("environment.drivers.register");
    expect(manifest.environmentDrivers).toHaveLength(1);
    const driver = manifest.environmentDrivers![0];
    expect(driver.driverKey).toBe("docker");
    expect(driver.kind).toBe("sandbox_provider");
  });

  it("exposes only what an operator may change — never the runtime", () => {
    const props = Object.keys(manifest.environmentDrivers![0].configSchema!.properties ?? {});
    expect(props).toEqual(expect.arrayContaining(["image", "memory", "cpus", "pidsLimit", "egressProxy", "timeoutMs"]));
    // A schema with a runtime field is a provider one config line away from runc.
    expect(props).not.toContain("runtime");
    expect(props).not.toContain("network");
    expect(props).not.toContain("privileged");
  });
});
```

- [ ] **Step 2: Scaffold the package**

`package.json` — copy `../e2b/package.json` and change these fields only:

```json
{
  "name": "@nufi/plugin-docker-sandbox",
  "version": "0.1.0",
  "description": "Docker+gVisor sandbox provider plugin for NUFI Works on the NuFi box",
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "https://github.com/dudaji-vn/nufi-app",
    "directory": "apps/agents/packages/plugins/sandbox-providers/docker"
  },
  "keywords": ["paperclip", "plugin", "sandbox", "docker", "gvisor", "nufi"],
  "dependencies": {
    "dockerode": "^4.0.2"
  },
  "devDependencies": {
    "@types/dockerode": "^3.3.31",
    "@types/node": "^24.6.0",
    "typescript": "^5.7.3",
    "vitest": "^4.1.8"
  }
}
```

Keep `type`, `exports`, `publishConfig`, `files`, `paperclipPlugin` and `scripts` exactly as e2b has them (the relative paths in `scripts` resolve the same from this directory). Drop `homepage` and `bugs`.

`tsconfig.json` and `vitest.config.ts`: byte-for-byte copies of e2b's.

`src/index.ts` and `src/worker.ts`: byte-for-byte copies of e2b's.

`src/manifest.ts`:

```ts
import type { PaperclipPluginManifestV1 } from "@paperclipai/plugin-sdk";

const PLUGIN_ID = "nufi.docker-sandbox-provider";
const PLUGIN_VERSION = "0.1.0";

const manifest: PaperclipPluginManifestV1 = {
  id: PLUGIN_ID,
  apiVersion: 1,
  version: PLUGIN_VERSION,
  displayName: "Docker + gVisor Sandbox Provider",
  description:
    "Runs agent code in a Docker container under gVisor on the NuFi box. Every sandbox is on an internal network with the egress proxy as its only way out.",
  author: "NuFi",
  categories: ["automation"],
  capabilities: ["environment.drivers.register"],
  entrypoints: {
    worker: "./dist/worker.js",
  },
  environmentDrivers: [
    {
      driverKey: "docker",
      kind: "sandbox_provider",
      displayName: "Docker + gVisor (NuFi box)",
      description:
        "A container per run under the runsc runtime, on the works-sandbox network, reaching the world only through works-egress.",
      // What an operator may change. Deliberately absent: runtime, network,
      // privileged, the socket. A provider that can be told to use runc is one
      // config line away from having no kernel boundary.
      configSchema: {
        type: "object",
        properties: {
          image: {
            type: "string",
            description:
              "Pinned image reference for the sandbox (tag or digest; a bare name is refused).",
            default: "ghcr.io/dudaji-vn/nufi-sandbox:main",
          },
          memory: {
            type: "string",
            description: "Memory limit, Docker syntax.",
            default: "2g",
          },
          cpus: {
            type: "number",
            description: "CPU limit, Docker syntax.",
            default: 2,
          },
          pidsLimit: {
            type: "number",
            description: "Process limit inside the sandbox.",
            default: 512,
          },
          egressProxy: {
            type: "string",
            description: "The forward proxy every sandbox is pointed at. Hostname:port on the works-sandbox network.",
            default: "works-egress:3128",
          },
          timeoutMs: {
            type: "number",
            description: "Sandbox lifetime in milliseconds; a lease older than this is not resumed.",
            default: 3600000,
          },
        },
      },
    },
  ],
};

export default manifest;
```

- [ ] **Step 3: Allowlist the package in the fork guard**

In `apps/agents/nufi/check-fork-diff.sh`, inside `ALLOWLIST=(`, after the `"nufi/"` line, add:

```bash
  # The Docker+gVisor sandbox provider for NUFI Works on the NuFi box. A
  # seventh provider beside upstream's six, in upstream's own plugin shape,
  # touching nothing of upstream's; see docs/superpowers/specs/2026-09-16-works-on-box-design.md.
  "packages/plugins/sandbox-providers/docker/"
```

- [ ] **Step 4: Install, run the test, confirm it passes, confirm the guard is green**

```bash
cd apps/agents/packages/plugins/sandbox-providers/docker
pnpm install
pnpm test
cd ../../../../../..   # repo root
./apps/agents/nufi/check-fork-diff.sh
```

Expected: `pnpm test` → 2 passed. `check-fork-diff.sh` → `OK — the fork diff is confined to the NuFi allowlist.` If it reports the new directory as a violation, the allowlist entry's trailing slash or path is wrong — it must be relative to `apps/agents/`.

- [ ] **Step 5: Add the CI job**

In `.github/workflows/agents-ci.yml`, add a job (read the file for its structure; match the indentation and the `on:` paths filter — add `apps/agents/packages/plugins/sandbox-providers/docker/**` to it if the filter is path-scoped):

```yaml
  docker-sandbox-provider:
    name: Docker sandbox provider
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      # The provider packages sit outside the pnpm workspace on purpose
      # (upstream publishes them standalone), so each installs on its own.
      # Nothing in this workflow ran any provider's tests before this job.
      - name: Install
        working-directory: apps/agents/packages/plugins/sandbox-providers/docker
        run: pnpm install
      - name: Typecheck
        working-directory: apps/agents/packages/plugins/sandbox-providers/docker
        run: pnpm typecheck
      - name: Test
        working-directory: apps/agents/packages/plugins/sandbox-providers/docker
        run: pnpm test
```

Check which `pnpm/action-setup` and node versions the file's other jobs use and match them.

- [ ] **Step 6: Commit**

```bash
git add apps/agents/packages/plugins/sandbox-providers/docker apps/agents/nufi/check-fork-diff.sh .github/workflows/agents-ci.yml
git commit -m "feat(agents): the docker sandbox provider package, allowlisted and in CI

A seventh provider beside upstream's six, in upstream's own plugin shape.
The manifest exposes image, limits, the proxy and a lifetime; it does not
expose the runtime, the network or privilege, and a test pins that -- a
provider that can be told to use runc is one config line away from no
kernel boundary.

Allowlisted in the fork guard, which diffs every path under apps/agents
and would otherwise fail on the first commit. And given a CI job: no
provider's tests ran in this workflow before, so green locally was the
only green there was."
```

---

### Task 2: Config parsing, with the defaults in one place

**Files:**
- Create: `src/config.ts`, `src/config.test.ts`

**Interfaces:**
- Produces:
  ```ts
  export interface DockerProviderConfig {
    image: string;        // pinned: has a tag or a digest
    memory: string;       // "2g"
    cpus: number;
    pidsLimit: number;
    egressProxy: string;  // "host:port"
    timeoutMs: number;
  }
  export const DEFAULTS: DockerProviderConfig;
  export function parseConfig(raw: Record<string, unknown>): DockerProviderConfig; // throws ConfigError
  export function validateConfig(raw: Record<string, unknown>): { ok: boolean; errors: string[]; warnings: string[] };
  export class ConfigError extends Error {}
  ```

- [ ] **Step 1: Write the failing tests**

`src/config.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { ConfigError, DEFAULTS, parseConfig, validateConfig } from "./config.js";

describe("parseConfig", () => {
  it("fills every default when given nothing", () => {
    expect(parseConfig({})).toEqual(DEFAULTS);
    expect(DEFAULTS.image).toMatch(/:/);   // the default itself is pinned
    expect(DEFAULTS.egressProxy).toBe("works-egress:3128");
  });

  it("takes what is given and keeps the rest", () => {
    const c = parseConfig({ image: "ghcr.io/dudaji-vn/nufi-sandbox:v1.2", cpus: 4 });
    expect(c.image).toBe("ghcr.io/dudaji-vn/nufi-sandbox:v1.2");
    expect(c.cpus).toBe(4);
    expect(c.memory).toBe(DEFAULTS.memory);
  });

  it("refuses an unpinned image — a bare name is whatever :latest is today", () => {
    expect(() => parseConfig({ image: "ghcr.io/dudaji-vn/nufi-sandbox" })).toThrow(ConfigError);
    expect(() => parseConfig({ image: "ghcr.io/dudaji-vn/nufi-sandbox" })).toThrow(/pinned/);
  });

  it("accepts a digest as pinned", () => {
    expect(parseConfig({ image: "ghcr.io/x/y@sha256:" + "a".repeat(64) }).image).toContain("@sha256:");
  });

  it("refuses limits that do not parse", () => {
    expect(() => parseConfig({ memory: "lots" })).toThrow(/memory/);
    expect(() => parseConfig({ cpus: 0 })).toThrow(/cpus/);
    expect(() => parseConfig({ cpus: "two" })).toThrow(/cpus/);
    expect(() => parseConfig({ pidsLimit: -1 })).toThrow(/pidsLimit/);
  });

  it("refuses a proxy that is not host:port", () => {
    expect(() => parseConfig({ egressProxy: "http://works-egress:3128" })).toThrow(/egressProxy/);
    expect(() => parseConfig({ egressProxy: "works-egress" })).toThrow(/egressProxy/);
  });

  it("ignores keys it does not know, so provider: docker in the stored config is fine", () => {
    expect(parseConfig({ provider: "docker", somethingElse: 1 })).toEqual(DEFAULTS);
  });
});

describe("validateConfig", () => {
  it("reports every problem at once, as errors, not by throwing", () => {
    const r = validateConfig({ image: "bare", cpus: 0 });
    expect(r.ok).toBe(false);
    expect(r.errors).toHaveLength(2);
    expect(r.errors.join(" ")).toMatch(/pinned/);
    expect(r.errors.join(" ")).toMatch(/cpus/);
  });
  it("is ok for the defaults", () => {
    expect(validateConfig({})).toEqual({ ok: true, errors: [], warnings: [] });
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm test -- src/config.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

`src/config.ts`:

```ts
/**
 * The environment config as an operator wrote it, checked and defaulted.
 *
 * This is the only file that knows a default value. `container-spec.ts`
 * consumes the parsed shape and never reaches into the raw one.
 */

export class ConfigError extends Error {}

export interface DockerProviderConfig {
  image: string;
  memory: string;
  cpus: number;
  pidsLimit: number;
  egressProxy: string;
  timeoutMs: number;
}

export const DEFAULTS: DockerProviderConfig = Object.freeze({
  image: "ghcr.io/dudaji-vn/nufi-sandbox:main",
  memory: "2g",
  cpus: 2,
  pidsLimit: 512,
  egressProxy: "works-egress:3128",
  timeoutMs: 3_600_000,
});

// A tag after the last slash, or a digest. `ghcr.io/x/y` alone is whatever
// :latest resolves to on the day, which is not a thing to run untrusted code in.
const PINNED_IMAGE = /^[^\s]+(:[\w][\w.-]{0,127}|@sha256:[0-9a-f]{64})$/;
const HOST_PORT = /^[a-zA-Z0-9.-]+:\d{1,5}$/;
const DOCKER_MEMORY = /^\d+(\.\d+)?[bkmg]?$/i;

type Problem = { field: keyof DockerProviderConfig; message: string };

function check(raw: Record<string, unknown>): { config: DockerProviderConfig; problems: Problem[] } {
  const problems: Problem[] = [];
  const out: DockerProviderConfig = { ...DEFAULTS };

  if (raw.image !== undefined) {
    if (typeof raw.image !== "string" || !PINNED_IMAGE.test(raw.image)) {
      problems.push({ field: "image", message: `image must be a pinned reference (tag or digest), got ${JSON.stringify(raw.image)}` });
    } else out.image = raw.image;
  }
  if (raw.memory !== undefined) {
    if (typeof raw.memory !== "string" || !DOCKER_MEMORY.test(raw.memory)) {
      problems.push({ field: "memory", message: `memory must be a Docker size like "2g", got ${JSON.stringify(raw.memory)}` });
    } else out.memory = raw.memory;
  }
  for (const field of ["cpus", "pidsLimit", "timeoutMs"] as const) {
    const v = raw[field];
    if (v === undefined) continue;
    if (typeof v !== "number" || !Number.isFinite(v) || v <= 0) {
      problems.push({ field, message: `${field} must be a positive number, got ${JSON.stringify(v)}` });
    } else out[field] = v;
  }
  if (raw.egressProxy !== undefined) {
    if (typeof raw.egressProxy !== "string" || !HOST_PORT.test(raw.egressProxy)) {
      problems.push({ field: "egressProxy", message: `egressProxy must be host:port (no scheme), got ${JSON.stringify(raw.egressProxy)}` });
    } else out.egressProxy = raw.egressProxy;
  }
  return { config: out, problems };
}

export function parseConfig(raw: Record<string, unknown>): DockerProviderConfig {
  const { config, problems } = check(raw);
  if (problems.length > 0) {
    throw new ConfigError(problems.map((p) => p.message).join("; "));
  }
  return config;
}

export function validateConfig(
  raw: Record<string, unknown>,
): { ok: boolean; errors: string[]; warnings: string[] } {
  const { problems } = check(raw);
  return { ok: problems.length === 0, errors: problems.map((p) => p.message), warnings: [] };
}
```

- [ ] **Step 4: Run — pass**

Run: `pnpm test -- src/config.test.ts`
Expected: PASS, all cases.

- [ ] **Step 5: Commit**

```bash
git add src/config.ts src/config.test.ts
git commit -m "feat(docker-provider): parse the environment config, defaults in one place

An unpinned image is refused: a bare name is whatever :latest resolves to
on the day, which is not a thing to run untrusted code in. validateConfig
reports every problem at once for the validate hook; parseConfig throws
for the hooks that need a usable config or none."
```

---

### Task 3: The container spec — where the non-negotiables live

**Files:**
- Create: `src/container-spec.ts`, `src/container-spec.test.ts`

**Interfaces:**
- Consumes: `DockerProviderConfig` (Task 2).
- Produces:
  ```ts
  export const SANDBOX_NETWORK = "works-sandbox";
  export const SANDBOX_RUNTIME = "runsc";
  export const WORKSPACE_DIR = "/workspace";
  export interface LeaseIdentity { runId: string; agentId?: string; companyId?: string }
  export function containerCreateOptions(config: DockerProviderConfig, lease: LeaseIdentity): Dockerode.ContainerCreateOptions;
  export function containerName(lease: LeaseIdentity): string;
  ```

- [ ] **Step 1: Write the failing tests**

`src/container-spec.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { DEFAULTS, parseConfig } from "./config.js";
import {
  SANDBOX_NETWORK,
  SANDBOX_RUNTIME,
  WORKSPACE_DIR,
  containerCreateOptions,
  containerName,
} from "./container-spec.js";

const lease = { runId: "run-42", agentId: "agent-7", companyId: "co-1" };

describe("containerCreateOptions — the things a sandbox cannot change", () => {
  const opts = containerCreateOptions(DEFAULTS, lease);
  const host = opts.HostConfig!;

  it("runs under gVisor, always", () => {
    expect(host.Runtime).toBe(SANDBOX_RUNTIME);
    expect(SANDBOX_RUNTIME).toBe("runsc");
  });

  it("is on the internal sandbox network and nothing else", () => {
    expect(host.NetworkMode).toBe(SANDBOX_NETWORK);
    expect(opts.NetworkingConfig?.EndpointsConfig).toEqual({ [SANDBOX_NETWORK]: {} });
  });

  it("is pointed at the egress proxy through the variables every HTTP client honours", () => {
    const env = Object.fromEntries((opts.Env ?? []).map((kv) => kv.split(/=(.*)/s).slice(0, 2)));
    expect(env.HTTP_PROXY).toBe("http://works-egress:3128");
    expect(env.HTTPS_PROXY).toBe("http://works-egress:3128");
    expect(env.http_proxy).toBe("http://works-egress:3128");
    expect(env.https_proxy).toBe("http://works-egress:3128");
    expect(env.NO_PROXY).toBe("localhost,127.0.0.1");
  });

  it("is bounded", () => {
    expect(host.Memory).toBe(2 * 1024 ** 3);
    expect(host.NanoCpus).toBe(2e9);
    expect(host.PidsLimit).toBe(512);
  });

  it("has a read-only root, a writable workspace and a tmpfs /tmp", () => {
    expect(host.ReadonlyRootfs).toBe(true);
    expect(host.Tmpfs).toEqual({ "/tmp": "rw,noexec,nosuid,size=256m" });
    expect(host.Mounts).toEqual([
      { Type: "volume", Source: `works-sandbox-${lease.runId}`, Target: WORKSPACE_DIR },
    ]);
    expect(opts.WorkingDir).toBe(WORKSPACE_DIR);
  });

  it("has no Docker socket, no privilege, no added capabilities", () => {
    expect(host.Privileged).toBeFalsy();
    expect(host.CapAdd).toBeUndefined();
    expect(host.CapDrop).toEqual(["ALL"]);
    expect(JSON.stringify(opts)).not.toContain("docker.sock");
  });

  it("uses the configured image and labels the run", () => {
    expect(opts.Image).toBe(DEFAULTS.image);
    expect(opts.Labels).toEqual({
      "me.nufi.works.run": "run-42",
      "me.nufi.works.agent": "agent-7",
      "me.nufi.works.company": "co-1",
    });
  });

  it("stays up waiting for exec, and is not auto-removed — the lease owns its lifetime", () => {
    expect(opts.Cmd).toEqual(["sleep", "infinity"]);
    expect(host.AutoRemove).toBeFalsy();
  });
});

describe("containerCreateOptions — the things the config does change", () => {
  it("memory and cpus follow the config", () => {
    const opts = containerCreateOptions(parseConfig({ memory: "512m", cpus: 1 }), lease);
    expect(opts.HostConfig!.Memory).toBe(512 * 1024 ** 2);
    expect(opts.HostConfig!.NanoCpus).toBe(1e9);
  });
  it("the proxy follows the config", () => {
    const opts = containerCreateOptions(parseConfig({ egressProxy: "proxy.internal:8080" }), lease);
    expect(opts.Env).toContain("HTTPS_PROXY=http://proxy.internal:8080");
  });
});

describe("containerName", () => {
  it("is derived from the run and safe for Docker", () => {
    expect(containerName({ runId: "run-42" })).toBe("works-sandbox-run-42");
    expect(containerName({ runId: "a/b c" })).toMatch(/^works-sandbox-[a-zA-Z0-9_.-]+$/);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm test -- src/container-spec.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

`src/container-spec.ts`:

```ts
/**
 * From a parsed config and a lease, the exact create request sent to Docker.
 *
 * Pure, so the whole contract of "what every sandbox gets and cannot change"
 * is one function with one test file. Nothing in here reads the raw config
 * and nothing in here talks to Docker.
 */
import type Dockerode from "dockerode";
import type { DockerProviderConfig } from "./config.js";

export const SANDBOX_NETWORK = "works-sandbox";
export const SANDBOX_RUNTIME = "runsc";
export const WORKSPACE_DIR = "/workspace";

export interface LeaseIdentity {
  runId: string;
  agentId?: string;
  companyId?: string;
}

const UNIT: Record<string, number> = { b: 1, k: 1024, m: 1024 ** 2, g: 1024 ** 3 };

/** "2g" → bytes. config.ts has already refused anything this cannot parse. */
export function memoryBytes(size: string): number {
  const m = /^(\d+(?:\.\d+)?)([bkmg]?)$/i.exec(size)!;
  return Math.round(Number(m[1]) * UNIT[(m[2] || "b").toLowerCase()]);
}

const SAFE_NAME = /[^a-zA-Z0-9_.-]/g;

export function containerName(lease: LeaseIdentity): string {
  return `works-sandbox-${lease.runId.replace(SAFE_NAME, "-")}`;
}

export function containerCreateOptions(
  config: DockerProviderConfig,
  lease: LeaseIdentity,
): Dockerode.ContainerCreateOptions {
  const proxy = `http://${config.egressProxy}`;
  const labels: Record<string, string> = { "me.nufi.works.run": lease.runId };
  if (lease.agentId) labels["me.nufi.works.agent"] = lease.agentId;
  if (lease.companyId) labels["me.nufi.works.company"] = lease.companyId;

  return {
    name: containerName(lease),
    Image: config.image,
    // Stay up and wait for exec; the lease decides when this container ends.
    Cmd: ["sleep", "infinity"],
    WorkingDir: WORKSPACE_DIR,
    Labels: labels,
    // Both cases: libraries disagree on which they read, and a client that
    // ignores both has no route anyway -- the network is internal.
    Env: [
      `HTTP_PROXY=${proxy}`,
      `HTTPS_PROXY=${proxy}`,
      `http_proxy=${proxy}`,
      `https_proxy=${proxy}`,
      "NO_PROXY=localhost,127.0.0.1",
      "no_proxy=localhost,127.0.0.1",
    ],
    NetworkingConfig: { EndpointsConfig: { [SANDBOX_NETWORK]: {} } },
    HostConfig: {
      // The kernel boundary. Not a config option, by design.
      Runtime: SANDBOX_RUNTIME,
      NetworkMode: SANDBOX_NETWORK,
      Memory: memoryBytes(config.memory),
      NanoCpus: Math.round(config.cpus * 1e9),
      PidsLimit: config.pidsLimit,
      ReadonlyRootfs: true,
      Tmpfs: { "/tmp": "rw,noexec,nosuid,size=256m" },
      Mounts: [
        { Type: "volume", Source: `works-sandbox-${lease.runId}`, Target: WORKSPACE_DIR },
      ],
      CapDrop: ["ALL"],
      SecurityOpt: ["no-new-privileges"],
      // The lease owns the lifetime; an auto-removed container would vanish
      // between execs.
      AutoRemove: false,
    },
  };
}
```

Note: the `Mounts` volume name uses the raw `runId`; if a run id can contain characters Docker rejects in a volume name, use `containerName(lease)` for the volume name too. The test uses a plain id; add a case if the host's run ids turn out not to be plain.

- [ ] **Step 4: Run — pass**

Run: `pnpm test -- src/container-spec.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/container-spec.ts src/container-spec.test.ts
git commit -m "feat(docker-provider): the container spec, and the things a sandbox cannot change

One pure function from config and lease to the create request, so the
whole contract -- runsc, the internal network, the proxy in the
environment, limits, a read-only root, no socket, no capabilities -- is a
single test file. The config changes the image, the limits and the proxy
address; it cannot reach the runtime or the network, and a test says so."
```

---

### Task 4: The fake Docker Engine, for tests

**Files:**
- Create: `src/fake-docker.ts`, `src/fake-docker.test.ts`

**Interfaces:**
- Produces:
  ```ts
  export class FakeDocker {
    static start(opts?: { runtimes?: string[] }): Promise<FakeDocker>;
    readonly socketPath: string;          // a unix socket dockerode can dial
    readonly calls: Array<{ method: string; path: string; body?: unknown }>;
    containers: Map<string, { id: string; name: string; create: unknown; running: boolean }>;
    execScript(handler: (cmd: string[]) => { exitCode: number; stdout: string; stderr: string; delayMs?: number }): void;
    stop(): Promise<void>;
  }
  ```
  It speaks: `GET /info`, `GET /_ping`, `POST /containers/create`, `POST /containers/{id}/start`, `GET /containers/{id}/json`, `POST /containers/{id}/stop`, `DELETE /containers/{id}`, `POST /containers/{id}/exec`, `POST /exec/{id}/start` (returning a multiplexed stream), `GET /exec/{id}/json`.

- [ ] **Step 1: Write the failing test**

`src/fake-docker.test.ts`:

```ts
import Dockerode from "dockerode";
import { afterEach, describe, expect, it } from "vitest";
import { FakeDocker } from "./fake-docker.js";

let fake: FakeDocker;
afterEach(async () => { await fake?.stop(); });

describe("FakeDocker speaks enough of the Engine API for dockerode", () => {
  it("answers info with the runtimes it was started with", async () => {
    fake = await FakeDocker.start({ runtimes: ["runc", "runsc"] });
    const docker = new Dockerode({ socketPath: fake.socketPath });
    const info = await docker.info();
    expect(Object.keys(info.Runtimes)).toEqual(["runc", "runsc"]);
  });

  it("creates, starts, inspects, stops and removes a container, recording each call", async () => {
    fake = await FakeDocker.start();
    const docker = new Dockerode({ socketPath: fake.socketPath });
    const c = await docker.createContainer({ Image: "alpine:3.20", name: "t1", HostConfig: { Runtime: "runsc" } });
    await c.start();
    expect((await c.inspect()).State.Running).toBe(true);
    await c.stop();
    expect((await c.inspect()).State.Running).toBe(false);
    await c.remove({ force: true });
    await expect(c.inspect()).rejects.toThrow(/404|no such/i);
    expect(fake.calls.map((x) => `${x.method} ${x.path.replace(/[0-9a-f]{12,}/, "{id}")}`)).toEqual([
      "POST /containers/create",
      "POST /containers/{id}/start",
      "GET /containers/{id}/json",
      "POST /containers/{id}/stop",
      "GET /containers/{id}/json",
      "DELETE /containers/{id}",
      "GET /containers/{id}/json",
    ]);
    // The create body is recorded verbatim, which is what the provider tests assert on.
    expect((fake.calls[0].body as { HostConfig: { Runtime: string } }).HostConfig.Runtime).toBe("runsc");
  });

  it("runs an exec through the scripted handler and returns its exit code and streams", async () => {
    fake = await FakeDocker.start();
    fake.execScript((cmd) => ({ exitCode: cmd[0] === "false" ? 1 : 0, stdout: `ran ${cmd.join(" ")}\n`, stderr: "" }));
    const docker = new Dockerode({ socketPath: fake.socketPath });
    const c = await docker.createContainer({ Image: "alpine:3.20", name: "t2" });
    await c.start();
    const exec = await c.exec({ Cmd: ["echo", "hi"], AttachStdout: true, AttachStderr: true });
    const stream = await exec.start({});
    const chunks: Buffer[] = [];
    await new Promise<void>((resolve) => { stream.on("data", (d: Buffer) => chunks.push(d)); stream.on("end", resolve); });
    expect((await exec.inspect()).ExitCode).toBe(0);
    // Multiplexed frames: 8-byte header then payload; the provider demuxes with dockerode's modem.
    expect(Buffer.concat(chunks).length).toBeGreaterThan(8);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm test -- src/fake-docker.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the fake**

`src/fake-docker.ts` — a `node:http` server on a unix socket under `os.tmpdir()`. Routes, in order of matching; every handler first pushes `{ method, path, body }` onto `calls`:

```ts
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { randomBytes } from "node:crypto";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

type ExecHandler = (cmd: string[]) => { exitCode: number; stdout: string; stderr: string; delayMs?: number };

interface FakeContainer { id: string; name: string; create: unknown; running: boolean }
interface FakeExec { id: string; containerId: string; cmd: string[]; exitCode: number | null; running: boolean }

export class FakeDocker {
  readonly calls: Array<{ method: string; path: string; body?: unknown }> = [];
  readonly containers = new Map<string, FakeContainer>();
  private readonly execs = new Map<string, FakeExec>();
  private execHandler: ExecHandler = () => ({ exitCode: 0, stdout: "", stderr: "" });
  private server!: Server;
  readonly socketPath: string;

  private constructor(private readonly runtimes: string[]) {
    this.socketPath = join(mkdtempSync(join(tmpdir(), "fake-docker-")), "docker.sock");
  }

  static async start(opts: { runtimes?: string[] } = {}): Promise<FakeDocker> {
    const fake = new FakeDocker(opts.runtimes ?? ["runc", "runsc"]);
    fake.server = createServer((req, res) => void fake.handle(req, res));
    await new Promise<void>((resolve) => fake.server.listen(fake.socketPath, resolve));
    return fake;
  }

  execScript(handler: ExecHandler): void { this.execHandler = handler; }

  async stop(): Promise<void> {
    await new Promise<void>((resolve) => this.server.close(() => resolve()));
  }

  private async handle(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const url = new URL(req.url ?? "/", "http://docker");
    // dockerode prefixes a version: /v1.47/containers/json
    const path = url.pathname.replace(/^\/v[\d.]+/, "");
    const body = await readJson(req);
    this.calls.push({ method: req.method ?? "GET", path, body });
    const json = (code: number, obj: unknown) => {
      res.writeHead(code, { "Content-Type": "application/json" });
      res.end(JSON.stringify(obj));
    };
    let m: RegExpExecArray | null;

    if (path === "/_ping") return void res.end("OK");
    if (path === "/info") {
      return json(200, { ServerVersion: "fake", Runtimes: Object.fromEntries(this.runtimes.map((r) => [r, { path: r }])) });
    }
    if (path === "/containers/create" && req.method === "POST") {
      const id = randomBytes(32).toString("hex");
      const name = url.searchParams.get("name") ?? (body as { name?: string })?.name ?? id.slice(0, 12);
      this.containers.set(id, { id, name, create: body, running: false });
      return json(201, { Id: id, Warnings: [] });
    }
    if ((m = /^\/containers\/([^/]+)\/start$/.exec(path)) && req.method === "POST") {
      const c = this.find(m[1]); if (!c) return json(404, { message: "no such container" });
      c.running = true; res.writeHead(204); return void res.end();
    }
    if ((m = /^\/containers\/([^/]+)\/stop$/.exec(path)) && req.method === "POST") {
      const c = this.find(m[1]); if (!c) return json(404, { message: "no such container" });
      c.running = false; res.writeHead(204); return void res.end();
    }
    if ((m = /^\/containers\/([^/]+)\/json$/.exec(path))) {
      const c = this.find(m[1]); if (!c) return json(404, { message: "no such container" });
      return json(200, { Id: c.id, Name: `/${c.name}`, State: { Running: c.running, Status: c.running ? "running" : "exited" }, Config: (c.create as { Env?: string[] }) ?? {}, HostConfig: (c.create as { HostConfig?: unknown })?.HostConfig ?? {} });
    }
    if ((m = /^\/containers\/([^/]+)$/.exec(path)) && req.method === "DELETE") {
      const c = this.find(m[1]); if (!c) return json(404, { message: "no such container" });
      this.containers.delete(c.id); res.writeHead(204); return void res.end();
    }
    if ((m = /^\/containers\/([^/]+)\/exec$/.exec(path)) && req.method === "POST") {
      const c = this.find(m[1]); if (!c) return json(404, { message: "no such container" });
      const id = randomBytes(32).toString("hex");
      this.execs.set(id, { id, containerId: c.id, cmd: (body as { Cmd: string[] }).Cmd, exitCode: null, running: false });
      return json(201, { Id: id });
    }
    if ((m = /^\/exec\/([^/]+)\/start$/.exec(path)) && req.method === "POST") {
      const e = this.execs.get(m[1]); if (!e) return json(404, { message: "no such exec" });
      e.running = true;
      const r = this.execHandler(e.cmd);
      res.writeHead(200, { "Content-Type": "application/vnd.docker.raw-stream" });
      const finish = () => {
        // Docker multiplexed stream: [type(1) 0 0 0 len(4 BE)] + payload, type 1=stdout 2=stderr
        for (const [type, text] of [[1, r.stdout], [2, r.stderr]] as const) {
          if (!text) continue;
          const payload = Buffer.from(text);
          const header = Buffer.alloc(8); header[0] = type; header.writeUInt32BE(payload.length, 4);
          res.write(Buffer.concat([header, payload]));
        }
        e.exitCode = r.exitCode; e.running = false; res.end();
      };
      if (r.delayMs) setTimeout(finish, r.delayMs); else finish();
      return;
    }
    if ((m = /^\/exec\/([^/]+)\/json$/.exec(path))) {
      const e = this.execs.get(m[1]); if (!e) return json(404, { message: "no such exec" });
      return json(200, { ID: e.id, Running: e.running, ExitCode: e.exitCode, ContainerID: e.containerId });
    }
    json(404, { message: `fake docker: no route for ${req.method} ${path}` });
  }

  private find(idOrName: string): FakeContainer | undefined {
    return this.containers.get(idOrName)
      ?? [...this.containers.values()].find((c) => c.name === idOrName || c.id.startsWith(idOrName));
  }
}

async function readJson(req: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  if (chunks.length === 0) return undefined;
  const text = Buffer.concat(chunks).toString("utf8");
  try { return JSON.parse(text); } catch { return text; }
}
```

- [ ] **Step 4: Run — pass**

Run: `pnpm test -- src/fake-docker.test.ts`
Expected: PASS. If dockerode's exec stream test hangs, the fake's `/exec/{id}/start` must end the response (it does, via `finish`); if the version prefix strip fails, print `path` in the 404 message and adjust the regex.

- [ ] **Step 5: Commit**

```bash
git add src/fake-docker.ts src/fake-docker.test.ts
git commit -m "test(docker-provider): a fake Docker Engine over a unix socket

Speaks the nine routes the provider uses and records every call with its
body, so the provider tests assert what was actually asked of Docker --
the runtime, the network, the mounts -- rather than that a mock was
called. Same shape as the fake app in test_ingest.py."
```

---

### Task 5: The Docker wrapper and the exec deadline

**Files:**
- Create: `src/docker.ts`, `src/docker.test.ts`

**Interfaces:**
- Consumes: `FakeDocker` (tests only).
- Produces:
  ```ts
  export interface ExecResult { exitCode: number | null; stdout: string; stderr: string; timedOut: boolean }
  export class DockerClient {
    constructor(opts?: { socketPath?: string });
    health(): Promise<{ ok: true } | { ok: false; reason: string }>;   // reachable AND runsc present
    create(options: Dockerode.ContainerCreateOptions): Promise<string>;  // id
    start(id: string): Promise<void>;
    inspect(id: string): Promise<{ exists: boolean; running: boolean }>;
    stop(id: string): Promise<void>;
    remove(id: string): Promise<void>;
    exec(id: string, cmd: string[], opts: { cwd?: string; env?: Record<string,string>; stdin?: string; timeoutMs?: number }): Promise<ExecResult>;
  }
  ```

- [ ] **Step 1: Write the failing tests**

`src/docker.test.ts`:

```ts
import { afterEach, describe, expect, it } from "vitest";
import { DockerClient } from "./docker.js";
import { FakeDocker } from "./fake-docker.js";

let fake: FakeDocker;
afterEach(async () => { await fake?.stop(); });

describe("health", () => {
  it("is ok when the daemon answers and runsc is a runtime", async () => {
    fake = await FakeDocker.start({ runtimes: ["runc", "runsc"] });
    expect(await new DockerClient({ socketPath: fake.socketPath }).health()).toEqual({ ok: true });
  });
  it("names the missing runtime — a daemon without runsc is not a healthy provider", async () => {
    fake = await FakeDocker.start({ runtimes: ["runc"] });
    const h = await new DockerClient({ socketPath: fake.socketPath }).health();
    expect(h.ok).toBe(false);
    if (!h.ok) expect(h.reason).toMatch(/runsc/);
  });
  it("names an unreachable daemon", async () => {
    const h = await new DockerClient({ socketPath: "/nonexistent/docker.sock" }).health();
    expect(h.ok).toBe(false);
    if (!h.ok) expect(h.reason).toMatch(/reach|connect|ENOENT/i);
  });
});

describe("exec", () => {
  it("returns exit code, stdout and stderr, demultiplexed", async () => {
    fake = await FakeDocker.start();
    fake.execScript((cmd) => ({ exitCode: 3, stdout: `out:${cmd[1]}`, stderr: "warn" }));
    const d = new DockerClient({ socketPath: fake.socketPath });
    const id = await d.create({ Image: "x:1", name: "e1" }); await d.start(id);
    const r = await d.exec(id, ["echo", "hi"], {});
    expect(r).toEqual({ exitCode: 3, stdout: "out:hi", stderr: "warn", timedOut: false });
  });

  it("passes cwd and env through, and stdin when given", async () => {
    fake = await FakeDocker.start();
    const d = new DockerClient({ socketPath: fake.socketPath });
    const id = await d.create({ Image: "x:1", name: "e2" }); await d.start(id);
    await d.exec(id, ["pwd"], { cwd: "/workspace/sub", env: { FOO: "bar" }, stdin: "data" });
    const execCreate = fake.calls.find((c) => /\/containers\/[^/]+\/exec$/.test(c.path))!.body as Record<string, unknown>;
    expect(execCreate.WorkingDir).toBe("/workspace/sub");
    expect(execCreate.Env).toEqual(["FOO=bar"]);
    expect(execCreate.AttachStdin).toBe(true);
  });

  it("kills a command that outstays timeoutMs and says so — it does not just stop listening", async () => {
    fake = await FakeDocker.start();
    fake.execScript(() => ({ exitCode: 0, stdout: "late", stderr: "", delayMs: 2000 }));
    const d = new DockerClient({ socketPath: fake.socketPath });
    const id = await d.create({ Image: "x:1", name: "e3" }); await d.start(id);
    const t0 = Date.now();
    const r = await d.exec(id, ["sleep", "10"], { timeoutMs: 200 });
    expect(Date.now() - t0).toBeLessThan(1500);
    expect(r.timedOut).toBe(true);
    expect(r.exitCode).toBeNull();
    // The deadline is enforced on the box, not only in the caller: the
    // container the exec was running in is stopped, which is the only handle
    // the Engine API gives us on a running exec.
    expect(fake.calls.some((c) => /\/containers\/[^/]+\/stop$/.test(c.path))).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm test -- src/docker.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

`src/docker.ts`:

```ts
/**
 * The thin edge between the plugin and the Engine API. Everything Docker-
 * specific -- multiplexed streams, 404 shapes, how a deadline is enforced --
 * is here, so plugin.ts reads as the ten hooks and nothing else.
 */
import Dockerode from "dockerode";
import { PassThrough } from "node:stream";
import { SANDBOX_RUNTIME } from "./container-spec.js";

export interface ExecResult {
  exitCode: number | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
}

export class DockerClient {
  private readonly docker: Dockerode;

  constructor(opts: { socketPath?: string } = {}) {
    this.docker = new Dockerode({ socketPath: opts.socketPath ?? "/var/run/docker.sock" });
  }

  async health(): Promise<{ ok: true } | { ok: false; reason: string }> {
    let info: { Runtimes?: Record<string, unknown> };
    try {
      info = await this.docker.info();
    } catch (err) {
      return { ok: false, reason: `cannot reach the Docker daemon: ${(err as Error).message}` };
    }
    if (!info.Runtimes || !(SANDBOX_RUNTIME in info.Runtimes)) {
      return {
        ok: false,
        reason: `Docker has no "${SANDBOX_RUNTIME}" runtime (has: ${Object.keys(info.Runtimes ?? {}).join(", ") || "none"}); gVisor is not installed on this box`,
      };
    }
    return { ok: true };
  }

  async create(options: Dockerode.ContainerCreateOptions): Promise<string> {
    const c = await this.docker.createContainer(options);
    return c.id;
  }

  async start(id: string): Promise<void> {
    await this.docker.getContainer(id).start();
  }

  async inspect(id: string): Promise<{ exists: boolean; running: boolean }> {
    try {
      const info = await this.docker.getContainer(id).inspect();
      return { exists: true, running: Boolean(info.State?.Running) };
    } catch (err) {
      if ((err as { statusCode?: number }).statusCode === 404) return { exists: false, running: false };
      throw err;
    }
  }

  async stop(id: string): Promise<void> {
    try {
      await this.docker.getContainer(id).stop({ t: 5 });
    } catch (err) {
      const code = (err as { statusCode?: number }).statusCode;
      if (code === 304 || code === 404) return; // already stopped, or gone
      throw err;
    }
  }

  async remove(id: string): Promise<void> {
    try {
      await this.docker.getContainer(id).remove({ force: true, v: true });
    } catch (err) {
      if ((err as { statusCode?: number }).statusCode === 404) return;
      throw err;
    }
  }

  async exec(
    id: string,
    cmd: string[],
    opts: { cwd?: string; env?: Record<string, string>; stdin?: string; timeoutMs?: number },
  ): Promise<ExecResult> {
    const container = this.docker.getContainer(id);
    const exec = await container.exec({
      Cmd: cmd,
      WorkingDir: opts.cwd,
      Env: opts.env ? Object.entries(opts.env).map(([k, v]) => `${k}=${v}`) : undefined,
      AttachStdout: true,
      AttachStderr: true,
      AttachStdin: opts.stdin !== undefined,
    });

    const stream = await exec.start({ hijack: opts.stdin !== undefined, stdin: opts.stdin !== undefined });
    const stdout = new PassThrough();
    const stderr = new PassThrough();
    const outChunks: Buffer[] = [];
    const errChunks: Buffer[] = [];
    stdout.on("data", (d: Buffer) => outChunks.push(d));
    stderr.on("data", (d: Buffer) => errChunks.push(d));
    this.docker.modem.demuxStream(stream, stdout, stderr);
    if (opts.stdin !== undefined) {
      stream.write(opts.stdin);
      stream.end();
    }

    const ended = new Promise<void>((resolve) => stream.on("end", () => resolve()));
    let timedOut = false;
    let timer: NodeJS.Timeout | undefined;
    const deadline = opts.timeoutMs
      ? new Promise<void>((resolve) => {
          timer = setTimeout(() => { timedOut = true; resolve(); }, opts.timeoutMs);
        })
      : new Promise<void>(() => {});

    await Promise.race([ended, deadline]);
    if (timer) clearTimeout(timer);

    if (timedOut) {
      // The Engine API has no "kill this exec". Stopping the container is the
      // one handle it gives, and it is the right one: a lease whose command
      // has outstayed its deadline is a lease the caller is about to give up
      // on. Stopping here is what makes the deadline real rather than a
      // client that walked away from a process still running.
      stream.destroy();
      await this.stop(id);
      return { exitCode: null, stdout: Buffer.concat(outChunks).toString("utf8"), stderr: Buffer.concat(errChunks).toString("utf8"), timedOut: true };
    }

    const info = await exec.inspect();
    return {
      exitCode: info.ExitCode ?? null,
      stdout: Buffer.concat(outChunks).toString("utf8"),
      stderr: Buffer.concat(errChunks).toString("utf8"),
      timedOut: false,
    };
  }
}
```

- [ ] **Step 4: Run — pass**

Run: `pnpm test -- src/docker.test.ts`
Expected: PASS. The timeout case must finish in well under 1.5 s and must record a `/stop` call — that assertion is the whole point of the test.

- [ ] **Step 5: Commit**

```bash
git add src/docker.ts src/docker.test.ts
git commit -m "feat(docker-provider): the Engine API edge, with a deadline that stops the container

health() is red without runsc, naming what Docker does have. exec()
demultiplexes the stream and, when a command outstays timeoutMs, stops
the container rather than merely stopping to listen -- the Engine API has
no handle on a running exec, and a client that walks away from a process
still running is the failure the whole design exists to avoid. The test
asserts the stop call arrived."
```

---

### Task 6: The plugin — ten hooks

**Files:**
- Create: `src/plugin.ts`, `src/plugin.test.ts`

**Interfaces:**
- Consumes: `parseConfig`, `validateConfig` (Task 2); `containerCreateOptions`, `WORKSPACE_DIR` (Task 3); `DockerClient` (Task 5); `FakeDocker` (tests).
- Produces: the default export `plugin`, built with the SDK's `definePlugin` (read `../e2b/src/plugin.ts` line 217 for the exact call and its import block for the hook parameter types). `definePlugin` takes the hooks only — the manifest is not passed to it; `package.json`'s `paperclipPlugin.manifest` points at it — and returns `{ definition }`, so tests reach hooks as `plugin.definition.onHealth()`.
- The `DockerClient` is constructed once in `setup(ctx)` and reused. For tests, the socket path is read from `process.env.NUFI_DOCKER_SOCKET` when set — a test-only override, documented as such in the code.

- [ ] **Step 1: Write the failing tests**

`src/plugin.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { FakeDocker } from "./fake-docker.js";
import plugin from "./plugin.js";
import { SANDBOX_NETWORK, SANDBOX_RUNTIME } from "./container-spec.js";

// definePlugin returns { definition }; the hooks live one level down.
const hooks = plugin.definition;

let fake: FakeDocker;
const ctx = { logger: { info() {}, warn() {}, error() {}, debug() {} } };
const base = { environmentId: "env-1", companyId: "co-1" };

beforeEach(async () => {
  fake = await FakeDocker.start();
  process.env.NUFI_DOCKER_SOCKET = fake.socketPath;
  await hooks.setup!(ctx as never);
});
afterEach(async () => { delete process.env.NUFI_DOCKER_SOCKET; await fake.stop(); });

describe("health and probe", () => {
  it("is healthy with runsc present", async () => {
    expect((await hooks.onHealth!()).status).toBe("ok");
  });
  it("is not healthy without runsc, and says why", async () => {
    await fake.stop();
    fake = await FakeDocker.start({ runtimes: ["runc"] });
    process.env.NUFI_DOCKER_SOCKET = fake.socketPath;
    await hooks.setup!(ctx as never);
    const h = await hooks.onHealth!();
    expect(h.status).toBe("error");
    expect(h.message).toMatch(/runsc/);
  });
});

describe("validate", () => {
  it("passes the config through validateConfig", async () => {
    const r = await hooks.onEnvironmentValidateConfig!({ ...base, config: { image: "bare" } } as never);
    expect(r.ok).toBe(false);
    expect(r.errors![0]).toMatch(/pinned/);
  });
});

describe("the lease lifecycle", () => {
  it("acquire creates and starts a container built from the spec, and returns its id", async () => {
    const lease = await hooks.onEnvironmentAcquireLease!({ ...base, config: {}, runId: "run-1", agentId: "a-1" } as never);
    expect(lease.providerLeaseId).toBeTruthy();
    const create = fake.calls.find((c) => c.path === "/containers/create")!.body as { HostConfig: Record<string, unknown>; Env: string[] };
    expect(create.HostConfig.Runtime).toBe(SANDBOX_RUNTIME);
    expect(create.HostConfig.NetworkMode).toBe(SANDBOX_NETWORK);
    expect(create.Env).toContain("HTTPS_PROXY=http://works-egress:3128");
    expect(fake.calls.some((c) => c.path.endsWith("/start"))).toBe(true);
    expect(fake.containers.get(lease.providerLeaseId!)?.running).toBe(true);
  });

  it("never asks for any runtime but runsc, whatever the config says", async () => {
    await hooks.onEnvironmentAcquireLease!({ ...base, config: { runtime: "runc", privileged: true }, runId: "run-2" } as never);
    const create = fake.calls.find((c) => c.path === "/containers/create")!.body as { HostConfig: Record<string, unknown> };
    expect(create.HostConfig.Runtime).toBe("runsc");
    expect(create.HostConfig.Privileged).toBeFalsy();
  });

  it("resume reattaches to a stopped container and starts it", async () => {
    const lease = await hooks.onEnvironmentAcquireLease!({ ...base, config: {}, runId: "run-3" } as never);
    await hooks.onEnvironmentReleaseLease!({ ...base, config: {}, lease } as never);
    expect(fake.containers.get(lease.providerLeaseId!)?.running).toBe(false);
    const resumed = await hooks.onEnvironmentResumeLease!({ ...base, config: {}, lease } as never);
    expect(resumed.providerLeaseId).toBe(lease.providerLeaseId);
    expect(fake.containers.get(lease.providerLeaseId!)?.running).toBe(true);
  });

  it("resume of a container that is gone fails rather than silently making a new one", async () => {
    await expect(
      hooks.onEnvironmentResumeLease!({ ...base, config: {}, lease: { providerLeaseId: "deadbeef".repeat(8) } } as never),
    ).rejects.toThrow(/no longer exists|not found|gone/i);
  });

  it("destroy removes the container", async () => {
    const lease = await hooks.onEnvironmentAcquireLease!({ ...base, config: {}, runId: "run-4" } as never);
    await hooks.onEnvironmentDestroyLease!({ ...base, config: {}, lease } as never);
    expect(fake.containers.has(lease.providerLeaseId!)).toBe(false);
  });
});

describe("workspace and execute", () => {
  it("realize creates the working directory inside the sandbox and returns it", async () => {
    fake.execScript(() => ({ exitCode: 0, stdout: "", stderr: "" }));
    const lease = await hooks.onEnvironmentAcquireLease!({ ...base, config: {}, runId: "run-5" } as never);
    const r = await hooks.onEnvironmentRealizeWorkspace!({ ...base, config: {}, lease, workspace: { remotePath: "/workspace/proj" } } as never);
    expect(r.cwd).toBe("/workspace/proj");
    const mk = fake.calls.find((c) => /\/exec$/.test(c.path))!.body as { Cmd: string[] };
    expect(mk.Cmd).toEqual(["mkdir", "-p", "/workspace/proj"]);
  });

  it("execute runs the command and returns the result shape the host expects", async () => {
    fake.execScript((cmd) => ({ exitCode: 0, stdout: `${cmd.join(" ")}\n`, stderr: "" }));
    const lease = await hooks.onEnvironmentAcquireLease!({ ...base, config: {}, runId: "run-6" } as never);
    const r = await hooks.onEnvironmentExecute!({ ...base, config: {}, lease, command: "uname", args: ["-r"], cwd: "/workspace", timeoutMs: 5000 } as never);
    expect(r).toMatchObject({ exitCode: 0, timedOut: false, stdout: "uname -r\n", stderr: "" });
  });

  it("execute with no lease id returns a failed result, not a throw", async () => {
    const r = await hooks.onEnvironmentExecute!({ ...base, config: {}, lease: { providerLeaseId: null }, command: "true" } as never);
    expect(r.exitCode).toBe(1);
    expect(r.stderr).toMatch(/lease/i);
  });

  it("execute honours the deadline and reports timedOut", async () => {
    fake.execScript(() => ({ exitCode: 0, stdout: "", stderr: "", delayMs: 2000 }));
    const lease = await hooks.onEnvironmentAcquireLease!({ ...base, config: {}, runId: "run-7" } as never);
    const r = await hooks.onEnvironmentExecute!({ ...base, config: {}, lease, command: "sleep", args: ["10"], timeoutMs: 200 } as never);
    expect(r.timedOut).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm test -- src/plugin.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

`src/plugin.ts`. Open `../e2b/src/plugin.ts` and copy its import block for the SDK types and `definePlugin`; the hooks below use the same parameter type names.

```ts
import {
  definePlugin,
  type PluginEnvironmentAcquireLeaseParams,
  type PluginEnvironmentDestroyLeaseParams,
  type PluginEnvironmentExecuteParams,
  type PluginEnvironmentExecuteResult,
  type PluginEnvironmentLease,
  type PluginEnvironmentProbeParams,
  type PluginEnvironmentProbeResult,
  type PluginEnvironmentRealizeWorkspaceParams,
  type PluginEnvironmentRealizeWorkspaceResult,
  type PluginEnvironmentReleaseLeaseParams,
  type PluginEnvironmentResumeLeaseParams,
  type PluginEnvironmentValidateConfigParams,
  type PluginEnvironmentValidationResult,
} from "@paperclipai/plugin-sdk";
import { parseConfig, validateConfig } from "./config.js";
import { containerCreateOptions, WORKSPACE_DIR } from "./container-spec.js";
import { DockerClient } from "./docker.js";
// One client for the worker's lifetime. NUFI_DOCKER_SOCKET exists for the
// tests, which point it at a fake daemon on a unix socket; on a box it is
// unset and the default socket is used.
let docker: DockerClient | null = null;
function client(): DockerClient {
  if (!docker) docker = new DockerClient({ socketPath: process.env.NUFI_DOCKER_SOCKET });
  return docker;
}

function leaseId(lease: PluginEnvironmentLease): string | null {
  return lease.providerLeaseId && lease.providerLeaseId.length > 0 ? lease.providerLeaseId : null;
}

const plugin = definePlugin({
  async setup(ctx) {
    docker = new DockerClient({ socketPath: process.env.NUFI_DOCKER_SOCKET });
    ctx.logger.info("Docker+gVisor sandbox provider ready");
  },

  async onHealth() {
    const h = await client().health();
    return h.ok
      ? { status: "ok", message: "Docker reachable, runsc runtime present" }
      : { status: "error", message: h.reason };
  },

  async onEnvironmentValidateConfig(
    params: PluginEnvironmentValidateConfigParams,
  ): Promise<PluginEnvironmentValidationResult> {
    return validateConfig(params.config ?? {});
  },

  async onEnvironmentProbe(_params: PluginEnvironmentProbeParams): Promise<PluginEnvironmentProbeResult> {
    const h = await client().health();
    return h.ok ? { ok: true, summary: "Docker reachable, runsc present" } : { ok: false, summary: h.reason };
  },

  async onEnvironmentAcquireLease(
    params: PluginEnvironmentAcquireLeaseParams,
  ): Promise<PluginEnvironmentLease> {
    // parseConfig ignores keys it does not know, and containerCreateOptions
    // never reads the raw config -- so `runtime: "runc"` or `privileged: true`
    // in a stored config changes nothing. The test for that is in
    // plugin.test.ts, not only container-spec.test.ts, because this is the
    // path a stored config actually takes.
    const config = parseConfig(params.config ?? {});
    const options = containerCreateOptions(config, {
      runId: params.runId,
      agentId: params.agentId,
      companyId: (params as { companyId?: string }).companyId,
    });
    const d = client();
    const id = await d.create(options);
    try {
      await d.start(id);
    } catch (err) {
      await d.remove(id).catch(() => undefined);
      throw err;
    }
    return {
      providerLeaseId: id,
      metadata: { provider: "docker", image: config.image, remoteCwd: WORKSPACE_DIR },
      expiresAt: new Date(Date.now() + config.timeoutMs).toISOString(),
    };
  },

  async onEnvironmentResumeLease(
    params: PluginEnvironmentResumeLeaseParams,
  ): Promise<PluginEnvironmentLease> {
    const id = leaseId(params.lease);
    if (!id) throw new Error("cannot resume a lease with no provider lease id");
    const d = client();
    const state = await d.inspect(id);
    if (!state.exists) {
      // Not quietly a new one: the host asked for *this* sandbox, with whatever
      // was in its workspace. A fresh container is a different answer, and the
      // host has an acquire hook for that.
      throw new Error(`sandbox ${id.slice(0, 12)} no longer exists on this box`);
    }
    if (!state.running) await d.start(id);
    return { providerLeaseId: id, metadata: { ...(params.lease.metadata ?? {}), resumed: true } };
  },

  async onEnvironmentReleaseLease(params: PluginEnvironmentReleaseLeaseParams): Promise<void> {
    const id = leaseId(params.lease);
    if (id) await client().stop(id);
  },

  async onEnvironmentDestroyLease(params: PluginEnvironmentDestroyLeaseParams): Promise<void> {
    const id = leaseId(params.lease);
    if (id) await client().remove(id);
  },

  async onEnvironmentRealizeWorkspace(
    params: PluginEnvironmentRealizeWorkspaceParams,
  ): Promise<PluginEnvironmentRealizeWorkspaceResult> {
    const cwd = params.workspace?.remotePath ?? params.workspace?.localPath ?? WORKSPACE_DIR;
    const id = leaseId(params.lease);
    if (id) {
      const r = await client().exec(id, ["mkdir", "-p", cwd], { timeoutMs: 30_000 });
      if (r.exitCode !== 0) throw new Error(`could not create ${cwd} in the sandbox: ${r.stderr}`);
    }
    return { cwd, metadata: { provider: "docker", remoteCwd: cwd } };
  },

  async onEnvironmentExecute(
    params: PluginEnvironmentExecuteParams,
  ): Promise<PluginEnvironmentExecuteResult> {
    const id = leaseId(params.lease);
    if (!id) {
      return { exitCode: 1, timedOut: false, stdout: "", stderr: "No provider lease ID available for execution." };
    }
    const r = await client().exec(id, [params.command, ...(params.args ?? [])], {
      cwd: params.cwd,
      env: params.env,
      stdin: params.stdin,
      timeoutMs: params.timeoutMs,
    });
    return { exitCode: r.exitCode, timedOut: r.timedOut, stdout: r.stdout, stderr: r.stderr };
  },
});

export default plugin;
```

If `definePlugin`'s hook signatures differ from the names above (check the e2b file — the SDK is the authority), match the SDK, not this plan.

- [ ] **Step 4: Run every test in the package, then typecheck**

Run: `pnpm test && pnpm typecheck`
Expected: all green. If `onHealth`'s return shape or `PluginEnvironmentProbeResult` fields differ from what the tests assume, adjust the **implementation** to the SDK and the **tests** to what the implementation returns; the SDK's types are the contract.

- [ ] **Step 5: Commit**

```bash
git add src/plugin.ts src/plugin.test.ts
git commit -m "feat(docker-provider): the ten hooks

Each hook is a few lines over the spec and the client. The tests drive
the real create/start/inspect/stop/remove/exec sequence against the fake
daemon and assert what was asked of Docker: runsc every time, the
internal network, the proxy in the environment -- including when the
stored config says runtime: runc, which changes nothing, because the spec
never reads the raw config. A resume of a sandbox that is gone fails
rather than quietly making a new one."
```

---

### Task 7: README and the full gate

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

`README.md`:

```markdown
# @nufi/plugin-docker-sandbox

The sandbox provider that lets NUFI Works run on a NuFi box without
Kubernetes. Each run gets a container under **gVisor** on an **internal
network** whose only way out is the box's egress proxy.

Design and the decisions behind it:
[`docs/superpowers/specs/2026-09-16-works-on-box-design.md`](../../../../../../docs/superpowers/specs/2026-09-16-works-on-box-design.md).

## What every sandbox gets, and cannot change

| | |
|---|---|
| runtime | `runsc` — the provider refuses to report healthy without it |
| network | `works-sandbox`, declared `internal: true` in the box compose |
| egress | `HTTP_PROXY` / `HTTPS_PROXY` → `works-egress:3128`; a client that ignores them has no route |
| limits | memory, CPUs, pids from the config; defaults 2 GB / 2 / 512 |
| filesystem | read-only root, a per-run `/workspace` volume, a `noexec` tmpfs `/tmp` |
| privilege | none: all capabilities dropped, `no-new-privileges`, no Docker socket |

The config schema exposes the image, the limits, the proxy address and a
lifetime. It does not expose the runtime, the network or privilege, and
`manifest.test.ts` pins that: a provider that can be told to use `runc` is
one config line away from having no kernel boundary. A stored config that
says `runtime: runc` changes nothing — `container-spec.ts` never reads the
raw config — and `plugin.test.ts` proves it on the real acquire path.

## The socket

The **provider** talks to the Engine over `/var/run/docker.sock`, mounted
into the `works` container. A process that can reach the daemon can start
any container on the box, as root. It is the same grant `nufi-cron`
deliberately avoids. It is accepted here because sibling containers cannot
be created any other way, and it is confined to the `works` service — no
sandbox has the mount.

## The deadline

The Engine API has no handle on a running exec. When a command outstays
`timeoutMs`, the provider **stops the container** rather than merely
stopping to listen: a client that walks away from a process still running
is the failure this whole design exists to avoid. `docker.test.ts` asserts
the stop call arrives.

## Tests

```sh
pnpm install
pnpm test
```

No Docker. `fake-docker.ts` is an Engine API over a unix socket that records
every call with its body, so the tests assert what was asked of Docker —
the runtime, the network, the mounts — rather than that a mock was called.
The one live proof is the box's own: `.github/workflows/gvisor-probe.yml`,
which showed `uname -r` inside `--runtime=runsc` reporting `4.19.0-gvisor`
on Ubuntu x86-64.

This package sits outside the pnpm workspace, like every provider upstream
ships, and installs on its own. `agents-ci.yml` runs its tests; no
provider's tests ran there before this one.
```

- [ ] **Step 2: Run what CI will run, from the repo root**

```bash
cd apps/agents/packages/plugins/sandbox-providers/docker && pnpm install && pnpm typecheck && pnpm test
cd "$(git rev-parse --show-toplevel)" && ./apps/agents/nufi/check-fork-diff.sh
```

Expected: green, and `OK — the fork diff is confined to the NuFi allowlist.`

- [ ] **Step 3: Commit and open the PR**

```bash
git add apps/agents/packages/plugins/sandbox-providers/docker/README.md
git commit -m "docs(docker-provider): what every sandbox gets, the socket, the deadline"
git push -u origin feat/works-on-box-a-docker-provider
```

Title: `feat(agents): the Docker+gVisor sandbox provider — piece A of Works on the box`

Body must cover: what every sandbox gets and cannot change (the table); that the config cannot reach the runtime and both a manifest test and an acquire-path test pin it; the socket grant, stated; the deadline stopping the container, with the test that asserts it; the fake daemon and why calls are asserted rather than mocked; the allowlist entry and the new CI job, and that no provider's tests ran in CI before; that piece B (the egress proxy) and piece C (the box registering the environment, per the revised design in #117) follow. Link the spec. End with the session's attribution lines.

---

## Self-review

**Spec coverage.** Section A: ten hooks — Task 6, each named. "What every sandbox gets, and cannot change" — Task 3 enforces all seven items and tests each; Task 6 re-tests the runtime and network on the acquire path with a hostile stored config. "`onHealth` refuses to report healthy without it" — Task 5 (`health()`) and Task 6 (the second health test). "The socket… stated in the box README" — this plan's README states it; the box README is piece C's. "`dockerode`, a new dependency of this package only" — Task 1. "Tests use a fake daemon over an HTTP server… calls asserted, not mocked" — Task 4. Section "Testing", A: "`runsc` is always requested and `runc` never is; every sandbox lands on the internal network with the proxy in its environment; a timed-out exec is killed rather than abandoned; `onHealth` is red without `runsc`" — Tasks 3, 5, 6. Covered.

**Placeholders.** None. The two conditionals ("if the SDK's hook names differ, match the SDK"; "if run ids are not plain, name the volume from `containerName`") each name the exact check and the exact fix.

**Type consistency.** `SANDBOX_RUNTIME = "runsc"` and `SANDBOX_NETWORK = "works-sandbox"` are defined in Task 3 and imported by name in Tasks 5 and 6. `DockerClient.exec` returns `ExecResult { exitCode, stdout, stderr, timedOut }` (Task 5) and Task 6 maps it field-for-field onto `PluginEnvironmentExecuteResult`. `FakeDocker.start({ runtimes })`, `.execScript(handler)`, `.calls`, `.containers`, `.socketPath`, `.stop()` (Task 4) are the only members Tasks 5 and 6 use. `parseConfig` / `validateConfig` / `DEFAULTS` (Task 2) are used with the signatures defined there. The container name prefix `works-sandbox-` (Task 3) matches the volume name prefix in the same function.
