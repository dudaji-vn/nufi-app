import { afterEach, beforeEach, describe, expect, test } from 'bun:test';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { usersList } from '../src/api/users';
import { signInvite, verifyInvite } from '../src/invite';
import { MeshError, type Node, type PreAuthKey } from '../src/mesh-api';
import { addUser, listUsers } from '../src/store';
import { TEST_ENV, makeApp, ownerCookie } from './helpers';

const TEMPLATES = join(import.meta.dir, '../../lib/join-templates');
const NOW = Date.parse('2026-10-05T00:00:00Z');
const FUTURE = '2026-10-05T01:00:00Z';
const PAST = '2026-10-04T00:00:00Z';
const rec = (name: string, keyId: string) => ({
  id: 'id-' + name, name, os: 'linux' as const, keyId, token: 't', createdAt: '2026-10-05T00:00:00Z',
});
const node = (id: string, preAuthKeyId?: string): Node => ({
  id, name: 'n' + id, ips: ['100.64.0.' + id], online: true, lastSeen: '', tags: ['tag:member'], preAuthKeyId,
});
const run = (users: ReturnType<typeof rec>[], nodes: Node[], keys: PreAuthKey[]) =>
  usersList({ listUsers: async () => users, listNodes: async () => nodes, listKeys: async () => keys, now: () => NOW });

describe('usersList activation join', () => {
  test('pending: key unused + unexpired, no node', async () => {
    const [r] = await run([rec('a', 'k1')], [], [{ id: 'k1', used: false, expiration: FUTURE }]);
    expect(r.activation).toBe('pending');
    expect(r.expiresAt).toBe(FUTURE);
  });
  test('activated: a node joined on the key, even if the key is now expired/used', async () => {
    const [r] = await run([rec('b', 'k2')], [node('7', 'k2')], [{ id: 'k2', used: true, expiration: PAST }]);
    expect(r.activation).toBe('activated');
    expect(r.nodeIp).toBe('100.64.0.7');
    expect(r.online).toBe(true);
  });
  test('activated even when the key is gone from the coordinator', async () => {
    const [r] = await run([rec('b', 'k2')], [node('7', 'k2')], []);
    expect(r.activation).toBe('activated');
  });
  test('expired: key past expiry, used, or missing; no node', async () => {
    const rows = await run(
      [rec('c', 'k3'), rec('d', 'k4'), rec('e', 'k5')],
      [],
      [{ id: 'k3', used: false, expiration: PAST }, { id: 'k4', used: true, expiration: FUTURE }],
    );
    expect(rows.map((r) => r.activation)).toEqual(['expired', 'expired', 'expired']);
  });
  test('a node with no matching record is not in the table; a node without a key never matches', async () => {
    const rows = await run([rec('a', 'k1')], [node('9', 'stranger-key'), node('10')], [{ id: 'k1', used: false, expiration: FUTURE }]);
    expect(rows.map((r) => r.name)).toEqual(['a']);
    expect(rows[0].activation).toBe('pending');
  });
});

// --- routes ---------------------------------------------------------------
let dir: string;
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'users-'));
  process.env.NUFI_STATE_DIR = dir;
});
afterEach(() => rmSync(dir, { recursive: true, force: true }));

const MESH = { MESH_SERVER_URL: 'https://hs.example', MESH_API_KEY: 'k' };
let nodes: Node[];
let keys: PreAuthKey[];
let minted = 0;
let revoked: string[];
let expired: string[];
const users = {
  listNodes: async () => nodes,
  listKeys: async () => keys,
  mintMemberKeyWithId: async () => {
    minted++;
    keys.push({ id: 'new' + minted, used: false, expiration: new Date(Date.now() + 3600_000).toISOString() });
    return { id: 'new' + minted, key: 'secret-key-' + minted };
  },
  revokeNode: async (_c: unknown, id: string) => { revoked.push(id); },
  expireKey: async (_c: unknown, k: string) => { expired.push(k); },
};
beforeEach(() => { nodes = []; keys = []; minted = 0; revoked = []; expired = []; });

const app = (env = MESH, u: object = users) => makeApp(env, { users: u });
const call = (a: ReturnType<typeof app>, method: string, path: string, body?: unknown, raw = false) =>
  a.request(path, {
    method,
    headers: { cookie: ownerCookie(), ...(body !== undefined && !raw ? { 'content-type': 'application/json' } : {}) },
    body: body === undefined ? undefined : raw ? (body as string) : JSON.stringify(body),
  });

describe('users routes', () => {
  test('requires owner auth', async () => {
    expect((await app().request('/api/users')).status).toBe(401);
  });

  test('coordinator unreachable -> 503 with error', async () => {
    const down = { ...users, listNodes: async () => { throw new MeshError('coordinator unreachable: ECONNREFUSED'); } };
    const r = await call(app(MESH, down), 'GET', '/api/users');
    expect(r.status).toBe(503);
    expect((await r.json()).error).toContain('unreachable');
  });

  test('box not on a mesh -> 503', async () => {
    const r = await call(app({}), 'GET', '/api/users');
    expect(r.status).toBe(503);
    expect((await r.json()).error).toContain('mesh');
  });

  test('POST adds a pending user; bad os -> 400', async () => {
    const a = app();
    expect((await call(a, 'POST', '/api/users', { name: 'Ivy', os: 'beos' })).status).toBe(400);
    expect((await call(a, 'POST', '/api/users', { name: '  ', os: 'linux' })).status).toBe(400);
    const r = await call(a, 'POST', '/api/users', { name: 'Ivy', os: 'macos' });
    expect(r.status).toBe(200);
    const row = await r.json();
    expect(row.name).toBe('Ivy');
    expect(row.activation).toBe('pending');
    expect(row.keyId).toBe('new1');
    expect(verifyInvite(TEST_ENV.BOX_OWNER_SESSION_SECRET, row.token)?.key).toBe('secret-key-1');
    expect((await listUsers()).map((u) => u.name)).toEqual(['Ivy']);
    const list = await (await call(a, 'GET', '/api/users')).json();
    expect(list).toHaveLength(1);
  });

  test('DELETE removes the record and revokes a joined node; 404 when unknown', async () => {
    const a = app();
    const u = await addUser({ name: 'Joe', os: 'linux', keyId: 'kj', token: 't' });
    const u2 = await addUser({ name: 'Pen', os: 'linux', keyId: 'kp', token: 't' });
    nodes = [node('42', 'kj')];
    expect((await call(a, 'DELETE', `/api/users/${u.id}`)).status).toBe(200);
    expect(revoked).toEqual(['42']);
    expect((await call(a, 'DELETE', `/api/users/${u2.id}`)).status).toBe(200);
    expect(revoked).toEqual(['42']); // pending: nothing to revoke
    expect(await listUsers()).toEqual([]);
    expect((await call(a, 'DELETE', '/api/users/nope')).status).toBe(404);
  });

  test('DELETE and regenerate expire the old key secret; DELETE survives an expire failure', async () => {
    const secret = TEST_ENV.BOX_OWNER_SESSION_SECRET;
    const tok = (k: string) => signInvite(secret, { key: k, serverUrl: 'https://hs.example' }, 3600);
    const a = app();
    const u = await addUser({ name: 'X', os: 'linux', keyId: 'kx', token: tok('secret-x') });
    await call(a, 'POST', `/api/users/${u.id}/regenerate`);
    expect(expired).toEqual(['secret-x']);
    const u2 = await addUser({ name: 'Y', os: 'linux', keyId: 'ky', token: tok('secret-y') });
    expect((await call(a, 'DELETE', `/api/users/${u2.id}`)).status).toBe(200);
    expect(expired).toEqual(['secret-x', 'secret-y']);
    const boom = app(MESH, { ...users, expireKey: async () => { throw new MeshError('nope'); } });
    const u3 = await addUser({ name: 'Z', os: 'linux', keyId: 'kz', token: tok('secret-z') });
    expect((await call(boom, 'DELETE', `/api/users/${u3.id}`)).status).toBe(200);
    expect((await listUsers()).some((x) => x.id === u3.id)).toBe(false);
  });

  test('a failed revoke returns 503 and keeps the record', async () => {
    const u = await addUser({ name: 'Keep', os: 'linux', keyId: 'kk', token: 't' });
    nodes = [node('5', 'kk')];
    const bad = app(MESH, { ...users, revokeNode: async () => { throw new MeshError('coordinator unreachable'); } });
    expect((await call(bad, 'DELETE', `/api/users/${u.id}`)).status).toBe(503);
    expect((await listUsers()).map((x) => x.id)).toEqual([u.id]);
    expect(expired).toEqual([]);
  });

  test('regenerate swaps keyId and token', async () => {
    const a = app();
    const u = await addUser({ name: 'Zed', os: 'linux', keyId: 'old', token: 'oldtoken' });
    const r = await call(a, 'POST', `/api/users/${u.id}/regenerate`);
    expect(r.status).toBe(200);
    const row = await r.json();
    expect(row.keyId).toBe('new1');
    expect(row.token).not.toBe('oldtoken');
    expect(row.activation).toBe('pending');
    expect((await listUsers())[0].keyId).toBe('new1');
    expect((await call(a, 'POST', '/api/users/nope/regenerate')).status).toBe(404);
  });

  test('connector: linux download, macos plan, bad token 400', async () => {
    const secret = TEST_ENV.BOX_OWNER_SESSION_SECRET;
    const token = signInvite(secret, { key: 'join-key', serverUrl: 'https://hs.example' }, 3600);
    const u = await addUser({ name: 'Lin', os: 'linux', keyId: 'k', token });
    const a = makeApp(MESH, { users, templatesDir: TEMPLATES, boxCaB64: async () => '', coordCaB64: () => '', agentSha256: () => ({ amd64: '', arm64: '' }) });
    const lin = await call(a, 'GET', `/api/users/${u.id}/connector`);
    expect(lin.status).toBe(200);
    expect(lin.headers.get('content-disposition')).toContain('attachment');
    expect(await lin.text()).toContain('join-key');
    const mac = await call(a, 'GET', `/api/users/${u.id}/connector?os=macos`);
    expect(mac.status).toBe(200);
    expect((await mac.json()).enroll).toContain('join-key');
    expect((await call(a, 'GET', `/api/users/${u.id}/connector?os=beos`)).status).toBe(400);
    const bad = await addUser({ name: 'Bad', os: 'linux', keyId: 'k', token: 'garbage' });
    expect((await call(a, 'GET', `/api/users/${bad.id}/connector`)).status).toBe(400);
  });

  test('import CSV adds rows (skipping malformed); export lists name,link', async () => {
    const a = app();
    const r = await call(a, 'POST', '/api/users/import', 'name,os\n=Ann,windows\nbroken-row\nBob,linux\n', true);
    expect(r.status).toBe(200);
    const rows = await r.json();
    expect(rows.map((x: { name: string }) => x.name)).toEqual(['=Ann', 'Bob']);
    expect(r.headers.get('x-skipped')).toBe('1');
    const e = await call(a, 'POST', '/api/users/export');
    expect(e.headers.get('content-type')).toContain('text/csv');
    expect(e.headers.get('content-disposition')).toContain('attachment');
    const lines = (await e.text()).trim().split('\n');
    expect(lines[0]).toBe('name,link');
    expect(lines).toHaveLength(3);
    expect(lines[1]).toContain("'=Ann,");
    expect(lines[1]).toContain('/connect#token=');
  });

  test('export honors selected ids; no body or empty ids exports all', async () => {
    const a = app();
    const r = await call(a, 'POST', '/api/users/import', 'name,os\nAnn,windows\nBob,linux\n', true);
    const [ann, bob] = await r.json();
    const only = await (await call(a, 'POST', '/api/users/export', { ids: [ann.id] })).text();
    expect(only).toContain('Ann,');
    expect(only).not.toContain('Bob,');
    expect(only.trim().split('\n')).toHaveLength(2);
    expect(bob.id).not.toBe(ann.id);
    for (const body of [undefined, {}, { ids: [] }]) {
      const all = await (await call(a, 'POST', '/api/users/export', body)).text();
      expect(all.trim().split('\n')).toHaveLength(3);
    }
  });
});
