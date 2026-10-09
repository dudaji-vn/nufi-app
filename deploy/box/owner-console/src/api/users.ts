import { Hono, type Context } from 'hono';
import { boxInfo } from '../boxinfo';
import { isOS, macosPlan, renderConnector, type OS } from '../connector';
import { connectLink, signInvite, verifyInvite } from '../invite';
import {
  MeshError, expireKey, listKeys, listNodes, meshConfig, mintMemberKeyWithId, revokeNode,
  type MeshConfig, type Node, type PreAuthKey,
} from '../mesh-api';
import { addUser, listUsers, removeUser, updateUser, type UserRecord } from '../store';

export type UserRow = UserRecord & {
  activation: 'pending' | 'activated' | 'expired';
  expiresAt?: string;
  nodeIp?: string;
  online?: boolean;
  // A LAN-shareable /connect link built from the box's canonical host on plain
  // :80 (see memberBase), so a member on another machine can open it — unlike a
  // link carrying whatever host the owner happened to open the console with.
  inviteUrl?: string;
};

export type UsersListDeps = {
  listNodes: () => Promise<Node[]>;
  listKeys: () => Promise<PreAuthKey[]>;
  listUsers: () => Promise<UserRecord[]>;
  now?: () => number;
};

// THE activation join. The local store drives the table (we iterate users, never
// nodes, so a node nobody invited is never shown); headscale only answers "did a
// node join on this user's key?" and "is that key still usable?".
//   node joined on the key  -> activated (even if the key has since expired/been used)
//   key gone, used, expired -> expired
//   otherwise               -> pending
export async function usersList(d: UsersListDeps): Promise<UserRow[]> {
  const [nodes, keys, users] = await Promise.all([d.listNodes(), d.listKeys(), d.listUsers()]);
  const now = d.now?.() ?? Date.now();
  return users.map((user): UserRow => {
    const joined = nodes.find((n) => n.preAuthKeyId !== undefined && n.preAuthKeyId === user.keyId);
    if (joined) return { ...user, activation: 'activated', nodeIp: joined.ips[0], online: joined.online };
    const key = keys.find((k) => k.id === user.keyId);
    if (!key) return { ...user, activation: 'expired' };
    if (key.used || (key.expiration && Date.parse(key.expiration) < now)) return { ...user, activation: 'expired' };
    return { ...user, activation: 'pending', expiresAt: key.expiration };
  });
}

export interface UsersDeps {
  listNodes: (cfg: MeshConfig) => Promise<Node[]>;
  listKeys: (cfg: MeshConfig) => Promise<PreAuthKey[]>;
  listUsers: typeof listUsers;
  addUser: typeof addUser;
  updateUser: typeof updateUser;
  removeUser: typeof removeUser;
  mintMemberKeyWithId: (cfg: MeshConfig) => Promise<{ id: string; key: string }>;
  revokeNode: (cfg: MeshConfig, id: string) => Promise<void>;
  expireKey: (cfg: MeshConfig, keySecret: string) => Promise<void>;
}

const real: UsersDeps = {
  listNodes: (cfg) => listNodes(cfg),
  listKeys: (cfg) => listKeys(cfg),
  listUsers, addUser, updateUser, removeUser,
  mintMemberKeyWithId: (cfg) => mintMemberKeyWithId(cfg),
  revokeNode: (cfg, id) => revokeNode(cfg, id),
  expireKey: (cfg, k) => expireKey(cfg, k),
};

// What the connector download needs from the app (same values /connect/connector uses).
export type UsersCtx = {
  env: Record<string, string | undefined>;
  secret: string;
  origin: (c: Context) => string;
  boxCaB64: () => Promise<string>;
  coordCaB64: () => string;
  templatesDir: string;
  agentSha256: () => { amd64: string; arm64: string };
};

const INVITE_TTL = 3600;
const NO_MESH = 'This box is not on a mesh yet — run `nufi-box mesh up` first.';

// A leading = + - @ would run as a formula in a spreadsheet, so prefix a quote.
const csvCell = (raw: string) => {
  const v = /^[=+\-@]/.test(raw) ? `'${raw}` : raw;
  return /[",\r\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
};
const unquote = (v: string) => {
  const t = v.trim();
  return t.length >= 2 && t.startsWith('"') && t.endsWith('"') ? t.slice(1, -1).replace(/""/g, '"') : t;
};

// Mounted behind the /api/* owner-auth middleware.
export function usersRoutes(ctx: UsersCtx, deps: Partial<UsersDeps> = {}): Hono {
  const d = { ...real, ...deps };
  const r = new Hono();

  const rows = (cfg: MeshConfig) =>
    usersList({ listNodes: () => d.listNodes(cfg), listKeys: () => d.listKeys(cfg), listUsers: d.listUsers });

  // Where a member reaches the box: plain HTTP :80 at the box's canonical LAN
  // host (its IP, else its configured hostname). The box Caddyfile serves
  // /connect and /agent/* on :80 precisely for a laptop that has NOT yet
  // trusted the box CA — the join file's `curl` of the agent can't click
  // through a TLS warning, so it must be plain :80, not the owner's TLS :3009
  // console origin (also a host only the owner's machine resolves).
  const memberBase = (c: Context): string => {
    let host = ctx.env.BOX_IP || ctx.env.BOX_HOST || '';
    if (!host) {
      try { host = new URL(ctx.origin(c)).hostname; } catch { host = 'localhost'; }
    }
    return `http://${host}`;
  };
  const withInvite = (c: Context, row: UserRow): UserRow => ({ ...row, inviteUrl: connectLink(memberBase(c), row.token) });

  const mint = async (cfg: MeshConfig) => {
    const { id, key } = await d.mintMemberKeyWithId(cfg);
    return { keyId: id, token: signInvite(ctx.secret, { key, serverUrl: cfg.serverUrl }, INVITE_TTL) };
  };

  // Runs a mesh-dependent handler: no mesh config or an unreachable coordinator is a 503.
  const withMesh = (fn: (c: Context, cfg: MeshConfig) => Promise<Response>) => async (c: Context) => {
    const cfg = meshConfig(ctx.env);
    if (!cfg) return c.json({ error: NO_MESH }, 503);
    try {
      return await fn(c, cfg);
    } catch (e) {
      if (e instanceof MeshError) return c.json({ error: e.message }, 503);
      return c.json({ error: e instanceof Error ? e.message : 'request failed' }, 500);
    }
  };

  // Best-effort belt-and-suspenders: expire the record's pre-auth key so the old link dies.
  // Failure is swallowed — the node revoke is the security-critical step. Live endpoint shape is verified in Task 11.
  const expireRecordKey = async (cfg: MeshConfig, rec: UserRecord) => {
    try {
      const invite = verifyInvite(ctx.secret, rec.token);
      if (invite) await d.expireKey(cfg, invite.key);
    } catch {
      /* best-effort */
    }
  };

  const rowFor = async (cfg: MeshConfig, id: string) => (await rows(cfg)).find((x) => x.id === id);

  r.get('/users', withMesh(async (c, cfg) => c.json((await rows(cfg)).map((row) => withInvite(c, row)))));

  r.post('/users', withMesh(async (c, cfg) => {
    const body = (await c.req.json().catch(() => ({}))) as { name?: unknown; os?: unknown; method?: unknown };
    const name = typeof body.name === 'string' ? body.name.trim() : '';
    if (!name) return c.json({ error: 'name is required' }, 400);
    if (!isOS(body.os)) return c.json({ error: 'unknown operating system' }, 400);
    const addingMethod = body.method === 'public' ? 'public' : 'private';
    const rec = await d.addUser({ name, os: body.os, addingMethod, ...(await mint(cfg)) });
    return c.json(withInvite(c, ((await rowFor(cfg, rec.id)) ?? rec) as UserRow));
  }));

  r.delete('/users/:id', async (c) => {
    const id = c.req.param('id');
    const rec = (await d.listUsers()).find((u) => u.id === id);
    if (!rec) return c.json({ error: 'user not found' }, 404);
    const cfg = meshConfig(ctx.env);
    if (cfg) {
      try {
        const joined = (await d.listNodes(cfg)).find((n) => n.preAuthKeyId !== undefined && n.preAuthKeyId === rec.keyId);
        if (joined) await d.revokeNode(cfg, joined.id);
        await expireRecordKey(cfg, rec);
      } catch (e) {
        // Keep the record: removing it while the node still has access would orphan that laptop.
        return c.json({ error: e instanceof Error ? e.message : 'revoke failed' }, e instanceof MeshError ? 503 : 500);
      }
    }
    await d.removeUser(id);
    return c.json({ ok: true });
  });

  r.post('/users/:id/regenerate', withMesh(async (c, cfg) => {
    const id = c.req.param('id');
    const rec = (await d.listUsers()).find((u) => u.id === id);
    if (!rec) return c.json({ error: 'user not found' }, 404);
    const fresh = await mint(cfg);
    await d.updateUser(id, fresh);
    await expireRecordKey(cfg, rec);
    const row = await rowFor(cfg, id);
    return c.json(row ? withInvite(c, row) : row);
  }));

  r.get('/users/:id/connector', async (c) => {
    const rec = (await d.listUsers()).find((u) => u.id === c.req.param('id'));
    if (!rec) return c.json({ error: 'user not found' }, 404);
    const q = c.req.query('os');
    if (q !== undefined && !isOS(q)) return c.json({ error: 'unknown operating system' }, 400);
    const os: OS = (q as OS | undefined) ?? rec.os;
    const invite = verifyInvite(ctx.secret, rec.token);
    if (!invite) return c.json({ error: 'this invite is invalid or has expired — regenerate it' }, 400);
    const info = boxInfo(ctx.env);
    const input = {
      os, member: rec.name, key: invite.key, serverUrl: invite.serverUrl,
      boxMeshHost: info.mesh.host, departments: info.departments,
      boxCaB64: '', coordCaB64: ctx.coordCaB64(), boxUrl: memberBase(c),
    };
    if (os === 'macos') return c.json(macosPlan(input));
    const connector = renderConnector(
      { ...input, boxCaB64: await ctx.boxCaB64(), agentSha256: ctx.agentSha256() },
      ctx.templatesDir,
    );
    return new Response(connector.body, {
      headers: {
        'content-type': connector.contentType,
        'content-disposition': `attachment; filename="${connector.filename}"`,
      },
    });
  });

  // CSV rows are `name,os` (an optional header row is skipped). Malformed rows are
  // skipped and counted in X-Skipped.
  r.post('/users/import', withMesh(async (c, cfg) => {
    const lines = (await c.req.text()).split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const added: string[] = [];
    let skipped = 0;
    for (const [i, line] of lines.entries()) {
      const cut = line.lastIndexOf(',');
      const name = cut < 0 ? '' : unquote(line.slice(0, cut));
      const os = cut < 0 ? '' : unquote(line.slice(cut + 1)).toLowerCase();
      if (i === 0 && name.toLowerCase() === 'name' && os === 'os') continue;
      if (!name || !isOS(os)) { skipped++; continue; }
      added.push((await d.addUser({ name, os, ...(await mint(cfg)) })).id);
    }
    const all = await rows(cfg);
    return c.json(all.filter((x) => added.includes(x.id)).map((row) => withInvite(c, row)), 200, { 'x-skipped': String(skipped) });
  }));

  r.post('/users/export', async (c) => {
    const origin = memberBase(c); // LAN-shareable links in the exported CSV, same as the table
    const body = (await c.req.json().catch(() => null)) as { ids?: unknown } | null;
    const ids = body && Array.isArray(body.ids) ? body.ids : [];
    const users = await d.listUsers();
    const picked = ids.length ? users.filter((u) => ids.includes(u.id)) : users;
    const lines = ['name,link', ...picked.map((u) => `${csvCell(u.name)},${csvCell(connectLink(origin, u.token))}`)];
    return new Response(lines.join('\n') + '\n', {
      headers: { 'content-type': 'text/csv; charset=utf-8', 'content-disposition': 'attachment; filename="nufi-users.csv"' },
    });
  });

  return r;
}
