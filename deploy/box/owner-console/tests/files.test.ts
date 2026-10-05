import { afterEach, beforeEach, expect, test } from 'bun:test';
import { existsSync, mkdirSync, symlinkSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { makeApp, ownerCookie } from './helpers';

let root: string;
let app: ReturnType<typeof makeApp>;

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'drives-'));
  mkdirSync(join(root, 'legal'));
  writeFileSync(join(root, 'legal', 'a.pdf'), 'hello-bytes');
  app = makeApp({ NUFI_DRIVES_DIR: root, DEPARTMENTS: 'legal,hr' });
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

const get = (path: string, auth = true) =>
  app.request(path, { headers: auth ? { cookie: ownerCookie() } : {} });
const upload = (dept: string, filename: string, body = 'data', auth = true, path = '') => {
  const fd = new FormData();
  fd.set('file', new File([body], filename));
  return app.request(`/api/files?dept=${dept}&path=${path}`, {
    method: 'POST',
    headers: auth ? { cookie: ownerCookie() } : {},
    body: fd,
  });
};

test('requires owner auth', async () => {
  expect((await get('/api/files?dept=legal', false)).status).toBe(401);
  expect((await upload('legal', 'x.txt', 'd', false)).status).toBe(401);
  expect((await get('/api/files/legal/a.pdf', false)).status).toBe(401);
});

test('lists files in a known department', async () => {
  const r = await get('/api/files?dept=legal');
  expect(r.status).toBe(200);
  const rows = await r.json();
  expect(rows).toHaveLength(1);
  expect(rows[0]).toMatchObject({ name: 'a.pdf', kind: 'file', size: 11 });
  expect(Date.parse(rows[0].uploadedAt)).not.toBeNaN();
  expect(Date.parse(rows[0].modifiedAt)).not.toBeNaN();
});

test('a known department with no directory yet lists as empty', async () => {
  const r = await get('/api/files?dept=hr');
  expect(r.status).toBe(200);
  expect(await r.json()).toEqual([]);
});

test('rejects unknown dept and dept traversal', async () => {
  expect((await get('/api/files?dept=../../etc')).status).toBe(400);
  expect((await get('/api/files?dept=nope')).status).toBe(400);
  expect((await get('/api/files')).status).toBe(400);
  expect((await upload('..', 'x.txt')).status).toBe(400);
  expect(readdirSync(root).sort()).toEqual(['legal']);
  expect(readdirSync(join(root, 'legal'))).toEqual(['a.pdf']);
  expect((await get('/api/files/..%2f/a.pdf')).status).toBe(400);
});

test('upload writes the file into the department drive', async () => {
  const r = await upload('legal', 'new.txt', 'payload');
  expect(r.status).toBe(201);
  expect(await r.json()).toEqual({ ok: true, name: 'new.txt' });
  expect(readFileSync(join(root, 'legal', 'new.txt'), 'utf8')).toBe('payload');
});

test('upload creates the department directory when absent', async () => {
  expect((await upload('hr', 'p.txt')).status).toBe(201);
  expect(existsSync(join(root, 'hr', 'p.txt'))).toBe(true);
});

test('upload with a separator or .. in the filename is refused, nothing written', async () => {
  for (const bad of ['../evil.txt', 'a/b.txt', 'a\\b.txt', '..', '.']) {
    expect((await upload('legal', bad)).status).toBe(400);
  }
  expect(readdirSync(join(root, 'legal'))).toEqual(['a.pdf']);
  expect(readdirSync(root).sort()).toEqual(['legal']);
});

test('upload without a file field is a 400', async () => {
  const r = await app.request('/api/files?dept=legal', {
    method: 'POST', headers: { cookie: ownerCookie() }, body: new FormData(),
  });
  expect(r.status).toBe(400);
});

test('download returns the bytes as an attachment', async () => {
  const r = await get('/api/files/legal/a.pdf');
  expect(r.status).toBe(200);
  expect(r.headers.get('content-disposition')).toBe(`attachment; filename="a.pdf"; filename*=UTF-8''a.pdf`);
  expect(await r.text()).toBe('hello-bytes');
});

test('download refuses traversal and 404s a missing file', async () => {
  expect((await get('/api/files/legal/..%2f..%2fetc%2fpasswd')).status).toBe(400);
  expect((await get('/api/files/legal/..%5c..%5cx')).status).toBe(400);
  expect((await get('/api/files/nope/a.pdf')).status).toBe(400);
  expect((await get('/api/files/legal/missing.pdf')).status).toBe(404);
});

test('upload overwrites a same-name file', async () => {
  expect((await upload('legal', 'a.pdf', 'v2')).status).toBe(201);
  expect(readFileSync(join(root, 'legal', 'a.pdf'), 'utf8')).toBe('v2');
});

test('download of a non-ASCII (Vietnamese/Korean) name works, RFC 5987 header', async () => {
  for (const n of ['báo-cáo.pdf', '보고서.pdf']) {
    writeFileSync(join(root, 'legal', n), 'xin-chao');
    const r = await get(`/api/files/legal/${encodeURIComponent(n)}`);
    expect(r.status).toBe(200);
    expect(r.headers.get('content-disposition')).toContain(`filename*=UTF-8''${encodeURIComponent(n)}`);
    expect(await r.text()).toBe('xin-chao');
  }
});

test('symlinks are never followed: hidden from list, 404 on download, refused on upload', async () => {
  const outside = join(root, 'secret.txt');
  writeFileSync(outside, 'top-secret');
  symlinkSync(outside, join(root, 'legal', 'link.txt'));
  const rows = await (await get('/api/files?dept=legal')).json();
  expect(rows.map((x: { name: string }) => x.name)).toEqual(['a.pdf']);
  expect((await get('/api/files/legal/link.txt')).status).toBe(404);
  expect((await upload('legal', 'link.txt', 'pwned')).status).toBe(400);
  expect(readFileSync(outside, 'utf8')).toBe('top-secret');
});

test('an oversized upload is rejected with 413 and nothing written', async () => {
  const small = makeApp({ NUFI_DRIVES_DIR: root, DEPARTMENTS: 'legal', NUFI_MAX_UPLOAD_BYTES: '10' });
  const fd = new FormData();
  fd.set('file', new File(['x'.repeat(11)], 'big.bin'));
  const r = await small.request('/api/files?dept=legal', { method: 'POST', headers: { cookie: ownerCookie() }, body: fd });
  expect(r.status).toBe(413);
  expect(existsSync(join(root, 'legal', 'big.bin'))).toBe(false);
});

test('a symlinked department directory is refused on list, download and upload', async () => {
  const outside = mkdtempSync(join(tmpdir(), 'outside-'));
  try {
    writeFileSync(join(outside, 'passwd'), 'root:x');
    symlinkSync(outside, join(root, 'hr'));
    expect((await get('/api/files?dept=hr')).status).toBe(400);
    const d = await get('/api/files/hr/passwd');
    expect(d.status).toBe(400);
    expect(await d.text()).not.toContain('root:x');
    expect((await upload('hr', 'pwn.txt')).status).toBe(400);
    expect(readdirSync(outside)).toEqual(['passwd']);
  } finally {
    rmSync(outside, { recursive: true, force: true });
  }
});

// ---- Cycle 2: folders ----
const j = (method: string, path: string, body?: unknown) =>
  app.request(path, { method, headers: { cookie: ownerCookie(), 'content-type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
const seedSub = () => {
  mkdirSync(join(root, 'legal', 'sub'));
  writeFileSync(join(root, 'legal', 'sub', 'a.pdf'), 'sub-bytes');
};
const snapshot = () => JSON.stringify([readdirSync(root).sort(), readdirSync(join(root, 'legal')).sort()]);

test('lists a subfolder, access defaults public, dotfiles hidden', async () => {
  seedSub();
  writeFileSync(join(root, 'legal', '.nufi-access.json'), '{"version":1,"entries":{}}');
  writeFileSync(join(root, 'legal', 'sub', '.hidden'), 'x');
  const top = await (await get('/api/files?dept=legal')).json();
  expect(top.map((x: { name: string }) => x.name).sort()).toEqual(['a.pdf', 'sub']);
  expect(top.find((x: { name: string }) => x.name === 'sub').kind).toBe('dir');
  const rows = await (await get('/api/files?dept=legal&path=sub')).json();
  expect(rows).toHaveLength(1);
  expect(rows[0]).toMatchObject({ name: 'a.pdf', kind: 'file', access: 'public' });
  expect(await (await get('/api/files?dept=legal&path=nope')).json()).toEqual([]);
});

test('access is attached: own entry and inherited from a folder', async () => {
  seedSub();
  writeFileSync(join(root, 'legal', 'sub', 'b.txt'), 'b');
  writeFileSync(join(root, 'legal', '.nufi-access.json'), JSON.stringify({ version: 1, entries: { 'a.pdf': { access: 'private' }, sub: { access: 'private' }, 'sub/b.txt': { access: 'public' } } }));
  const top = await (await get('/api/files?dept=legal')).json();
  expect(top.find((x: { name: string }) => x.name === 'a.pdf').access).toBe('private');
  expect(top.find((x: { name: string }) => x.name === 'sub').access).toBe('private');
  const sub = await (await get('/api/files?dept=legal&path=sub')).json();
  expect(sub.find((x: { name: string }) => x.name === 'a.pdf').access).toBe('private'); // inherited
  expect(sub.find((x: { name: string }) => x.name === 'b.txt').access).toBe('public'); // own wins
});

test('upload into a subfolder (auto-mkdir) and download it by path', async () => {
  expect((await upload('legal', 'n.txt', 'deep', true, 'x/y')).status).toBe(201);
  expect(readFileSync(join(root, 'legal', 'x', 'y', 'n.txt'), 'utf8')).toBe('deep');
  seedSub();
  const r = await get('/api/files/legal/sub/a.pdf');
  expect(r.status).toBe(200);
  expect(await r.text()).toBe('sub-bytes');
});

test('mkdir creates a folder; duplicate is 409', async () => {
  expect((await j('POST', '/api/files/folder', { dept: 'legal', path: '', name: 'docs' })).status).toBe(201);
  expect(existsSync(join(root, 'legal', 'docs'))).toBe(true);
  expect((await j('POST', '/api/files/folder', { dept: 'legal', path: 'docs', name: 'inner' })).status).toBe(201);
  expect(existsSync(join(root, 'legal', 'docs', 'inner'))).toBe(true);
  expect((await j('POST', '/api/files/folder', { dept: 'legal', path: '', name: 'docs' })).status).toBe(409);
});

test('rename a file and a folder in place; existing target is refused', async () => {
  seedSub();
  expect((await j('POST', '/api/files/rename', { dept: 'legal', path: 'a.pdf', newName: 'b.pdf' })).status).toBe(200);
  expect(existsSync(join(root, 'legal', 'b.pdf'))).toBe(true);
  expect(existsSync(join(root, 'legal', 'a.pdf'))).toBe(false);
  expect((await j('POST', '/api/files/rename', { dept: 'legal', path: 'sub', newName: 'sub2' })).status).toBe(200);
  expect(readFileSync(join(root, 'legal', 'sub2', 'a.pdf'), 'utf8')).toBe('sub-bytes');
  expect((await j('POST', '/api/files/rename', { dept: 'legal', path: 'sub2', newName: 'b.pdf' })).status).toBe(409);
  expect((await j('POST', '/api/files/rename', { dept: 'legal', path: 'ghost', newName: 'z' })).status).toBe(404);
});

test('delete removes a file, and a folder with contents plus its access entries', async () => {
  seedSub();
  writeFileSync(join(root, 'legal', '.nufi-access.json'), JSON.stringify({ version: 1, entries: { sub: { access: 'private' }, 'sub/a.pdf': { access: 'public' }, 'a.pdf': { access: 'private' } } }));
  expect((await j('DELETE', '/api/files?dept=legal&path=sub')).status).toBe(200);
  expect(existsSync(join(root, 'legal', 'sub'))).toBe(false);
  const acc = JSON.parse(readFileSync(join(root, 'legal', '.nufi-access.json'), 'utf8'));
  expect(Object.keys(acc.entries)).toEqual(['a.pdf']);
  expect((await j('DELETE', '/api/files?dept=legal&path=a.pdf')).status).toBe(200);
  expect(existsSync(join(root, 'legal', 'a.pdf'))).toBe(false);
  expect((await j('DELETE', '/api/files?dept=legal&path=a.pdf')).status).toBe(404);
  expect((await j('DELETE', '/api/files?dept=legal')).status).toBe(400); // never the dept root
  expect(existsSync(join(root, 'legal'))).toBe(true);
});

test('traversal in path / name / newName is 400 and changes nothing', async () => {
  seedSub();
  const before = snapshot();
  const bad = ['../x', 'a/../../etc', '%2e%2e%2fx', '..', 'sub/..', '.nufi-access.json', 'sub//a.pdf', 'a\\..\\b'];
  for (const p of bad) {
    expect((await get(`/api/files?dept=legal&path=${p}`)).status).toBe(400);
    expect((await upload('legal', 'z.txt', 'd', true, p)).status).toBe(400);
    expect((await j('DELETE', `/api/files?dept=legal&path=${p}`)).status).toBe(400);
    const decoded = decodeURIComponent(p);
    expect((await j('POST', '/api/files/folder', { dept: 'legal', path: decoded, name: 'n' })).status).toBe(400);
    expect((await j('POST', '/api/files/rename', { dept: 'legal', path: decoded, newName: 'n' })).status).toBe(400);
  }
  for (const n of ['a/b', '../x', '..', '.', '', '.nufi-access.json', 'a\\b']) {
    expect((await j('POST', '/api/files/folder', { dept: 'legal', path: '', name: n })).status).toBe(400);
    expect((await j('POST', '/api/files/rename', { dept: 'legal', path: 'a.pdf', newName: n })).status).toBe(400);
  }
  expect((await j('POST', '/api/files/folder', { dept: 'legal', path: 5, name: 'n' })).status).toBe(400);
  expect((await j('POST', '/api/files/folder', { dept: 'nope', path: '', name: 'n' })).status).toBe(400);
  for (const u of ['/api/files/legal/..%2f..%2fetc', '/api/files/legal/sub/%2e%2e/%2e%2e/x', '/api/files/legal/%2e%2e%2fx']) {
    expect((await get(u)).status).toBe(400);
  }
  expect(snapshot()).toBe(before);
  expect(readdirSync(join(root, 'legal', 'sub'))).toEqual(['a.pdf']);
});

test('a dot-leading upload name is refused; the access file is never listed or downloadable', async () => {
  writeFileSync(join(root, 'legal', '.nufi-access.json'), '{"version":1,"entries":{}}');
  expect((await upload('legal', '.nufi-access.json', '{"x":1}')).status).toBe(400);
  expect((await upload('legal', '.secret', 'x', true, '')).status).toBe(400);
  expect(readFileSync(join(root, 'legal', '.nufi-access.json'), 'utf8')).toBe('{"version":1,"entries":{}}');
  const names = (await (await get('/api/files?dept=legal')).json()).map((x: { name: string }) => x.name);
  expect(names).not.toContain('.nufi-access.json');
  expect((await get('/api/files/legal/.nufi-access.json')).status).toBe(400);
});

test('a symlinked intermediate directory is refused on every endpoint', async () => {
  const outside = mkdtempSync(join(tmpdir(), 'outside-'));
  try {
    writeFileSync(join(outside, 'passwd'), 'root:x');
    symlinkSync(outside, join(root, 'legal', 'lnk'));
    expect((await get('/api/files?dept=legal&path=lnk')).status).toBe(400);
    expect((await get('/api/files?dept=legal&path=lnk/deeper')).status).toBe(400);
    expect((await upload('legal', 'pwn.txt', 'd', true, 'lnk')).status).toBe(400);
    expect((await upload('legal', 'pwn.txt', 'd', true, 'lnk/deeper')).status).toBe(400);
    expect((await get('/api/files/legal/lnk/passwd')).status).toBe(400);
    expect((await j('POST', '/api/files/folder', { dept: 'legal', path: 'lnk', name: 'n' })).status).toBe(400);
    expect((await j('POST', '/api/files/rename', { dept: 'legal', path: 'lnk/passwd', newName: 'n' })).status).toBe(400);
    expect((await j('POST', '/api/files/rename', { dept: 'legal', path: 'lnk', newName: 'n' })).status).toBe(400);
    expect((await j('DELETE', '/api/files?dept=legal&path=lnk/passwd')).status).toBe(400);
    expect((await j('DELETE', '/api/files?dept=legal&path=lnk')).status).toBe(400);
    expect(readdirSync(outside)).toEqual(['passwd']);
    expect(readFileSync(join(outside, 'passwd'), 'utf8')).toBe('root:x');
  } finally {
    rmSync(outside, { recursive: true, force: true });
  }
});

test('renaming a Private file or a folder with a Private child keeps them private', async () => {
  seedSub();
  writeFileSync(join(root, 'legal', '.nufi-access.json'), JSON.stringify({ version: 1, entries: { 'a.pdf': { access: 'private' }, 'sub/a.pdf': { access: 'private' } } }));
  expect((await j('POST', '/api/files/rename', { dept: 'legal', path: 'a.pdf', newName: 'c.pdf' })).status).toBe(200);
  const top = await (await get('/api/files?dept=legal')).json();
  expect(top.find((x: { name: string }) => x.name === 'c.pdf').access).toBe('private');
  expect((await j('POST', '/api/files/rename', { dept: 'legal', path: 'sub', newName: 'moved' })).status).toBe(200);
  const rows = await (await get('/api/files?dept=legal&path=moved')).json();
  expect(rows[0]).toMatchObject({ name: 'a.pdf', access: 'private' });
  const acc = JSON.parse(readFileSync(join(root, 'legal', '.nufi-access.json'), 'utf8'));
  expect(Object.keys(acc.entries).sort()).toEqual(['c.pdf', 'moved/a.pdf']);
});

test('a folder own Private entry moves with it; a rename that cannot happen leaves the old key', async () => {
  seedSub();
  writeFileSync(join(root, 'legal', '.nufi-access.json'), JSON.stringify({ version: 1, entries: { sub: { access: 'private' } } }));
  expect((await j('POST', '/api/files/rename', { dept: 'legal', path: 'sub', newName: 'a.pdf' })).status).toBe(409);
  let acc = JSON.parse(readFileSync(join(root, 'legal', '.nufi-access.json'), 'utf8'));
  expect(Object.keys(acc.entries)).toEqual(['sub']);
  expect((await j('POST', '/api/files/rename', { dept: 'legal', path: 'sub', newName: 'sub2' })).status).toBe(200);
  acc = JSON.parse(readFileSync(join(root, 'legal', '.nufi-access.json'), 'utf8'));
  expect(Object.keys(acc.entries)).toEqual(['sub2']);
  const top = await (await get('/api/files?dept=legal')).json();
  expect(top.find((x: { name: string }) => x.name === 'sub2').access).toBe('private');
});

const setAcc = (body: unknown) => j('PUT', '/api/files/access', body);

test('set access: file private shows in list; folder private is inherited by children', async () => {
  seedSub();
  expect((await setAcc({ dept: 'legal', path: 'a.pdf', access: 'private' })).status).toBe(200);
  const top = await (await get('/api/files?dept=legal')).json();
  expect(top.find((x: { name: string }) => x.name === 'a.pdf').access).toBe('private');
  expect((await setAcc({ dept: 'legal', path: 'sub', access: 'private' })).status).toBe(200);
  const rows = await (await get('/api/files?dept=legal&path=sub')).json();
  expect(rows[0]).toMatchObject({ name: 'a.pdf', access: 'private' });
});

test('set access rejects bad input', async () => {
  expect((await setAcc({ dept: 'legal', path: 'a.pdf', access: 'secret' })).status).toBe(400);
  expect((await setAcc({ dept: 'legal', path: 'nope.pdf', access: 'private' })).status).toBe(404);
  expect((await setAcc({ dept: 'legal', path: '.nufi-access.json', access: 'private' })).status).toBe(400);
  expect((await setAcc({ dept: 'legal', path: 'sub/.hidden', access: 'private' })).status).toBe(400);
  expect((await setAcc({ dept: 'legal', path: '', access: 'private' })).status).toBe(400);
  expect((await setAcc({ dept: 'nope', path: 'a.pdf', access: 'private' })).status).toBe(400);
});

test('set access requires owner auth', async () => {
  const r = await app.request('/api/files/access', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ dept: 'legal', path: 'a.pdf', access: 'private' }) });
  expect(r.status).toBe(401);
});

test('deleting a private item leaves no stale access entry', async () => {
  await setAcc({ dept: 'legal', path: 'a.pdf', access: 'private' });
  expect((await j('DELETE', '/api/files?dept=legal&path=a.pdf')).status).toBe(200);
  const acc = JSON.parse(readFileSync(join(root, 'legal', '.nufi-access.json'), 'utf8'));
  expect(Object.keys(acc.entries)).toEqual([]);
});

test('a corrupt access file fails closed: list errors, access change is refused and the file is untouched', async () => {
  const f = join(root, 'legal', '.nufi-access.json');
  writeFileSync(f, '{not json');
  const r = await get('/api/files?dept=legal');
  expect(r.status).toBe(409);
  expect((await r.json()).error).toContain('corrupt');
  const put = await app.request('/api/files/access', {
    method: 'PUT',
    headers: { cookie: ownerCookie(), 'content-type': 'application/json' },
    body: JSON.stringify({ dept: 'legal', path: 'a.pdf', access: 'private' }),
  });
  expect(put.status).toBe(409);
  expect(readFileSync(f, 'utf8')).toBe('{not json');
});
