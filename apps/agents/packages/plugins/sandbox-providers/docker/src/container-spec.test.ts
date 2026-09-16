import { describe, expect, it } from "vitest";
import { DEFAULTS, parseConfig } from "./config.js";
import {
  SANDBOX_NETWORK,
  SANDBOX_RUNTIME,
  WORKSPACE_DIR,
  containerCreateOptions,
  containerName,
  memoryBytes,
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
      { Type: "volume", Source: containerName(lease), Target: WORKSPACE_DIR },
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

  it("runs an init (tini) as PID 1 so a graceful stop on release is prompt, not a 5s wait for SIGKILL", () => {
    expect(host.Init).toBe(true);
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

describe("memoryBytes", () => {
  it("converts each Docker size unit to bytes", () => {
    expect(memoryBytes("512m")).toBe(512 * 1024 ** 2);
    expect(memoryBytes("2g")).toBe(2 * 1024 ** 3);
    expect(memoryBytes("1.5g")).toBe(1.5 * 1024 ** 3);
    expect(memoryBytes("1024k")).toBe(1024 * 1024);
    expect(memoryBytes("100")).toBe(100); // bare number = bytes
    expect(memoryBytes("1B")).toBe(1);
  });
});
