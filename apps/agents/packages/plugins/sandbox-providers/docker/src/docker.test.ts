import { afterEach, describe, expect, it } from "vitest";
import { DEFAULT_KILL_GRACE_MS, DockerClient, SandboxStateUnknownError } from "./docker.js";
import { FakeDocker } from "./fake-docker.js";

let fake: FakeDocker;
afterEach(async () => { await fake?.stop(); });

async function started(d: DockerClient, name: string): Promise<string> {
  const id = await d.create({ Image: "x:1", name });
  await d.start(id);
  return id;
}

const execCreates = () => fake.calls.filter((c) => c.method === "POST" && /\/containers\/[^/]+\/exec$/.test(c.path));
const killed = () => fake.calls.some((c) => /\/containers\/[^/]+\/kill$/.test(c.path));

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
    const id = await started(d, "e1");
    const r = await d.exec(id, ["echo", "hi"], {});
    expect(r).toEqual({ exitCode: 3, stdout: "out:hi", stderr: "warn", timedOut: false });
  });

  it("passes cwd and env through, and stdin when given", async () => {
    fake = await FakeDocker.start();
    const d = new DockerClient({ socketPath: fake.socketPath });
    const id = await started(d, "e2");
    await d.exec(id, ["pwd"], { cwd: "/workspace/sub", env: { FOO: "bar" }, stdin: "data" });
    const execCreate = execCreates()[0].body as Record<string, unknown>;
    expect(execCreate.WorkingDir).toBe("/workspace/sub");
    expect(execCreate.Env).toEqual(["FOO=bar"]);
    expect(execCreate.AttachStdin).toBe(true);
  });

  it("waits for the exec to report not-running before reading its exit code", async () => {
    fake = await FakeDocker.start();
    fake.execScript(() => ({ exitCode: 7, stdout: "", stderr: "", exitAfterEndMs: 120 }));
    const d = new DockerClient({ socketPath: fake.socketPath });
    const id = await started(d, "e-poll");
    const r = await d.exec(id, ["true"], {});
    expect(r.exitCode).toBe(7);
    expect(fake.calls.filter((c) => /\/exec\/[^/]+\/json$/.test(c.path)).length).toBeGreaterThan(1);
  });

  describe("the deadline", () => {
    it("is enforced by wrapping the command in timeout(1) inside the sandbox", async () => {
      fake = await FakeDocker.start();
      const d = new DockerClient({ socketPath: fake.socketPath });
      const id = await started(d, "e-wrap");
      await d.exec(id, ["sleep", "10"], { timeoutMs: 2500 });
      expect((execCreates()[0].body as { Cmd: string[] }).Cmd).toEqual(["timeout", "-s", "KILL", "3", "sleep", "10"]);
    });

    it("does not wrap a command that has no deadline", async () => {
      fake = await FakeDocker.start();
      const d = new DockerClient({ socketPath: fake.socketPath });
      const id = await started(d, "e-nowrap");
      await d.exec(id, ["sleep", "10"], {});
      expect((execCreates()[0].body as { Cmd: string[] }).Cmd).toEqual(["sleep", "10"]);
    });

    it("reports timedOut when the command outstays timeoutMs, and leaves the container alone when the stream then ends on its own", async () => {
      fake = await FakeDocker.start();
      // The in-sandbox timeout(1) rounds up to whole seconds, so the stream
      // ends a little after our deadline, not on it: that is the ordinary
      // shape of a timed-out exec and it must not cost the sandbox.
      fake.execScript(() => ({ exitCode: 137, stdout: "late", stderr: "", delayMs: 600 }));
      const d = new DockerClient({ socketPath: fake.socketPath });
      const id = await started(d, "e3");
      const t0 = Date.now();
      const r = await d.exec(id, ["sleep", "10"], { timeoutMs: 200 });
      const elapsed = Date.now() - t0;
      expect(r.timedOut).toBe(true);
      expect(r.exitCode).toBeNull();
      expect(r.stdout).toBe("late");
      // Returned when the stream ended (~600ms), not when the grace ran out.
      expect(elapsed).toBeGreaterThanOrEqual(550);
      expect(elapsed).toBeLessThan(DEFAULT_KILL_GRACE_MS);
      expect(killed()).toBe(false);
    });

    it("kills the container only as a fallback: a stream that never ends within the grace after the deadline", async () => {
      fake = await FakeDocker.start();
      fake.execScript(() => ({ exitCode: 0, stdout: "", stderr: "", neverEnd: true }));
      const d = new DockerClient({ socketPath: fake.socketPath, killGraceMs: 300 });
      const id = await started(d, "e-grace");
      const t0 = Date.now();
      const r = await d.exec(id, ["sleep", "10"], { timeoutMs: 200 });
      const elapsed = Date.now() - t0;
      expect(r.timedOut).toBe(true);
      expect(r.exitCode).toBeNull();
      expect(elapsed).toBeGreaterThanOrEqual(500); // deadline + grace, not before
      expect(elapsed).toBeLessThan(1500);
      expect(killed()).toBe(true);
      expect(fake.containers.get(id)?.running).toBe(false);
    });

    it("aborts a start call the daemon never answers, then falls back to the kill (the abort-before-start branch)", async () => {
      fake = await FakeDocker.start();
      fake.execScript(() => ({ exitCode: 0, stdout: "", stderr: "", neverStart: true }));
      const d = new DockerClient({ socketPath: fake.socketPath, killGraceMs: 300 });
      const id = await started(d, "e4");
      const t0 = Date.now();
      const r = await d.exec(id, ["sleep", "10"], { timeoutMs: 200 });
      expect(Date.now() - t0).toBeGreaterThanOrEqual(500);
      expect(Date.now() - t0).toBeLessThan(1500);
      expect(r.timedOut).toBe(true);
      expect(r.exitCode).toBeNull();
      expect(killed()).toBe(true);
    });

    it("gives the command five seconds past the deadline by default", () => {
      expect(DEFAULT_KILL_GRACE_MS).toBe(5_000);
    });
  });

  it("rejects, rather than hanging or crashing the process, when the exec stream errors mid-flight with no timeoutMs set -- and says the state is unknown", async () => {
    fake = await FakeDocker.start();
    fake.execScript(() => ({ exitCode: 0, stdout: "", stderr: "", error: true }));
    const d = new DockerClient({ socketPath: fake.socketPath });
    const id = await started(d, "e5");
    // No timeoutMs: the only thing that can end this is the stream itself
    // erroring out. If exec() does not attach an error handler, this hangs
    // forever (the pre-fix failure mode); if the daemon hands back a raw
    // socket whose EPIPE nobody is listening for, this throws past the
    // promise chain and kills the process instead of rejecting it.
    await expect(d.exec(id, ["sleep", "10"], {})).rejects.toThrow(SandboxStateUnknownError);
  });

  it("a failure before the exec exists is an ordinary error -- the container is as it was", async () => {
    fake = await FakeDocker.start();
    const d = new DockerClient({ socketPath: fake.socketPath });
    const id = await started(d, "e6");
    fake.containers.get(id)!.running = false; // exec-create on a stopped container: 409 from the daemon
    await expect(d.exec(id, ["true"], {})).rejects.toThrow();
    await expect(d.exec(id, ["true"], {})).rejects.not.toThrow(SandboxStateUnknownError);
  });
});
