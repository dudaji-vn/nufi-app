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

export class CorruptAccessError extends Error {
  constructor(driveDir: string, cause?: unknown) {
    super(`accessibility file for ${driveDir} is corrupt`, { cause });
    this.name = 'CorruptAccessError';
  }
}

// Absent file -> empty (legitimately all-public). Present but unreadable/unparseable -> throws,
// so no caller can treat a corrupt file as "everything public" or overwrite it.
export async function readAccess(driveDir: string): Promise<AccessFile> {
  let text: string;
  try {
    text = await readFile(accessPath(driveDir), 'utf8');
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === 'ENOENT') return empty();
    throw new CorruptAccessError(driveDir, e);
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    throw new CorruptAccessError(driveDir, e);
  }
  const p = parsed as { entries?: unknown } | null;
  if (
    !p ||
    typeof p !== 'object' ||
    Array.isArray(p) ||
    !p.entries ||
    typeof p.entries !== 'object' ||
    Array.isArray(p.entries)
  ) {
    throw new CorruptAccessError(driveDir);
  }
  const src = p.entries as Record<string, { access?: unknown } | null>;
  const entries: AccessFile['entries'] = Object.create(null);
  for (const k of Object.keys(src)) {
    const v = src[k]?.access;
    if (v === 'public' || v === 'private') entries[k] = { access: v };
  }
  return { version: 1, entries };
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

function rekey(a: AccessFile, from: string, to: string, keepOld: boolean): void {
  for (const k of Object.keys(a.entries)) {
    if (k !== from && !k.startsWith(`${from}/`)) continue;
    const nk = to + k.slice(from.length);
    a.entries[nk] = a.entries[k] as { access: Access };
    if (!keepOld) delete a.entries[k];
  }
}

// Re-keys `from` and everything under it to `to` (from/x/y -> to/x/y), atomically.
export function moveSubtree(driveDir: string, from: string, to: string): Promise<void> {
  return enqueue(async () => {
    const a = await readAccess(driveDir);
    rekey(a, from, to, false);
    await write(driveDir, a);
  });
}

// Like moveSubtree but keeps the old keys: lets a caller protect the new path first,
// do the filesystem rename, then drop the old keys (a failure never exposes a Private item).
export function copySubtree(driveDir: string, from: string, to: string): Promise<void> {
  return enqueue(async () => {
    const a = await readAccess(driveDir);
    rekey(a, from, to, true);
    await write(driveDir, a);
  });
}
