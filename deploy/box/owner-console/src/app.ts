import { Hono } from 'hono';
import { deleteCookie, getCookie, setCookie } from 'hono/cookie';
import { signSession, verifyPassword, verifySession } from './auth';
import { boxInfo } from './boxinfo';
import { checkAll, probesForEnv, type Health } from './health';
import { dashboard, loginPage } from './views';

const COOKIE = 'nufi_owner';
const NOT_CONFIGURED = 'The owner password is not configured on this box.';

type AppEnv = {
  BOX_OWNER_PASSWORD?: string;
  BOX_OWNER_SESSION_SECRET?: string;
  [key: string]: string | undefined;
};

// `checkHealth` and `now` are injectable so the dashboard route is tested
// without real network calls or a real clock; production uses the defaults.
type Deps = { checkHealth?: () => Promise<Health[]>; now?: () => Date };

export function createApp(env: AppEnv = process.env, deps: Deps = {}): Hono {
  const password = env.BOX_OWNER_PASSWORD ?? '';
  const secret = env.BOX_OWNER_SESSION_SECRET ?? '';
  const configured = Boolean(password && secret);
  const checkHealth = deps.checkHealth ?? (() => checkAll(probesForEnv(env)));
  const now = deps.now ?? (() => new Date());
  const app = new Hono();

  app.get('/healthz', (c) => c.text('ok'));

  app.get('/login', (c) => c.html(loginPage(configured ? undefined : NOT_CONFIGURED)));

  app.post('/login', async (c) => {
    if (!configured) return c.html(loginPage(NOT_CONFIGURED), 401);
    const body = await c.req.parseBody();
    const pw = typeof body.password === 'string' ? body.password : '';
    if (!verifyPassword(pw, password)) return c.html(loginPage('Wrong password.'), 401);
    setCookie(c, COOKIE, signSession(secret), {
      httpOnly: true, secure: true, sameSite: 'Lax', path: '/',
    });
    return c.redirect('/', 303);
  });

  app.post('/logout', (c) => {
    deleteCookie(c, COOKIE, { path: '/' });
    return c.redirect('/login', 303);
  });

  app.get('/', async (c) => {
    if (!configured || !verifySession(secret, getCookie(c, COOKIE))) return c.redirect('/login', 303);
    const health = await checkHealth();
    return c.html(dashboard(boxInfo(env), health, now()));
  });

  return app;
}
