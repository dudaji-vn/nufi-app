import { afterEach, beforeEach, describe, expect, test } from 'bun:test';
import { mkdtemp, readdir, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  accessPath,
  effectiveAccess,
  readAccess,
  removeSubtree,
  setEntry,
  type AccessFile,
} from '../src/access';

let dir: string;
beforeEach(async () => {
  dir = await mkdtemp(join(tmpdir(), 'access-'));
});
afterEach(async () => {
  await rm(dir, { recursive: true, force: true });
});

describe('effectiveAccess', () => {
  const a: AccessFile = {
    version: 1,
    entries: {
      a: { access: 'private' },
      'a/b': { access: 'public' },
      'a/own.pdf': { access: 'public' },
    },
  };
  test('own entry wins', () => expect(effectiveAccess(a, 'a/own.pdf')).toBe('public'));
  test('deeper ancestor wins over shallower', () =>
    expect(effectiveAccess(a, 'a/b/c.pdf')).toBe('public'));
  test('shallower ancestor applies', () => expect(effectiveAccess(a, 'a/z/c.pdf')).toBe('private'));
  test('prototype-named paths with no entry are public', () => {
    const e: AccessFile = { version: 1, entries: {} };
    for (const n of ['constructor', '__proto__', 'toString', 'valueOf', 'a/constructor'])
      expect(effectiveAccess(e, n)).toBe('public');
  });
  test('folder named constructor does not poison children', () => {
    const e: AccessFile = { version: 1, entries: {} };
    expect(effectiveAccess(e, 'constructor/x.pdf')).toBe('public');
    expect(effectiveAccess(e, '__proto__/x.pdf')).toBe('public');
  });
  test('invalid access value is ignored', () => {
    const e = { version: 1, entries: { a: { access: 'private' }, 'a/b': { access: 'bogus' } } } as unknown as AccessFile;
    expect(effectiveAccess(e, 'a/b')).toBe('private');
    expect(effectiveAccess(e, 'a/b/c')).toBe('private');
  });
  test('no entry is public', () => expect(effectiveAccess(a, 'q/r.pdf')).toBe('public'));
});

describe('persistence', () => {
  test('path', () => expect(accessPath('/x')).toBe('/x/.nufi-access.json'));
  test('absent file gives empty default', async () => {
    expect(await readAccess(dir)).toEqual({ version: 1, entries: {} });
  });
  test('corrupt file gives empty default', async () => {
    await writeFile(accessPath(dir), '{not json');
    expect(await readAccess(dir)).toEqual({ version: 1, entries: {} });
    await writeFile(accessPath(dir), '[1,2]');
    expect(await readAccess(dir)).toEqual({ version: 1, entries: {} });
    await writeFile(accessPath(dir), '"x"');
    expect(await readAccess(dir)).toEqual({ version: 1, entries: {} });
  });
  test('setEntry round-trips and keeps others', async () => {
    await setEntry(dir, 'a/b.pdf', 'private');
    await setEntry(dir, 'c', 'public');
    expect((await readAccess(dir)).entries).toEqual({
      'a/b.pdf': { access: 'private' },
      c: { access: 'public' },
    });
  });
  test('removeSubtree drops descendants but not siblings with shared prefix', async () => {
    for (const p of ['a', 'a/x', 'a/y/z', 'ab']) await setEntry(dir, p, 'private');
    await removeSubtree(dir, 'a');
    expect(Object.keys((await readAccess(dir)).entries)).toEqual(['ab']);
  });
  test('atomic write leaves no tmp file', async () => {
    await setEntry(dir, 'a', 'private');
    expect(await readdir(dir)).toEqual(['.nufi-access.json']);
  });
  test('concurrent setEntry calls do not drop entries', async () => {
    await Promise.all(Array.from({ length: 20 }, (_, i) => setEntry(dir, `f${i}`, 'private')));
    expect(Object.keys((await readAccess(dir)).entries).length).toBe(20);
  });
  test('empty file, null, and non-object entries give empty default', async () => {
    for (const body of ['', 'null', '{"version":1,"entries":5}', '{"version":1,"entries":[]}', '{"version":1}']) {
      await writeFile(accessPath(dir), body);
      expect(await readAccess(dir)).toEqual({ version: 1, entries: {} });
    }
  });
  test('invalid entries are dropped on read', async () => {
    await writeFile(accessPath(dir), JSON.stringify({ version: 1, entries: { a: { access: 'bogus' }, b: { access: 'private' } } }));
    expect(Object.keys((await readAccess(dir)).entries)).toEqual(['b']);
  });
  test('setEntry is safe for __proto__ and constructor', async () => {
    await setEntry(dir, '__proto__', 'private');
    await setEntry(dir, 'constructor', 'private');
    const a = await readAccess(dir);
    expect(effectiveAccess(a, '__proto__/x')).toBe('private');
    expect(effectiveAccess(a, 'constructor')).toBe('private');
    expect(effectiveAccess(a, 'toString')).toBe('public');
  });
  test('file mode is 0600', async () => {
    await setEntry(dir, 'a', 'private');
    expect((await stat(accessPath(dir))).mode & 0o777).toBe(0o600);
  });
  test('a failed op does not poison the next', async () => {
    await expect(setEntry(join(dir, 'missing'), 'a', 'private')).rejects.toThrow();
    await setEntry(dir, 'b', 'private');
    expect((await readAccess(dir)).entries.b).toEqual({ access: 'private' });
  });
  test('removeSubtree keeps abc/x', async () => {
    for (const p of ['a', 'abc/x', 'ab']) await setEntry(dir, p, 'private');
    await removeSubtree(dir, 'a');
    expect(Object.keys((await readAccess(dir)).entries).sort()).toEqual(['ab', 'abc/x']);
  });
});
