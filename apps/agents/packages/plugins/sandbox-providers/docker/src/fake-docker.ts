import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { randomBytes } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

type ExecHandler = (cmd: string[]) => {
  exitCode: number;
  stdout: string;
  stderr: string;
  delayMs?: number;
  /** Write the response headers, then kill the connection before ever finishing -- a mid-exec drop, not a clean end. */
  error?: boolean;
  /** Never respond at all -- not even headers -- so the client's start() call hangs until it gives up on its own. */
  neverStart?: boolean;
};

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
