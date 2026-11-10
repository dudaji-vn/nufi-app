import { afterAll, beforeAll, expect, test } from 'bun:test';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { rangeResponse } from './range';

let dir: string;
let file: string;
beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), 'range-'));
  file = join(dir, 'clip.mp4');
  writeFileSync(file, '0123456789');
});
afterAll(() => rmSync(dir, { recursive: true, force: true }));

test('bytes=2-5 returns 206 with exactly those bytes', async () => {
  const r = await rangeResponse(file, 'bytes=2-5');
  expect(r?.status).toBe(206);
  expect(r?.headers.get('content-range')).toBe('bytes 2-5/10');
  expect(r?.headers.get('content-length')).toBe('4');
  expect(r?.headers.get('content-type')).toContain('video/mp4');
  expect(await r?.text()).toBe('2345');
});

test('open-ended range bytes=7- runs to the end', async () => {
  const r = await rangeResponse(file, 'bytes=7-');
  expect(r?.headers.get('content-range')).toBe('bytes 7-9/10');
  expect(await r?.text()).toBe('789');
});

test('suffix range bytes=-3 returns the last 3 bytes', async () => {
  const r = await rangeResponse(file, 'bytes=-3');
  expect(await r?.text()).toBe('789');
});

test('end past the file is clamped', async () => {
  const r = await rangeResponse(file, 'bytes=8-999');
  expect(r?.headers.get('content-range')).toBe('bytes 8-9/10');
});

test('start past the end is 416', async () => {
  const r = await rangeResponse(file, 'bytes=50-60');
  expect(r?.status).toBe(416);
  expect(r?.headers.get('content-range')).toBe('bytes */10');
});

test('missing file or unparseable header falls through (null)', async () => {
  expect(await rangeResponse(join(dir, 'nope.mp4'), 'bytes=0-1')).toBeNull();
  expect(await rangeResponse(file, 'items=0-1')).toBeNull();
});
