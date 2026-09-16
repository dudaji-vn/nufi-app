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

  it("kills (SIGKILL) a command that outstays timeoutMs and says so — it does not just stop listening (stream already attached, so this exercises the destroy() branch)", async () => {
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
    // container the exec was running in is killed, which is the only handle
    // the Engine API gives us on a running exec. It is a kill (SIGKILL), not
    // a graceful stop: PID 1 ("sleep infinity") has nothing to shut down for
    // -- a stop() here would just be five more seconds waiting on a SIGTERM
    // nobody honours before the daemon SIGKILLs anyway.
    expect(fake.calls.some((c) => /\/containers\/[^/]+\/kill$/.test(c.path))).toBe(true);
  });

  it("aborts the still-pending start call when the daemon never even answers before the deadline (the abort-before-start branch)", async () => {
    fake = await FakeDocker.start();
    fake.execScript(() => ({ exitCode: 0, stdout: "", stderr: "", neverStart: true }));
    const d = new DockerClient({ socketPath: fake.socketPath });
    const id = await d.create({ Image: "x:1", name: "e4" }); await d.start(id);
    const t0 = Date.now();
    const r = await d.exec(id, ["sleep", "10"], { timeoutMs: 200 });
    expect(Date.now() - t0).toBeLessThan(1500);
    expect(r.timedOut).toBe(true);
    expect(r.exitCode).toBeNull();
    expect(fake.calls.some((c) => /\/containers\/[^/]+\/kill$/.test(c.path))).toBe(true);
  });

  it("rejects, rather than hanging or crashing the process, when the exec stream errors mid-flight with no timeoutMs set", async () => {
    fake = await FakeDocker.start();
    fake.execScript(() => ({ exitCode: 0, stdout: "", stderr: "", error: true }));
    const d = new DockerClient({ socketPath: fake.socketPath });
    const id = await d.create({ Image: "x:1", name: "e5" }); await d.start(id);
    // No timeoutMs: the only thing that can end this is the stream itself
    // erroring out. If exec() does not attach an error handler, this hangs
    // forever (the pre-fix failure mode); if the daemon hands back a raw
    // socket whose EPIPE nobody is listening for, this throws past the
    // promise chain and kills the process instead of rejecting it.
    await expect(d.exec(id, ["sleep", "10"], {})).rejects.toThrow();
  });
});
