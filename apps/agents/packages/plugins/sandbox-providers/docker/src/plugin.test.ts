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
    // onEnvironmentReleaseLease/onEnvironmentResumeLease take providerLeaseId
    // directly on params (PluginEnvironmentReleaseLeaseParams /
    // PluginEnvironmentResumeLeaseParams in @paperclipai/plugin-sdk), not a
    // nested `lease` -- unlike onEnvironmentRealizeWorkspace/onEnvironmentExecute,
    // which do carry the full PluginEnvironmentLease. See ../e2b/src/plugin.test.ts
    // for the same shape.
    await hooks.onEnvironmentReleaseLease!({ ...base, config: {}, providerLeaseId: lease.providerLeaseId } as never);
    expect(fake.containers.get(lease.providerLeaseId!)?.running).toBe(false);
    const resumed = await hooks.onEnvironmentResumeLease!({ ...base, config: {}, providerLeaseId: lease.providerLeaseId } as never);
    expect(resumed.providerLeaseId).toBe(lease.providerLeaseId);
    expect(fake.containers.get(lease.providerLeaseId!)?.running).toBe(true);
  });

  it("resume of a container that is gone fails rather than silently making a new one", async () => {
    await expect(
      hooks.onEnvironmentResumeLease!({ ...base, config: {}, providerLeaseId: "deadbeef".repeat(8) } as never),
    ).rejects.toThrow(/no longer exists|not found|gone/i);
  });

  it("destroy removes the container", async () => {
    const lease = await hooks.onEnvironmentAcquireLease!({ ...base, config: {}, runId: "run-4" } as never);
    await hooks.onEnvironmentDestroyLease!({ ...base, config: {}, providerLeaseId: lease.providerLeaseId } as never);
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

  it("execute removes the sandbox and reports its state as unknown when the daemon connection is lost mid-exec", async () => {
    fake.execScript(() => ({ exitCode: 0, stdout: "", stderr: "", error: true }));
    const lease = await hooks.onEnvironmentAcquireLease!({ ...base, config: {}, runId: "run-8" } as never);
    const r = await hooks.onEnvironmentExecute!({ ...base, config: {}, lease, command: "true" } as never);
    expect(r.exitCode).toBeNull();
    expect(fake.calls.some((c) => c.method === "DELETE" && c.path === `/containers/${lease.providerLeaseId}`)).toBe(true);
  });
});
