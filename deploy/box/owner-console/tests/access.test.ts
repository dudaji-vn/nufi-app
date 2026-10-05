import { afterEach, beforeEach, describe, expect, test } from 'bun:test';
import { mkdtemp, readdir, rm, writeFile } from 'node:fs/promises';
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
});
