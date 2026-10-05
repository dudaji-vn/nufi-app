import { afterEach, beforeEach, describe, expect, test } from 'bun:test';
import { mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { addUser, listUsers, removeUser, updateUser } from '../src/store';

let dir: string;
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'store-'));
  process.env.NUFI_STATE_DIR = dir;
});
afterEach(() => rmSync(dir, { recursive: true, force: true }));

const base = (n: string) => ({ name: 'u' + n, os: 'linux' as const, keyId: 'k' + n, token: 't' + n });

describe('user store', () => {
  test('empty when file absent', async () => {
    expect(await listUsers()).toEqual([]);
  });

  test('add then list persists to disk', async () => {
    const u = await addUser({ name: 'Sun', os: 'macos', keyId: 'k1', token: 't1' });
    expect(u.id).toBeTruthy();
    expect(Number.isNaN(Date.parse(u.createdAt))).toBe(false);
    expect((await listUsers()).map((x) => x.name)).toContain('Sun');
    const onDisk = JSON.parse(readFileSync(join(dir, 'users.json'), 'utf8'));
    expect(onDisk[0].id).toBe(u.id);
    expect(readdirSync(dir)).toEqual(['users.json']);
  });

  test('update patches and throws on unknown id', async () => {
    const u = await addUser(base('1'));
    const out = await updateUser(u.id, { name: 'Renamed' });
    expect(out.name).toBe('Renamed');
    expect(out.id).toBe(u.id);
    expect((await listUsers())[0].name).toBe('Renamed');
    await expect(updateUser('nope', { name: 'x' })).rejects.toThrow();
  });

  test('remove deletes', async () => {
    const a = await addUser(base('1'));
    await addUser(base('2'));
    await removeUser(a.id);
    expect((await listUsers()).map((x) => x.name)).toEqual(['u2']);
  });

  test('concurrent adds do not drop records', async () => {
    const N = 50;
    await Promise.all(Array.from({ length: N }, (_, i) => addUser(base(String(i)))));
    const all = await listUsers();
    expect(all.length).toBe(N);
    expect(new Set(all.map((x) => x.id)).size).toBe(N);
  });
});
