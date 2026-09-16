/**
 * The thin edge between the plugin and the Engine API. Everything Docker-
 * specific -- multiplexed streams, 404 shapes, how a deadline is enforced --
 * is here, so plugin.ts reads as the ten hooks and nothing else.
 */
import Dockerode from "dockerode";
import { PassThrough, type Duplex } from "node:stream";
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

  /**
   * `force: true, v: true` only takes anonymous volumes with the container --
   * ours is named (`containerName(lease)`, from container-spec.ts), so a
   * plain remove leaks it. Read the volume's name off the container's own
   * HostConfig before the container (and that HostConfig) is gone, then
   * delete it by name afterwards.
   */
  async remove(id: string): Promise<void> {
    let volumeNames: string[] = [];
    try {
      const info = await this.docker.getContainer(id).inspect();
      volumeNames = (info.HostConfig.Mounts ?? [])
        .filter((m) => m.Type === "volume")
        .map((m) => m.Source);
    } catch (err) {
      if ((err as { statusCode?: number }).statusCode !== 404) throw err;
      // Already gone -- nothing to inspect, nothing new to remove below.
    }

    try {
      await this.docker.getContainer(id).remove({ force: true, v: true });
    } catch (err) {
      if ((err as { statusCode?: number }).statusCode !== 404) throw err;
    }

    for (const name of volumeNames) {
      try {
        await this.docker.getVolume(name).remove();
      } catch (err) {
        if ((err as { statusCode?: number }).statusCode !== 404) throw err;
      }
    }
  }

  async kill(id: string): Promise<void> {
    try {
      await this.docker.getContainer(id).kill();
    } catch (err) {
      const code = (err as { statusCode?: number }).statusCode;
      if (code === 404 || code === 409) return; // gone, or already not running
      throw err;
    }
  }

  /**
   * Docker has no per-caller scope: with the socket, remove()/stop() reach
   * every container on the box, not only ones this provider created. Every
   * destructive path calls this first so a mislabeled or foreign container
   * -- another plugin's, a co-located service's -- cannot be torn down
   * through us. A 404 means there is nothing there to protect; the caller's
   * own 404 handling (already gone) proceeds from there.
   */
  async assertOurs(id: string): Promise<void> {
    let info: { Config?: { Labels?: Record<string, string> } };
    try {
      info = await this.docker.getContainer(id).inspect();
    } catch (err) {
      if ((err as { statusCode?: number }).statusCode === 404) return;
      throw err;
    }
    if (!info.Config?.Labels?.["me.nufi.works.run"]) {
      throw new Error(`refusing to touch container ${id.slice(0, 12)}: not a Works sandbox (no me.nufi.works.run label)`);
    }
  }

  /**
   * A rejection from exec() means the container's state is unknown -- the
   * deadline path SIGKILLs and the stream path can fail mid-teardown, so the
   * caller must force-remove rather than treat a rejection as a clean,
   * side-effect-free failure.
   */
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

    const outChunks: Buffer[] = [];
    const errChunks: Buffer[] = [];
    // The deadline has to cover the whole exchange, not just "wait for the
    // stream to end": a server that has not sent a byte yet (headers held
    // back until the first write, which is exactly what a still-running
    // command looks like) leaves exec.start() itself unresolved. Racing only
    // the post-start wait would let that hang outlast timeoutMs.
    const abortController = new AbortController();
    let stream: Duplex | undefined;

    const run = (async () => {
      const s = await exec.start({
        hijack: opts.stdin !== undefined,
        stdin: opts.stdin !== undefined,
        abortSignal: abortController.signal,
      });
      stream = s;
      const stdout = new PassThrough();
      const stderr = new PassThrough();
      stdout.on("data", (d: Buffer) => outChunks.push(d));
      stderr.on("data", (d: Buffer) => errChunks.push(d));
      this.docker.modem.demuxStream(s, stdout, stderr);
      if (opts.stdin !== undefined) {
        s.write(opts.stdin);
        s.end();
      }
      // dockerode hands back a bare stream with no listeners of its own. An
      // 'error' event nobody is listening for is Node's cue to throw --
      // straight through to uncaughtException and down the whole worker
      // process -- so we always attach one. A clean 'end' resolves as
      // before; 'close' is also a resolution signal (it is what a hijacked
      // stdin session's own destroy() -- ours, below, on the timeout path --
      // produces instead of 'end'), but a 'close' that arrives *without* a
      // preceding 'end' means the daemon's connection dropped mid-exec, and
      // that is treated as the same failure as an explicit 'error' --
      // silently returning as if the command had finished would be worse
      // than rejecting.
      let sawEnd = false;
      await new Promise<void>((resolve, reject) => {
        s.once("error", reject);
        s.once("end", () => { sawEnd = true; resolve(); });
        s.once("close", () => {
          if (sawEnd) resolve();
          else reject(new Error("the exec stream closed before it ended -- the connection to the Docker daemon was lost"));
        });
      });
    })();

    let timer: NodeJS.Timeout | undefined;
    const deadline = opts.timeoutMs
      ? new Promise<"timeout">((resolve) => {
          timer = setTimeout(() => resolve("timeout"), opts.timeoutMs);
        })
      : new Promise<never>(() => {});

    let winner: "done" | "timeout";
    try {
      winner = await Promise.race([run.then((): "done" => "done"), deadline]);
    } finally {
      if (timer) clearTimeout(timer);
    }

    if (winner === "timeout") {
      // The Engine API has no "kill this exec". The container is the only
      // handle it gives us on a running exec, and a command that has
      // outstayed its deadline gets no grace period: PID 1 is "sleep
      // infinity" (an init reaps it, but there is nothing to shut down
      // gracefully here), so this is a kill (SIGKILL), not a stop -- a
      // stop() on a command that is deliberately ignoring its deadline would
      // just be five more seconds of the daemon waiting on a SIGTERM nobody
      // is going to honour before it SIGKILLs anyway. We also tear down our
      // own end -- destroy the attached stream if we got one, otherwise
      // abort the still-pending start request -- so this client does not
      // just stop listening while the command runs on underneath it.
      if (stream) stream.destroy();
      else abortController.abort();
      run.catch(() => {});
      await this.kill(id);
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
