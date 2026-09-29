import { readFileSync } from 'node:fs';
import { Hono } from 'hono';
import { deleteCookie, getCookie, setCookie } from 'hono/cookie';
import { signSession, verifyPassword, verifySession } from './auth';
import { boxInfo } from './boxinfo';
import { isOS, renderConnector } from './connector';
import { checkAll, probesForEnv, type Health } from './health';
import { connectLink, signInvite, verifyInvite } from './invite';
import { MeshError, listNodes, meshConfig, mintMemberKey, revokeNode, type MeshConfig } from './mesh-api';
import { connectPage, dashboard, loginPage, type InviteResult, type MembersData } from './views';

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
  mint?: (cfg: MeshConfig) => Promise<string>;
  now?: () => Date;
  templatesDir?: string;
  boxCaB64?: () => Promise<string>;
  coordCaB64?: () => string;
  listMembers?: () => Promise<MembersData>;
  revoke?: (cfg: MeshConfig, id: string) => Promise<void>;
};

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

export function createApp(env: AppEnv = process.env, deps: Deps = {}): Hono {
  const password = env.BOX_OWNER_PASSWORD ?? '';
  const secret = env.BOX_OWNER_SESSION_SECRET ?? '';
  const configured = Boolean(password && secret);
  const canInvite = meshConfig(env) !== null;
  const checkHealth = deps.checkHealth ?? (() => checkAll(probesForEnv(env)));
  const mint = deps.mint ?? ((cfg: MeshConfig) => mintMemberKey(cfg));
  const now = deps.now ?? (() => new Date());
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

  const app = new Hono();

  const authed = (c: { req: { header: (n: string) => string | undefined } }) =>
    configured && verifySession(secret, getCookie(c as never, COOKIE));

  // The current mesh members, best-effort: undefined when the box is not on a
  // mesh, an error string when the coordinator can't be reached, else the list.
  const listMembersSafe = async (): Promise<MembersData> => {
    if (deps.listMembers) return deps.listMembers();
    const cfg = meshConfig(env);
    if (!cfg) return undefined;
    try {
      return await listNodes(cfg);
    } catch (e) {
      return { error: e instanceof MeshError ? e.message : 'coordinator unreachable' };
    }
  };

  const render = async (invite?: InviteResult) => {
    const [health, members] = await Promise.all([checkHealth(), listMembersSafe()]);
    return dashboard(boxInfo(env), health, now(), invite, canInvite, members);
  };

  app.get('/healthz', (c) => c.text('ok'));

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

  app.get('/', async (c) => {
    if (!authed(c)) return c.redirect('/login', 303);
    return c.html(await render());
  });

  app.post('/invite', async (c) => {
    if (!authed(c)) return c.redirect('/login', 303);
    const cfg = meshConfig(env);
    if (!cfg) return c.html(await render({ error: 'This box is not on a mesh yet — run `nufi-box mesh up` first.' }));
    try {
      const key = await mint(cfg);
      const token = signInvite(secret, { key, serverUrl: cfg.serverUrl });
      return c.html(await render({ link: connectLink(originOf(c), token) }));
    } catch (e) {
      const unreachable = e instanceof MeshError && /unreachable/.test(e.message);
      const detail = e instanceof MeshError ? e.message : 'could not reach the coordinator';
      const hint = unreachable
        ? ' If this box runs with --egress-enforce, the coordinator must be on the egress allow-list.'
        : '';
      return c.html(await render({ error: `Invite failed: ${detail}.${hint}` }));
    }
  });

  // Remove one member by node id (day-two). Session-guarded; the destructive
  // confirm is a client-side guard on the form.
  app.post('/revoke', async (c) => {
    if (!authed(c)) return c.redirect('/login', 303);
    const cfg = meshConfig(env);
    if (!cfg) return c.html(await render());
    const body = await c.req.parseBody();
    const id = typeof body.id === 'string' ? body.id : '';
    if (!id) return c.redirect('/', 303);
    try {
      await (deps.revoke ? deps.revoke(cfg, id) : revokeNode(cfg, id));
    } catch (e) {
      const detail = e instanceof MeshError ? e.message : 'could not reach the coordinator';
      return c.html(await render({ error: `Revoke failed: ${detail}.` }));
    }
    return c.redirect('/', 303); // gone from the list on the reloaded dashboard
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
    const connector = renderConnector({
      os,
      member,
      key: invite.key,
      serverUrl: invite.serverUrl,
      boxMeshHost: info.mesh.host,
      departments: info.departments,
      boxCaB64: await boxCaB64(),
      coordCaB64: coordCaB64(),
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
