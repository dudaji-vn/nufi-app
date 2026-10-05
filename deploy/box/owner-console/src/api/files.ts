import { lstat, mkdir, readdir, rename, rm, writeFile } from 'node:fs/promises';
import { dirname, resolve, sep } from 'node:path';
import { Hono } from 'hono';
import { CorruptAccessError, copySubtree, effectiveAccess, readAccess, removeSubtree, setEntry } from '../access';
import { boxInfo } from '../boxinfo';

type Env = Record<string, string | undefined>;

class Bad extends Error {}
class Conflict extends Error {}
class Missing extends Error {}

const DEFAULT_MAX_UPLOAD = 100 * 1024 * 1024; // 100 MB
class TooLarge extends Error {}

// lstat, never stat: a symlink planted in a shared drive must not be followed.
// null when absent; otherwise the entry's own stats (isSymbolicLink() is honest).
const entry = (p: string) => lstat(p).catch(() => null);

// Every path is validated BEFORE any filesystem call, then defended again after
// resolve(). dept must be an exact member of the box's department set; name must
// be a single plain path segment.
async function deptDir(env: Env, dept: string | undefined): Promise<string> {
  if (!dept || !boxInfo(env).departments.includes(dept)) throw new Bad('unknown department');
  const root = resolve(env.NUFI_DRIVES_DIR ?? '/drives');
  const dir = resolve(root, dept);
  if (!dir.startsWith(root + sep)) throw new Bad('invalid department');
  // resolve() is lexical: a symlinked dept dir would still pass the prefix check.
  if ((await entry(dir))?.isSymbolicLink()) throw new Bad('invalid department');
  return dir;
}

function safeName(name: unknown): string {
  // eslint-disable-next-line no-control-regex
  // Dot-leading names are reserved (.nufi-access.json) and never listed, so never writable either.
  if (typeof name !== 'string' || !name || name.startsWith('.') || /[/\\\u0000-\u001f]/.test(name) || name === '.' || name.split(/[/\\]/).includes('..') || name.includes('..')) {
    throw new Bad('invalid file name');
  }
  return name;
}

function filePath(dir: string, name: string): string {
  const p = resolve(dir, name);
  if (!p.startsWith(dir + sep)) throw new Bad('invalid file name');
  return p;
}

// Resolves a '/'-separated path relative to dir. Every segment goes through
// safeName, the joined path is rechecked against dir, and a symlinked ancestor
// directory is refused. The final segment's own symlink-ness is the caller's call.
async function resolveRel(dir: string, rel: unknown): Promise<string> {
  if (rel === undefined || rel === null || rel === '') return dir;
  if (typeof rel !== 'string') throw new Bad('invalid path');
  let cur = dir;
  const segs = rel.split('/');
  for (let i = 0; i < segs.length; i++) {
    cur = filePath(cur, safeName(segs[i]));
    if (i < segs.length - 1 && (await entry(cur))?.isSymbolicLink()) throw new Bad('invalid path');
  }
  return cur;
}

const relOf = (path: string, name: string) => (path ? `${path}/${name}` : name);

const attachment = (name: string) =>
  `attachment; filename="${name.replace(/[^\x20-\x7e]|["\\%]/g, '_')}"; filename*=UTF-8''${encodeURIComponent(name).replace(/['()*]/g, (ch) => `%${ch.charCodeAt(0).toString(16).toUpperCase()}`)}`;

// Mounted behind the /api/* owner-auth middleware.
export function filesRoutes(env: Env): Hono {
  const MAX_UPLOAD = Number(env.NUFI_MAX_UPLOAD_BYTES) || DEFAULT_MAX_UPLOAD; // env override exists for tests
  const r = new Hono();

  const fail = (c: import('hono').Context, e: unknown, fallback: string) => {
    if (e instanceof TooLarge) return c.json({ error: 'file too large (max 100 MB)' }, 413);
    if (e instanceof Bad) return c.json({ error: e.message }, 400);
    if (e instanceof Missing) return c.json({ error: 'not found' }, 404);
    if (e instanceof CorruptAccessError)
      return c.json({ error: 'the accessibility file for this department is corrupt and must be fixed' }, 409);
    if (e instanceof Conflict) return c.json({ error: e.message }, 409);
    return c.json({ error: fallback }, 500);
  };
  const jsonBody = async (c: import('hono').Context): Promise<Record<string, unknown>> => {
    const b = await c.req.json().catch(() => null);
    return b && typeof b === 'object' && !Array.isArray(b) ? (b as Record<string, unknown>) : {};
  };

  r.get('/files', async (c) => {
    try {
      const root = await deptDir(env, c.req.query('dept'));
      const path = c.req.query('path') ?? '';
      const dir = await resolveRel(root, path);
      if ((await entry(dir))?.isSymbolicLink()) throw new Bad('invalid path');
      let names: string[];
      try {
        names = await readdir(dir);
      } catch (e) {
        const code = (e as NodeJS.ErrnoException).code;
        if (code === 'ENOENT' || code === 'ENOTDIR') return c.json([]);
        throw e;
      }
      const access = await readAccess(root);
      const rows = await Promise.all(
        names
          .filter((name) => !name.startsWith('.'))
          .map(async (name) => {
            const s = await entry(filePath(dir, name));
            if (!s || s.isSymbolicLink()) return null;
            return {
              name,
              kind: s.isDirectory() ? ('dir' as const) : ('file' as const),
              size: s.size,
              uploadedAt: s.birthtime.toISOString(),
              modifiedAt: s.mtime.toISOString(),
              access: effectiveAccess(access, relOf(path, name)),
            };
          }),
      );
      return c.json(rows.filter((x) => x !== null));
    } catch (e) {
      return fail(c, e, 'could not list files');
    }
  });

  r.post('/files', async (c) => {
    try {
      const root = await deptDir(env, c.req.query('dept'));
      const dir = await resolveRel(root, c.req.query('path') ?? '');
      const declared = Number(c.req.header('content-length') ?? 0);
      if (declared > MAX_UPLOAD + 1024 * 1024) throw new TooLarge();
      const body = await c.req.parseBody().catch(() => ({}) as Record<string, unknown>);
      const file = body.file;
      if (!(file instanceof File)) throw new Bad('missing file');
      if (file.size > MAX_UPLOAD) throw new TooLarge();
      const name = safeName(file.name);
      const path = filePath(dir, name);
      // Overwrites a same-name file; refuses to write through a symlink.
      if ((await entry(dir))?.isSymbolicLink()) throw new Bad('invalid path');
      if ((await entry(path))?.isSymbolicLink()) throw new Bad('refusing to write through a symlink');
      await mkdir(dir, { recursive: true });
      await writeFile(path, Buffer.from(await file.arrayBuffer()));
      return c.json({ ok: true, name }, 201);
    } catch (e) {
      return fail(c, e, 'upload failed');
    }
  });

  r.get('/files/:dept/*', async (c) => {
    try {
      const root = await deptDir(env, c.req.param('dept'));
      // Wildcard remainder, percent-decoded per segment; any decoded '/' is then split and re-validated by resolveRel.
      const dept = c.req.param('dept');
      const raw = c.req.path.slice(c.req.path.indexOf('/files/') + '/files/'.length);
      const rest = raw.startsWith(`${encodeURIComponent(dept)}/`) ? raw.slice(encodeURIComponent(dept).length + 1) : '';
      let rel: string;
      try {
        rel = rest.split('/').map(decodeURIComponent).join('/');
      } catch {
        throw new Bad('invalid path');
      }
      if (!rel) throw new Bad('invalid path');
      const path = await resolveRel(root, rel);
      const s = await entry(path);
      if (!s || s.isSymbolicLink() || !s.isFile()) return c.json({ error: 'not found' }, 404);
      const name = rel.split('/').at(-1) as string;
      return new Response(Bun.file(path).stream(), {
        headers: {
          'content-type': 'application/octet-stream',
          'content-length': String(s.size),
          // RFC 5987: an ASCII fallback for legacy clients plus the real UTF-8 name.
          'content-disposition': attachment(name),
        },
      });
    } catch (e) {
      return fail(c, e, 'download failed');
    }
  });

  r.post('/files/folder', async (c) => {
    try {
      const b = await jsonBody(c);
      const root = await deptDir(env, b.dept as string | undefined);
      const parent = await resolveRel(root, b.path ?? '');
      if ((await entry(parent))?.isSymbolicLink()) throw new Bad('invalid path');
      const target = filePath(parent, safeName(b.name));
      if (await entry(target)) throw new Conflict('already exists');
      await mkdir(target, { recursive: true });
      return c.json({ ok: true, name: b.name }, 201);
    } catch (e) {
      return fail(c, e, 'could not create folder');
    }
  });

  r.post('/files/rename', async (c) => {
    try {
      const b = await jsonBody(c);
      const root = await deptDir(env, b.dept as string | undefined);
      if (typeof b.path !== 'string' || !b.path) throw new Bad('invalid path');
      const from = await resolveRel(root, b.path);
      const to = filePath(dirname(from), safeName(b.newName));
      const s = await entry(from);
      if (!s) throw new Missing();
      if (s.isSymbolicLink()) throw new Bad('invalid path');
      if (await entry(to)) throw new Conflict('already exists');
      // Fail closed: protect the new path first, rename, then drop the old keys. If the
      // rename throws, the old keys still guard the item and the new ones are rolled back.
      const oldRel = b.path;
      const newRel = relOf(oldRel.includes('/') ? oldRel.slice(0, oldRel.lastIndexOf('/')) : '', b.newName as string);
      await copySubtree(root, oldRel, newRel);
      try {
        await rename(from, to);
      } catch (e) {
        await removeSubtree(root, newRel).catch(() => undefined);
        throw e;
      }
      await removeSubtree(root, oldRel);
      return c.json({ ok: true, name: b.newName });
    } catch (e) {
      return fail(c, e, 'rename failed');
    }
  });

  r.put('/files/access', async (c) => {
    try {
      const b = await jsonBody(c);
      const root = await deptDir(env, b.dept as string | undefined);
      if (b.access !== 'public' && b.access !== 'private') throw new Bad('invalid access');
      if (typeof b.path !== 'string' || !b.path) throw new Bad('invalid path'); // per file/folder, never the dept root
      const target = await resolveRel(root, b.path);
      const s = await entry(target);
      if (!s) throw new Missing();
      if (s.isSymbolicLink()) throw new Bad('invalid path');
      await setEntry(root, b.path, b.access);
      return c.json({ ok: true });
    } catch (e) {
      return fail(c, e, 'could not set access');
    }
  });

  r.delete('/files', async (c) => {
    try {
      const root = await deptDir(env, c.req.query('dept'));
      const rel = c.req.query('path') ?? '';
      if (!rel) throw new Bad('invalid path'); // never the department root
      const target = await resolveRel(root, rel);
      const s = await entry(target);
      if (!s) throw new Missing();
      if (s.isSymbolicLink()) throw new Bad('invalid path');
      await rm(target, { recursive: true, force: true });
      await removeSubtree(root, rel);
      return c.json({ ok: true });
    } catch (e) {
      return fail(c, e, 'delete failed');
    }
  });

  return r;
}
