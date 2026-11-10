import { expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';

// The runtime image copies server.ts by name; every local module it imports — directly or through another
// local module — must be copied too, or the container crashes on start (this happened with ./range).
function localImports(file: string, seen = new Set<string>()): Set<string> {
  const src = readFileSync(new URL(`./${file}`, import.meta.url), 'utf8');
  for (const m of src.matchAll(/from '\.\/([^']+)'/g)) {
    const dep = m[1]!.replace(/(\.ts)?$/, '.ts');
    if (!seen.has(dep)) {
      seen.add(dep);
      localImports(dep, seen);
    }
  }
  return seen;
}

test('runtime image copies every local module server.ts needs', () => {
  const needed = localImports('server.ts');
  expect([...needed].sort()).toEqual(['app.ts', 'range.ts']);
  const copy = readFileSync(new URL('./Dockerfile', import.meta.url), 'utf8')
    .split('\n')
    .find((l) => /^COPY .*server\.ts/.test(l)) ?? '';
  for (const f of needed) expect(copy.split(/\s+/)).toContain(f);
});
