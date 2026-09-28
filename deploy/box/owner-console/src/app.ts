import { Hono } from 'hono';
import { deleteCookie, getCookie, setCookie } from 'hono/cookie';
import { signSession, verifyPassword, verifySession } from './auth';
import { boxInfo } from './boxinfo';
import { checkAll, probesForEnv, type Health } from './health';
import { connectLink, signInvite } from './invite';
import { MeshError, meshConfig, mintMemberKey, type MeshConfig } from './mesh-api';
import { dashboard, loginPage, type InviteResult } from './views';

const COOKIE = 'nufi_owner';
const NOT_CONFIGURED = 'The owner password is not configured on this box.';

type AppEnv = {
  BOX_OWNER_PASSWORD?: string;
  BOX_OWNER_SESSION_SECRET?: string;
  [key: string]: string | undefined;
};

// `checkHealth`, `mint` and `now` are injectable so the routes are tested
// without real network calls or a real clock; production uses the defaults.
type Deps = {
  checkHealth?: () => Promise<Health[]>;
  mint?: (cfg: MeshConfig) => Promise<string>;
  now?: () => Date;
};

// The external origin the owner reached us on (Caddy preserves Host and sets
// X-Forwarded-Proto), so an invite link is correct on the LAN name, the IP, or
// the mesh name without the box being told which.
function originOf(c: { req: { header: (n: string) => string | undefined } }): string {
  const proto = c.req.header('x-forwarded-proto') ?? 'https';
  const host = c.req.header('host') ?? 'localhost';
  return `${proto}://${host}`;
}

export function createApp(env: AppEnv = process.env, deps: Deps = {}): Hono {
  const password = env.BOX_OWNER_PASSWORD ?? '';
  const secret = env.BOX_OWNER_SESSION_SECRET ?? '';
  const configured = Boolean(password && secret);
  const checkHealth = deps.checkHealth ?? (() => checkAll(probesForEnv(env)));
  const mint = deps.mint ?? ((cfg: MeshConfig) => mintMemberKey(cfg));
  const now = deps.now ?? (() => new Date());
  const app = new Hono();

  const authed = (c: { req: { header: (n: string) => string | undefined } }) =>
    configured && verifySession(secret, getCookie(c as never, COOKIE));

  const render = async (invite?: InviteResult) =>
    dashboard(boxInfo(env), await checkHealth(), now(), invite);

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

  // Generate a share link for one laptop: mint a tag:member pre-auth key on the
  // coordinator, wrap it in a signed token, and hand back /connect?token=…
  app.post('/invite', async (c) => {
    if (!authed(c)) return c.redirect('/login', 303);
    const cfg = meshConfig(env);
    if (!cfg) {
      return c.html(await render({ error: 'This box is not on a mesh yet — run `nufi-box mesh up` first.' }));
    }
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

  return app;
}
