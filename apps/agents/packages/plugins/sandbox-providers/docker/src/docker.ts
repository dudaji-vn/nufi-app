/**
 * The thin edge between the plugin and the Engine API. Everything Docker-
 * specific -- multiplexed streams, 404 shapes, how a deadline is enforced --
 * is here, so plugin.ts reads as the ten hooks and nothing else.
 */
import Dockerode from "dockerode";
import { PassThrough, type Duplex } from "node:stream";
import { setTimeout as sleep } from "node:timers/promises";
import { SANDBOX_RUNTIME } from "./container-spec.js";

export interface ExecResult {
  exitCode: number | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
}

/**
 * How long past its deadline a command's stream may still end on its own
 * before the container is killed out from under it. The in-sandbox
 * timeout(1) rounds the deadline up to whole seconds, so an ordinary
 * timed-out exec ends up to a second late; five seconds is well clear of
 * that and still short enough that a command which escaped timeout(1) --
 * or an exec-create the daemon never answered -- is not left running.
 */
export const DEFAULT_KILL_GRACE_MS = 5_000;

/**
 * exec() failed after the exec was created: a command may be running in
 * there and this client no longer knows. A rejection that is *not* this
 * (assertOurs refused, exec-create itself failed) leaves the container
 * exactly as it was, and the caller may treat it as an ordinary error.
 */
export class SandboxStateUnknownError extends Error {
  constructor(cause: unknown) {
    super(cause instanceof Error ? cause.message : String(cause), { cause });
    this.name = "SandboxStateUnknownError";
  }
}

const OURS_LABEL = "me.nufi.works.run";

/** Resolves true if `p` settles (either way) within `ms`, false otherwise. */
function settledWithin(p: Promise<unknown>, ms: number): Promise<boolean> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(false), ms);
    p.then(() => true, () => true).then((v) => { clearTimeout(timer); resolve(v); });
  });
}

export class DockerClient {
  private readonly docker: Dockerode;
  private readonly killGraceMs: number;
  // Container ids this client has already confirmed carry our label. The
  // run-log tail execs about four times a second, and an inspect per exec
  // would double the daemon's load for an answer that cannot change: a
  // label is set at create and never edited, and an id is never reused.
  private readonly ours = new Set<string>();

  constructor(opts: { socketPath?: string; killGraceMs?: number } = {}) {
    this.docker = new Dockerode({ socketPath: opts.socketPath ?? "/var/run/docker.sock" });
    this.killGraceMs = opts.killGraceMs ?? DEFAULT_KILL_GRACE_MS;
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

  /**
   * `force: true, v: true` only takes anonymous volumes with the container --
   * ours is named (`containerName(lease)`, from container-spec.ts), so a
   * plain remove leaks it. Read the volume's name off the container's own
   * HostConfig before the container (and that HostConfig) is gone, then
   * delete it by name afterwards. `volumeName` is the lease's own record of
   * that name, for when the container is already gone and there is no
   * HostConfig left to read it from.
   */
  async remove(id: string, volumeName?: string): Promise<void> {
    const volumeNames = new Set<string>(volumeName ? [volumeName] : []);
    try {
      const info = await this.docker.getContainer(id).inspect();
      for (const m of info.HostConfig.Mounts ?? []) {
        if (m.Type === "volume") volumeNames.add(m.Source);
      }
    } catch (err) {
      if ((err as { statusCode?: number }).statusCode !== 404) throw err;
      // Already gone -- nothing to inspect; only the hinted volume is left to remove.
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
   * Docker has no per-caller scope: with the socket, exec()/remove()/kill()
   * reach every container on the box, not only ones this provider created.
   * Every path that touches a container calls this first so a mislabeled or
   * foreign container -- another plugin's, a co-located service's -- cannot
   * be run in or torn down through us. A 404 means there is nothing there
   * to protect; the caller's own 404 handling (already gone) proceeds from
   * there, and nothing is remembered about the id.
   */
  async assertOurs(id: string): Promise<void> {
    if (this.ours.has(id)) return;
    let info: { Config?: { Labels?: Record<string, string> } };
    try {
      info = await this.docker.getContainer(id).inspect();
    } catch (err) {
      if ((err as { statusCode?: number }).statusCode === 404) return;
      throw err;
    }
    if (!info.Config?.Labels?.[OURS_LABEL]) {
      throw new Error(`refusing to touch container ${id.slice(0, 12)}: not a Works sandbox (no ${OURS_LABEL} label)`);
    }
    this.ours.add(id);
  }

  /**
   * Runs `cmd` in the container and waits for it.
   *
   * With a `timeoutMs`, the command is wrapped in the sandbox's own
   * `timeout -s KILL` so the deadline is enforced where the process is --
   * the Engine API has no "kill this exec", and killing the container
   * instead would destroy the agent's sandbox on any single slow command
   * (the host's run-log tail execs every 250ms with a 15s deadline and
   * tolerates a few timeouts; it does not tolerate its sandbox vanishing).
   * Our own timer stays the arbiter of `timedOut: true`. If it fires and
   * the stream has still not ended within `killGraceMs`, the command has
   * outlived the one thing that was supposed to stop it, and the container
   * is killed rather than the command abandoned.
   *
   * Rejects with SandboxStateUnknownError for a failure after the exec was
   * created (a dropped daemon connection mid-command); any other rejection
   * happened before anything ran.
   */
  async exec(
    id: string,
    cmd: string[],
    opts: { cwd?: string; env?: Record<string, string>; stdin?: string; timeoutMs?: number },
  ): Promise<ExecResult> {
    await this.assertOurs(id);
    const container = this.docker.getContainer(id);

    // The timer starts before the first request so a hung exec-create is
    // bounded too; the abort signal reaches both requests.
    let timer: NodeJS.Timeout | undefined;
    const deadline = opts.timeoutMs
      ? new Promise<"timeout">((resolve) => {
          timer = setTimeout(() => resolve("timeout"), opts.timeoutMs);
        })
      : new Promise<never>(() => {});
    const abortController = new AbortController();

    const outChunks: Buffer[] = [];
    const errChunks: Buffer[] = [];
    let stream: Duplex | undefined;

    const run = (async (): Promise<Dockerode.Exec> => {
      const exec = await container.exec({
        Cmd: opts.timeoutMs ? withDeadline(cmd, opts.timeoutMs) : cmd,
        WorkingDir: opts.cwd,
        Env: opts.env ? Object.entries(opts.env).map(([k, v]) => `${k}=${v}`) : undefined,
        AttachStdout: true,
        AttachStderr: true,
        AttachStdin: opts.stdin !== undefined,
        abortSignal: abortController.signal,
      });
      try {
        // A server that has not sent a byte yet (headers held back until
        // the first write, which is exactly what a still-running command
        // looks like) leaves exec.start() itself unresolved; the deadline
        // above covers that too.
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
      } catch (err) {
        throw new SandboxStateUnknownError(err);
      }
      return exec;
    })();

    let winner: "done" | "timeout";
    try {
      winner = await Promise.race([run.then((): "done" => "done"), deadline]);
    } finally {
      if (timer) clearTimeout(timer);
    }

    if (winner === "timeout") {
      // The ordinary case: timeout(1) inside the sandbox kills the command
      // within the second, the stream ends, and the container is untouched.
      const ended = await settledWithin(run, this.killGraceMs);
      if (!ended) {
        // The fallback. Tear down our own end -- destroy the attached stream
        // if we got one, otherwise abort the still-pending request -- so this
        // client does not just stop listening, then SIGKILL the container:
        // PID 1 is "sleep infinity", there is nothing to shut down
        // gracefully, and a stop() would only be five more seconds of the
        // daemon waiting on a SIGTERM nobody honours.
        if (stream) stream.destroy();
        else abortController.abort();
        run.catch(() => {});
        await this.kill(id);
      }
      return { exitCode: null, stdout: Buffer.concat(outChunks).toString("utf8"), stderr: Buffer.concat(errChunks).toString("utf8"), timedOut: true };
    }

    // The stream can end a moment before the daemon records the exit code;
    // read it only once the exec reports it is no longer running.
    const exec = await run;
    let info = await exec.inspect();
    for (let polls = 0; info.Running && polls < 20; polls += 1) {
      await sleep(50);
      info = await exec.inspect();
    }
    return {
      exitCode: info.ExitCode ?? null,
      stdout: Buffer.concat(outChunks).toString("utf8"),
      stderr: Buffer.concat(errChunks).toString("utf8"),
      timedOut: false,
    };
  }
}

/**
 * The command under the sandbox's own timeout(1), which sends SIGKILL when
 * the seconds run out. Whole seconds, rounded up: a deadline is never
 * shortened by rounding.
 *
 * The image must ship GNU coreutils' timeout, not busybox's. GNU signals the
 * whole process group; busybox signals only the direct child. The host runs
 * `bash -lc <script>`, so under busybox a timed-out script whose current step
 * is a forked child would leave that child holding stdout, the stream would
 * not end, and the 5 s container-kill fallback would fire -- the regression
 * this wrapper exists to prevent. A hard requirement on nufi-sandbox:main.
 */
function withDeadline(cmd: string[], timeoutMs: number): string[] {
  return ["timeout", "-s", "KILL", String(Math.ceil(timeoutMs / 1000)), ...cmd];
}
