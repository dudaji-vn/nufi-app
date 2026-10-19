import { describe, expect, test } from 'bun:test';
import { checkUpdate, fetchLatestMain } from '../src/update-check';

const now = () => new Date('2026-10-19T00:00:00Z');

describe('checkUpdate', () => {
  test('update available when the box revision differs from main', async () => {
    const s = await checkUpdate({ revision: () => 'aaaaaaa1111', fetchLatest: async () => 'bbbbbbb2222', now });
    expect(s.current).toBe('aaaaaaa1111');
    expect(s.latest).toBe('bbbbbbb2222');
    expect(s.updateAvailable).toBe(true);
  });

  test('up to date — a short baked sha still matches a full main sha by prefix', async () => {
    const full = '1234567abcdef0000000000000000000000000000';
    const s = await checkUpdate({ revision: () => '1234567', fetchLatest: async () => full, now });
    expect(s.updateAvailable).toBe(false);
  });

  test('unknown (null) when the image never baked a revision', async () => {
    const s = await checkUpdate({ revision: () => '  ', fetchLatest: async () => 'bbbbbbb', now });
    expect(s.current).toBeNull();
    expect(s.updateAvailable).toBeNull();
  });

  test('unknown (null) when GitHub could not be reached', async () => {
    const s = await checkUpdate({ revision: () => 'aaaaaaa', fetchLatest: async () => null, now });
    expect(s.latest).toBeNull();
    expect(s.updateAvailable).toBeNull();
  });
});

describe('fetchLatestMain', () => {
  const resp = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
  test('returns the commit sha on 200', async () => {
    expect(await fetchLatestMain(async () => resp(200, { sha: 'deadbeefcafe' }))).toBe('deadbeefcafe');
  });
  test('null on a non-2xx (rate-limited / private)', async () => {
    expect(await fetchLatestMain(async () => resp(403, { message: 'rate limited' }))).toBeNull();
  });
  test('null when the fetch throws (offline)', async () => {
    expect(await fetchLatestMain(async () => { throw new Error('offline'); })).toBeNull();
  });
  test('null when the payload carries no sha', async () => {
    expect(await fetchLatestMain(async () => resp(200, { nope: 1 }))).toBeNull();
  });
});
