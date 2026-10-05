import { randomUUID } from 'node:crypto';
import { readFile, rename, writeFile } from 'node:fs/promises';

export type Access = 'public' | 'private';
export type AccessFile = { version: 1; entries: Record<string, { access: Access }> };

export function accessPath(driveDir: string): string {
  return `${driveDir}/.nufi-access.json`;
}

const empty = (): AccessFile => ({ version: 1, entries: {} });

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
      return { version: 1, entries: parsed.entries };
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
  const own = a.entries[relPath];
  if (own) return own.access;
  let p = relPath;
  for (;;) {
    const i = p.lastIndexOf('/');
    if (i < 0) return 'public';
    p = p.slice(0, i);
    const e = a.entries[p];
    if (e) return e.access;
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
