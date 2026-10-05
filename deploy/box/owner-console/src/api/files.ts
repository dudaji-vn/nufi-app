import { lstat, mkdir, readdir, writeFile } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { Hono } from 'hono';
import { boxInfo } from '../boxinfo';

type Env = Record<string, string | undefined>;

class Bad extends Error {}

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
  if (typeof name !== 'string' || !name || /[/\\\u0000-\u001f]/.test(name) || name === '.' || name.split(/[/\\]/).includes('..') || name.includes('..')) {
    throw new Bad('invalid file name');
  }
  return name;
}

function filePath(dir: string, name: string): string {
  const p = resolve(dir, name);
  if (!p.startsWith(dir + sep)) throw new Bad('invalid file name');
  return p;
}

// Mounted behind the /api/* owner-auth middleware.
export function filesRoutes(env: Env): Hono {
  const MAX_UPLOAD = Number(env.NUFI_MAX_UPLOAD_BYTES) || DEFAULT_MAX_UPLOAD; // env override exists for tests
  const r = new Hono();

  r.get('/files', async (c) => {
    try {
      const dir = await deptDir(env, c.req.query('dept'));
      let names: string[];
      try {
        names = await readdir(dir);
      } catch (e) {
        if ((e as NodeJS.ErrnoException).code === 'ENOENT') return c.json([]);
        throw e;
      }
      const rows = await Promise.all(
        names.map(async (name) => {
          const s = await entry(filePath(dir, name));
          if (!s || s.isSymbolicLink()) return null;
          return {
            name,
            kind: s.isDirectory() ? ('dir' as const) : ('file' as const),
            size: s.size,
            uploadedAt: s.birthtime.toISOString(),
            modifiedAt: s.mtime.toISOString(),
          };
        }),
      );
      return c.json(rows.filter((x) => x !== null));
    } catch (e) {
      if (e instanceof Bad) return c.json({ error: e.message }, 400);
      return c.json({ error: 'could not list files' }, 500);
    }
  });

  r.post('/files', async (c) => {
    try {
      const dir = await deptDir(env, c.req.query('dept'));
      const declared = Number(c.req.header('content-length') ?? 0);
      if (declared > MAX_UPLOAD + 1024 * 1024) throw new TooLarge();
      const body = await c.req.parseBody().catch(() => ({}) as Record<string, unknown>);
      const file = body.file;
      if (!(file instanceof File)) throw new Bad('missing file');
      if (file.size > MAX_UPLOAD) throw new TooLarge();
      const name = safeName(file.name);
      const path = filePath(dir, name);
      // Overwrites a same-name file; refuses to write through a symlink.
      if ((await entry(path))?.isSymbolicLink()) throw new Bad('refusing to write through a symlink');
      await mkdir(dir, { recursive: true });
      await writeFile(path, Buffer.from(await file.arrayBuffer()));
      return c.json({ ok: true, name }, 201);
    } catch (e) {
      if (e instanceof TooLarge) return c.json({ error: 'file too large (max 100 MB)' }, 413);
      if (e instanceof Bad) return c.json({ error: e.message }, 400);
      return c.json({ error: 'upload failed' }, 500);
    }
  });

  r.get('/files/:dept/:name', async (c) => {
    try {
      const dir = await deptDir(env, c.req.param('dept'));
      const name = safeName(c.req.param('name'));
      const path = filePath(dir, name);
      const s = await entry(path);
      if (!s || s.isSymbolicLink() || !s.isFile()) return c.json({ error: 'not found' }, 404);
      return new Response(Bun.file(path).stream(), {
        headers: {
          'content-type': 'application/octet-stream',
          'content-length': String(s.size),
          // RFC 5987: an ASCII fallback for legacy clients plus the real UTF-8 name.
          'content-disposition':
            `attachment; filename="${name.replace(/[^\x20-\x7e]|["\\%]/g, '_')}"; filename*=UTF-8''${encodeURIComponent(name).replace(/['()*]/g, (ch) => `%${ch.charCodeAt(0).toString(16).toUpperCase()}`)}`,
        },
      });
    } catch (e) {
      if (e instanceof Bad) return c.json({ error: e.message }, 400);
      return c.json({ error: 'download failed' }, 500);
    }
  });

  return r;
}
