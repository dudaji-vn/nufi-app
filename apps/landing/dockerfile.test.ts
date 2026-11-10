import { expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';

// The runtime image copies server.ts by name; every local module it imports must be copied too,
// or the container crashes on start (this happened with ./range).
test('runtime image copies every local module server.ts imports', () => {
  const server = readFileSync(new URL('./server.ts', import.meta.url), 'utf8');
  const local = [...server.matchAll(/from '\.\/([^']+)'/g)].map((m) => m[1].replace(/(\.ts)?$/, '.ts'));
  const copy = readFileSync(new URL('./Dockerfile', import.meta.url), 'utf8')
    .split('\n')
    .find((l) => /^COPY .*server\.ts/.test(l)) ?? '';
  expect(local.length).toBeGreaterThan(0);
  for (const f of local) expect(copy.split(/\s+/)).toContain(f);
});
