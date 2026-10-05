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
const upload = (dept: string, filename: string, body = 'data', auth = true) => {
  const fd = new FormData();
  fd.set('file', new File([body], filename));
  return app.request(`/api/files?dept=${dept}`, {
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
