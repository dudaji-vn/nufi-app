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
