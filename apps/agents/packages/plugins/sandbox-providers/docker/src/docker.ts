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

    const outChunks: Buffer[] = [];
    const errChunks: Buffer[] = [];
    // The deadline has to cover the whole exchange, not just "wait for the
    // stream to end": a server that has not sent a byte yet (headers held
    // back until the first write, which is exactly what a still-running
    // command looks like) leaves exec.start() itself unresolved. Racing only
    // the post-start wait would let that hang outlast timeoutMs.
    const abortController = new AbortController();
    let stream: NodeJS.ReadWriteStream | undefined;

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
      await new Promise<void>((resolve) => s.on("end", () => resolve()));
    })();

    let timer: NodeJS.Timeout | undefined;
    const deadline = opts.timeoutMs
      ? new Promise<"timeout">((resolve) => {
          timer = setTimeout(() => resolve("timeout"), opts.timeoutMs);
        })
      : new Promise<never>(() => {});

    const winner = await Promise.race([run.then((): "done" => "done"), deadline]);
    if (timer) clearTimeout(timer);

    if (winner === "timeout") {
      // The Engine API has no "kill this exec". Stopping the container is the
      // one handle it gives, and it is the right one: a lease whose command
      // has outstayed its deadline is a lease the caller is about to give up
      // on. Stopping here is what makes the deadline real rather than a
      // client that walked away from a process still running. We also tear
      // down our own end -- destroy the attached stream if we got one,
      // otherwise abort the still-pending start request -- so this client
      // does not just stop listening while the command runs on underneath it.
      if (stream) stream.destroy();
      else abortController.abort();
      run.catch(() => {});
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
