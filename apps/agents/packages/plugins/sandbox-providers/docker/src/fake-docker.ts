import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { randomBytes } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import type { Duplex } from "node:stream";

type ExecHandler = (cmd: string[]) => {
  exitCode: number;
  stdout: string;
  stderr: string;
  delayMs?: number;
  /** Write the response headers, then kill the connection before ever finishing -- a mid-exec drop, not a clean end. */
  error?: boolean;
  /** Never respond at all -- not even headers -- so the client's start() call hangs until it gives up on its own. */
  neverStart?: boolean;
  /** Respond with headers (or the 101), then never write a frame and never end -- a command that ignores every deadline. */
  neverEnd?: boolean;
  /** Keep reporting Running: true from /exec/{id}/json for this long after the stream has ended, as the daemon can. */
  exitAfterEndMs?: number;
};

interface FakeContainer { id: string; name: string; create: unknown; running: boolean }
interface FakeExec { id: string; containerId: string; cmd: string[]; exitCode: number | null; running: boolean; stdin?: Buffer }

export class FakeDocker {
  readonly calls: Array<{ method: string; path: string; body?: unknown }> = [];
  readonly containers = new Map<string, FakeContainer>();
  private readonly execs = new Map<string, FakeExec>();
  private readonly hijacked = new Set<Duplex>();
  private execHandler: ExecHandler = () => ({ exitCode: 0, stdout: "", stderr: "" });
  private server!: Server;
  readonly socketPath: string;

  private constructor(private readonly runtimes: string[]) {
    this.socketPath = join(mkdtempSync(join(tmpdir(), "fake-docker-")), "docker.sock");
  }

  static async start(opts: { runtimes?: string[] } = {}): Promise<FakeDocker> {
    const fake = new FakeDocker(opts.runtimes ?? ["runc", "runsc"]);
    fake.server = createServer((req, res) => void fake.handle(req, res));
    // A request carrying `Upgrade` never reaches the request handler above;
    // Node hands it here with the raw socket instead.
    fake.server.on("upgrade", (req, socket, head) => fake.handleUpgrade(req, socket, head));
    await new Promise<void>((resolve) => fake.server.listen(fake.socketPath, resolve));
    return fake;
  }

  execScript(handler: ExecHandler): void { this.execHandler = handler; }

  /** What the client wrote on a hijacked exec's stdin, as delivered, once it half-closed. */
  stdinFor(execId: string): string | undefined {
    return this.execs.get(execId)?.stdin?.toString("utf8");
  }

  async stop(): Promise<void> {
    for (const s of this.hijacked) s.destroy();
    this.server.closeAllConnections();
    await new Promise<void>((resolve) => this.server.close(() => resolve()));
    rmSync(dirname(this.socketPath), { recursive: true, force: true });
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
    if ((m = /^\/containers\/([^/]+)\/kill$/.exec(path)) && req.method === "POST") {
      const c = this.find(m[1]); if (!c) return json(404, { message: "no such container" });
      c.running = false; res.writeHead(204); return void res.end();
    }
    if ((m = /^\/containers\/([^/]+)\/json$/.exec(path))) {
      const c = this.find(m[1]); if (!c) return json(404, { message: "no such container" });
      const createBody = (c.create as { Labels?: Record<string, string>; HostConfig?: unknown }) ?? {};
      return json(200, {
        Id: c.id,
        Name: `/${c.name}`,
        State: { Running: c.running, Status: c.running ? "running" : "exited" },
        Config: { ...createBody, Labels: createBody.Labels ?? {} },
        HostConfig: createBody.HostConfig ?? {},
      });
    }
    if ((m = /^\/containers\/([^/]+)$/.exec(path)) && req.method === "DELETE") {
      const c = this.find(m[1]); if (!c) return json(404, { message: "no such container" });
      this.containers.delete(c.id); res.writeHead(204); return void res.end();
    }
    if ((m = /^\/volumes\/([^/]+)$/.exec(path)) && req.method === "DELETE") {
      res.writeHead(204); return void res.end();
    }
    if ((m = /^\/containers\/([^/]+)\/exec$/.exec(path)) && req.method === "POST") {
      const c = this.find(m[1]); if (!c) return json(404, { message: "no such container" });
      // The daemon's own answer to an exec on a container that is not up.
      if (!c.running) return json(409, { message: `container ${c.id.slice(0, 12)} is not running` });
      const id = randomBytes(32).toString("hex");
      this.execs.set(id, { id, containerId: c.id, cmd: (body as { Cmd: string[] }).Cmd, exitCode: null, running: false });
      return json(201, { Id: id });
    }
    if ((m = /^\/exec\/([^/]+)\/start$/.exec(path)) && req.method === "POST") {
      const e = this.execs.get(m[1]); if (!e) return json(404, { message: "no such exec" });
      e.running = true;
      const r = this.execHandler(e.cmd);
      if (r.neverStart) return; // leave the request hanging -- no response, ever.
      res.writeHead(200, { "Content-Type": "application/vnd.docker.raw-stream" });
      // A real Engine writes its 101/200 line before the exec even starts, so
      // start() resolves promptly; flush now rather than letting Node hold the
      // headers back for the first body write, which is what a still-running
      // command's slow-to-produce-output stream would otherwise look like.
      res.flushHeaders();
      if (r.error) {
        // Simulate a connection drop mid-exec: headers went out, then the
        // wire dies -- no clean end, ever.
        setTimeout(() => { res.destroy(); }, r.delayMs ?? 0);
        return;
      }
      if (r.neverEnd) return; // headers went out; the command never finishes.
      const finish = () => {
        res.write(muxFrames(r.stdout, r.stderr));
        this.finishExec(e, r);
        res.end();
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

  /**
   * `POST /exec/{id}/start` with `Upgrade: tcp`, which is what dockerode
   * sends for `hijack: true` (an exec with stdin). The Engine answers 101 and
   * from then on the socket is the exec's stdin one way and its multiplexed
   * stdout/stderr the other. dockerode sends the JSON body (Content-Length)
   * ahead of the upgrade; the parser hands back whatever it had already read
   * past the headers as `head`, the rest arrives as socket data, and
   * everything after that body is stdin, until the client half-closes.
   */
  private handleUpgrade(req: IncomingMessage, socket: Duplex, head: Buffer): void {
    this.hijacked.add(socket);
    socket.once("close", () => this.hijacked.delete(socket));
    const url = new URL(req.url ?? "/", "http://docker");
    const path = url.pathname.replace(/^\/v[\d.]+/, "");
    const m = /^\/exec\/([^/]+)\/start$/.exec(path);
    if (!m || req.method !== "POST") {
      socket.end("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n");
      return;
    }
    const contentLength = Number(req.headers["content-length"] ?? 0);
    let received = Buffer.alloc(0);
    let body: unknown;
    let bodySeen = false;
    const stdinChunks: Buffer[] = [];
    let exec: FakeExec | undefined;
    let script: ReturnType<ExecHandler> | undefined;

    const onBody = () => {
      const text = received.subarray(0, contentLength).toString("utf8");
      try { body = text.length > 0 ? JSON.parse(text) : undefined; } catch { body = text; }
      this.calls.push({ method: "POST", path, body });
      exec = this.execs.get(m[1]);
      if (!exec) {
        socket.end("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n");
        return;
      }
      exec.running = true;
      script = this.execHandler(exec.cmd);
      if (script.neverStart) return; // no 101, ever: the client never gets its socket.
      socket.write("HTTP/1.1 101 UPGRADED\r\nConnection: Upgrade\r\nUpgrade: tcp\r\n\r\n");
      if (script.error) {
        setTimeout(() => { socket.destroy(); }, script.delayMs ?? 0);
      }
    };
    const take = (chunk: Buffer) => {
      if (bodySeen) { stdinChunks.push(chunk); return; }
      received = Buffer.concat([received, chunk]);
      if (received.length < contentLength) return;
      bodySeen = true;
      const rest = received.subarray(contentLength);
      onBody();
      if (rest.length > 0) stdinChunks.push(rest);
    };
    socket.on("data", take);
    socket.on("end", () => {
      if (!exec || !script) return;
      exec.stdin = Buffer.concat(stdinChunks);
      if (script.neverStart || script.error || script.neverEnd) return;
      const r = script;
      const finish = () => {
        socket.write(muxFrames(r.stdout, r.stderr));
        this.finishExec(exec!, r);
        socket.end();
      };
      if (r.delayMs) setTimeout(finish, r.delayMs); else finish();
    });
    take(head);
  }

  private finishExec(e: FakeExec, r: ReturnType<ExecHandler>): void {
    e.exitCode = r.exitCode;
    if (r.exitAfterEndMs) setTimeout(() => { e.running = false; }, r.exitAfterEndMs);
    else e.running = false;
  }

  private find(idOrName: string): FakeContainer | undefined {
    return this.containers.get(idOrName)
      ?? [...this.containers.values()].find((c) => c.name === idOrName || c.id.startsWith(idOrName));
  }
}

/** Docker multiplexed stream: [type(1) 0 0 0 len(4 BE)] + payload, type 1=stdout 2=stderr. */
function muxFrames(stdout: string, stderr: string): Buffer {
  const frames: Buffer[] = [];
  for (const [type, text] of [[1, stdout], [2, stderr]] as const) {
    if (!text) continue;
    const payload = Buffer.from(text);
    const header = Buffer.alloc(8); header[0] = type; header.writeUInt32BE(payload.length, 4);
    frames.push(header, payload);
  }
  return Buffer.concat(frames);
}

async function readJson(req: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  if (chunks.length === 0) return undefined;
  const text = Buffer.concat(chunks).toString("utf8");
  try { return JSON.parse(text); } catch { return text; }
}
