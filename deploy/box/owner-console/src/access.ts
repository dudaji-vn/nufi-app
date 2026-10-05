import { randomUUID } from 'node:crypto';
import { readFile, rename, writeFile } from 'node:fs/promises';

export type Access = 'public' | 'private';
export type AccessFile = { version: 1; entries: Record<string, { access: Access }> };

export function accessPath(driveDir: string): string {
  return `${driveDir}/.nufi-access.json`;
}

const empty = (): AccessFile => ({ version: 1, entries: Object.create(null) });

// Own, well-formed entry or undefined (prototype keys and bad values are "no entry").
function lookup(a: AccessFile, k: string): Access | undefined {
  if (!Object.hasOwn(a.entries, k)) return undefined;
  const v = a.entries[k]?.access;
  return v === 'public' || v === 'private' ? v : undefined;
}

export async function readAccess(driveDir: string): Promise<AccessFile> {
  try {
    const parsed = JSON.parse(await readFile(accessPath(driveDir), 'utf8'));
    if (
      parsed &&
      typeof parsed === 'object' &&
      !Array.isArray(parsed) &&
      parsed.entries &&
      typeof parsed.entries === 'object' &&
      !Array.isArray(parsed.entries)
    ) {
      const entries: AccessFile['entries'] = Object.create(null);
      for (const k of Object.keys(parsed.entries)) {
        const v = parsed.entries[k]?.access;
        if (v === 'public' || v === 'private') entries[k] = { access: v };
      }
      return { version: 1, entries };
    }
  } catch {
    // absent or corrupt: fall through to the empty default
  }
  return empty();
}

async function write(driveDir: string, a: AccessFile): Promise<void> {
  const path = accessPath(driveDir);
  const tmp = `${path}.${process.pid}.${randomUUID()}.tmp`;
  await writeFile(tmp, JSON.stringify(a, null, 2), { mode: 0o600 });
  await rename(tmp, path);
}

// Serializes every write so concurrent read-modify-writes never drop entries.
let queue: Promise<unknown> = Promise.resolve();
function enqueue<T>(fn: () => Promise<T>): Promise<T> {
  const run = queue.then(fn);
  queue = run.catch(() => undefined); // a failure must not poison later mutations
  return run;
}

export function writeAccess(driveDir: string, a: AccessFile): Promise<void> {
  return enqueue(() => write(driveDir, a));
}

export function effectiveAccess(a: AccessFile, relPath: string): Access {
  const own = lookup(a, relPath);
  if (own) return own;
  let p = relPath;
  for (;;) {
    const i = p.lastIndexOf('/');
    if (i < 0) return 'public';
    p = p.slice(0, i);
    const e = lookup(a, p);
    if (e) return e;
  }
}

export function setEntry(driveDir: string, relPath: string, access: Access): Promise<void> {
  return enqueue(async () => {
    const a = await readAccess(driveDir);
    a.entries[relPath] = { access };
    await write(driveDir, a);
  });
}

export function removeSubtree(driveDir: string, relPath: string): Promise<void> {
  return enqueue(async () => {
    const a = await readAccess(driveDir);
    for (const k of Object.keys(a.entries)) {
      if (k === relPath || k.startsWith(`${relPath}/`)) delete a.entries[k];
    }
    await write(driveDir, a);
  });
}
