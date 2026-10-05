import { existsSync, readFileSync, statSync } from 'node:fs';
import { join, normalize, resolve, sep } from 'node:path';
import { Hono } from 'hono';
import { deleteCookie, getCookie, setCookie } from 'hono/cookie';
import { signSession, verifyPassword, verifySession } from './auth';
import { filesRoutes } from './api/files';
import { controlRoutes, type ControlDeps } from './api/control';
import { buildStatus } from './api/status';
import { usersRoutes, type UsersDeps } from './api/users';
import { boxInfo } from './boxinfo';
import { isOS, macosPlan, renderConnector } from './connector';
import { checkAll, probesForEnv, type Health } from './health';
import { verifyInvite } from './invite';
import { connectPage, loginPage } from './views';

const COOKIE = 'nufi_owner';
const NOT_CONFIGURED = 'The owner password is not configured on this box.';

type AppEnv = {
  BOX_OWNER_PASSWORD?: string;
  BOX_OWNER_SESSION_SECRET?: string;
  [key: string]: string | undefined;
};

// Injectable so the routes are tested without real network calls, filesystem,
// or clock; production uses the defaults.
type Deps = {
  checkHealth?: () => Promise<Health[]>;
  templatesDir?: string;
  boxCaB64?: () => Promise<string>;
  coordCaB64?: () => string;
  agentDistDir?: string;
  agentSha256?: () => { amd64: string; arm64: string };
  exec?: Partial<ControlDeps>;
  users?: Partial<UsersDeps>;
};

// The NufiBox Agent bundles the box ships for a member to install — the Linux
// tarballs (one per arch) and the signed macOS .pkg. The name is allow-listed so
// the path can never escape the dist directory.
const AGENT_FILE = /^nufibox-agent-(linux-(amd64|arm64)\.tar\.gz|macos\.pkg)$/;

function originOf(c: { req: { header: (n: string) => string | undefined } }): string {
  const proto = c.req.header('x-forwarded-proto') ?? 'https';
  const host = c.req.header('host') ?? 'localhost';
  return `${proto}://${host}`;
}

const b64OfFile = (path: string): string => {
  try {
    return Buffer.from(readFileSync(path)).toString('base64');
  } catch {
    return '';
  }
};

// The first whitespace-delimited token of a `.sha256` file (plain hex, or the
// `<hash>  <file>` form), lowercased; '' if unreadable. Only a well-formed
// 64-char hex digest is returned, so a garbled file can never inject into the
// generated script.
const shaOfFile = (path: string): string => {
  try {
    const tok = (readFileSync(path, 'utf8').trim().split(/\s+/)[0] ?? '').toLowerCase();
    return /^[0-9a-f]{64}$/.test(tok) ? tok : '';
  } catch {
    return '';
  }
};

export function createApp(env: AppEnv = process.env, deps: Deps = {}): Hono {
  const password = env.BOX_OWNER_PASSWORD ?? '';
  const secret = env.BOX_OWNER_SESSION_SECRET ?? '';
  const configured = Boolean(password && secret);
  const checkHealth = deps.checkHealth ?? (() => checkAll(probesForEnv(env)));
  const templatesDir = deps.templatesDir ?? env.JOIN_TEMPLATES_DIR ?? '/app/join-templates';

  // The box's own Caddy CA is public (served on :80), so fetch it rather than
  // mount the caddy volume. Best-effort: on failure the connector still joins
  // the mesh, the member just gets a cert warning opening chat.
  const boxCaUrl = env.BOX_CA_URL ?? 'http://caddy/nufi-box-ca.crt';
  const boxCaB64 = deps.boxCaB64 ?? (async () => {
    try {
      const r = await fetch(boxCaUrl, { signal: AbortSignal.timeout(5000) });
      if (!r.ok) return '';
      return Buffer.from(await r.arrayBuffer()).toString('base64');
    } catch {
      return '';
    }
  });
  // The coordinator CA is embedded only for a SELF-HOSTED (internal-CA) box; a
  // public coordinator needs no embedded CA (and /mesh-ca.crt is the system
  // bundle there, which must not be embedded).
  const coordCaB64 = deps.coordCaB64 ?? (() =>
    env.NUFI_SELF_HOST_COORD === '1' ? b64OfFile(env.NODE_EXTRA_CA_CERTS ?? '/mesh-ca.crt') : '');

  const agentDistDir = deps.agentDistDir ?? env.AGENT_DIST_DIR ?? '/app/agent-dist';
  // The digests baked beside each agent tarball at image-build time (build-agent.sh).
  const agentSha256 = deps.agentSha256 ?? (() => ({
    amd64: shaOfFile(`${agentDistDir}/nufibox-agent-linux-amd64.tar.gz.sha256`),
    arm64: shaOfFile(`${agentDistDir}/nufibox-agent-linux-arm64.tar.gz.sha256`),
  }));
  const app = new Hono();

  const authed = (c: { req: { header: (n: string) => string | undefined } }) =>
    configured && verifySession(secret, getCookie(c as never, COOKIE));

  app.get('/healthz', (c) => c.text('ok'));

  // Every /api/* route needs an owner session, except the public ping.
  app.use('/api/*', async (c, next) => {
    if (c.req.method === 'GET' && c.req.path === '/api/ping') return next();
    if (!authed(c)) return c.json({ error: 'unauthorized' }, 401);
    return next();
  });

  app.get('/api/ping', (c) => c.json({ ok: true }));

  app.get('/api/status', async (c) => c.json(await buildStatus(() => boxInfo(env), checkHealth)));

  app.route('/api', controlRoutes(deps.exec));

  app.route('/api', filesRoutes(env));

  app.route('/api', usersRoutes({ env, secret, origin: originOf, boxCaB64, coordCaB64, templatesDir, agentSha256 }, deps.users));

  // The React SPA (built to web/dist). Served at / and /app; unknown /api/* is a real 404, unknown /assets/*
  // is a 404, and any other unmatched GET falls back to index.html (client routes).
  const distDir = resolve(env.WEB_DIST_DIR ?? join(import.meta.dir, '../web/dist'));
  const spaIndex = () => {
    const f = join(distDir, 'index.html');
    return existsSync(f) ? new Response(Bun.file(f), { headers: { 'content-type': 'text/html; charset=utf-8' } }) : null;
  };
  app.get('/assets/*', (c) => {
    const rel = normalize(decodeURIComponent(new URL(c.req.url).pathname).replace(/^\/+/, ''));
    const f = resolve(distDir, rel);
    if (!f.startsWith(distDir + sep) || !existsSync(f) || !statSync(f).isFile()) return c.notFound();
    return new Response(Bun.file(f), { headers: { 'cache-control': 'public, max-age=31536000, immutable' } });
  });
  app.get('/app', (c) => spaIndex() ?? c.notFound());
  app.get('/app/*', (c) => spaIndex() ?? c.notFound());

  // The owner console: the SPA at / (and /app). Unauthenticated -> the login page.
  app.get('/', (c) => {
    if (!authed(c)) return c.redirect('/login', 303);
    return spaIndex() ?? c.redirect('/app', 303);
  });

  app.get('/login', (c) => c.html(loginPage(configured ? undefined : NOT_CONFIGURED)));

  app.post('/login', async (c) => {
    if (!configured) return c.html(loginPage(NOT_CONFIGURED), 401);
    const body = await c.req.parseBody();
    const pw = typeof body.password === 'string' ? body.password : '';
    if (!verifyPassword(pw, password)) return c.html(loginPage('Wrong password.'), 401);
    setCookie(c, COOKIE, signSession(secret), { httpOnly: true, secure: true, sameSite: 'Lax', path: '/' });
    return c.redirect('/', 303);
  });

  app.post('/logout', (c) => {
    deleteCookie(c, COOKIE, { path: '/' });
    return c.redirect('/login', 303);
  });

  // The de-branded NufiBox Agent, served for a member to install — public and
  // reachable on plain :80 (like /connect), so a laptop that has not trusted the
  // box CA yet can fetch it. Not secret: it is the client binaries + wrapper.
  app.get('/agent/:file', async (c) => {
    const file = c.req.param('file');
    // The coordinator CA, for the macOS enrol command on a self-hosted box. Not
    // secret (a CA public cert); empty (404) on a public-coordinator box.
    if (file === 'mesh-ca.crt') {
      const pem = Buffer.from(coordCaB64(), 'base64').toString('utf8');
      return pem ? new Response(pem, { headers: { 'content-type': 'application/x-pem-file' } }) : c.text('not found', 404);
    }
    if (!AGENT_FILE.test(file)) return c.text('not found', 404);
    const f = Bun.file(`${agentDistDir}/${file}`);
    if (!(await f.exists())) return c.text('not found', 404);
    const type = file.endsWith('.pkg') ? 'application/octet-stream' : 'application/gzip';
    return new Response(f.stream(), {
      headers: { 'content-type': type, 'content-disposition': `attachment; filename="${file}"` },
    });
  });

  // --- member-facing, NO login (the invite token is the credential) ---------
  // Served on plain :80 too (see the Caddyfile), so a laptop that has not yet
  // trusted the box CA can open it. The token is in the URL #fragment, read
  // client-side and POSTed back — the server never sees it on the GET.
  app.get('/connect', (c) => c.html(connectPage()));

  app.post('/connect/connector', async (c) => {
    const body = await c.req.parseBody();
    const token = typeof body.token === 'string' ? body.token : '';
    const os = typeof body.os === 'string' ? body.os : '';
    const member = typeof body.member === 'string' ? body.member : '';
    if (!isOS(os)) return c.text('unknown operating system', 400);
    const invite = verifyInvite(secret, token);
    if (!invite) return c.text('this invite link is invalid or has expired — ask for a new one', 400);
    const info = boxInfo(env);
    // macOS: no downloadable script (an unsigned .command re-triggers Gatekeeper).
    // Return a plan the page renders as steps — install the signed .pkg, then paste
    // one enrol command.
    if (os === 'macos') {
      return c.json(macosPlan({
        os, member, key: invite.key, serverUrl: invite.serverUrl,
        boxMeshHost: info.mesh.host, departments: info.departments,
        boxCaB64: '', coordCaB64: coordCaB64(), boxUrl: originOf(c),
      }));
    }
    const connector = renderConnector({
      os,
      member,
      key: invite.key,
      serverUrl: invite.serverUrl,
      boxMeshHost: info.mesh.host,
      departments: info.departments,
      boxCaB64: await boxCaB64(),
      coordCaB64: coordCaB64(),
      boxUrl: originOf(c), // where the member reached us, for the agent download (linux)
      agentSha256: agentSha256(), // verify the agent download before it runs as root (linux)
    }, templatesDir);
    return new Response(connector.body, {
      headers: {
        'content-type': connector.contentType,
        'content-disposition': `attachment; filename="${connector.filename}"`,
      },
    });
  });

  return app;
}
