/**
 * Every /screenshots/... a page references must exist.
 *
 * The Next build already fails on a missing image, but it fails deep inside a
 * render with a message that names the page and not the file. This says which
 * file, in one line, before the build starts.
 */
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const CONTENT = join(root, 'content', 'docs');
const SHOTS = join(root, 'public', 'screenshots');

function mdxFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return mdxFiles(full);
    return entry.name.endsWith('.mdx') ? [full] : [];
  });
}

const missing = [];
for (const file of mdxFiles(CONTENT)) {
  const body = readFileSync(file, 'utf8');
  for (const [, name] of body.matchAll(/\/screenshots\/([A-Za-z0-9._-]+)/g)) {
    if (!existsSync(join(SHOTS, name))) {
      missing.push(`${file.slice(root.length + 1)} -> /screenshots/${name}`);
    }
  }
}

if (missing.length > 0) {
  console.error('Missing screenshots:');
  for (const line of new Set(missing)) console.error(`  ${line}`);
  console.error(`\n${missing.length} reference(s) with no file. Run \`bun run screenshots\`.`);
  process.exit(1);
}

console.log('All referenced screenshots exist.');
