import { expect, test } from 'bun:test';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// The Dockerfile builds with NODE_ENV=production, where Bun (1.3.x) can't load react-dom/server's production build.
test('prerender works under NODE_ENV=production (as in the Docker build)', () => {
  const dist = mkdtempSync(join(tmpdir(), 'prerender-'));
  try {
    writeFileSync(join(dist, 'index.html'), readFileSync(join(import.meta.dir, '..', 'index.html'), 'utf8'));
    const r = Bun.spawnSync(['bun', join(import.meta.dir, 'prerender.ts'), dist], {
      env: { ...process.env, NODE_ENV: 'production' },
    });
    expect(r.stderr.toString()).toBe('');
    expect(r.exitCode).toBe(0);
    expect(readFileSync(join(dist, 'blog', 'when-everyone-asks-the-llm-at-once', 'index.html'), 'utf8')).toContain(
      '<h1>When everyone asks the LLM at once',
    );
    for (const f of ['404.html', 'llms.txt', 'robots.txt', 'sitemap.xml']) expect(existsSync(join(dist, f))).toBe(true);
  } finally {
    rmSync(dist, { recursive: true, force: true });
  }
});
