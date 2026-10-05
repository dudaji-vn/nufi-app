import { expect, test } from 'bun:test';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const ENTRYPOINT = join(import.meta.dir, '../entrypoint.sh');
const FAKE_CA = '-----BEGIN CERTIFICATE-----\nFAKECA-for-test\n-----END CERTIFICATE-----\n';

// Runs the entrypoint with a stub `bun` (and a redirected bundle path) so we
// observe the CA bundle and SSL_CERT_FILE it would hand to the server.
test('entrypoint builds a CA bundle with MESH_CA_FILE and exports SSL_CERT_FILE', () => {
  const dir = mkdtempSync(join(tmpdir(), 'ca-'));
  const caFile = join(dir, 'mesh-ca.crt');
  writeFileSync(caFile, FAKE_CA);
  const bundle = join(dir, 'ca-bundle.crt');
  const stubBun = join(dir, 'bun');
  writeFileSync(stubBun, '#!/bin/sh\necho "SSL_CERT_FILE=$SSL_CERT_FILE"\n', { mode: 0o755 });

  const script = readFileSync(ENTRYPOINT, 'utf8').replaceAll('/tmp/ca-bundle.crt', bundle);
  const patched = join(dir, 'entrypoint.sh');
  writeFileSync(patched, script, { mode: 0o755 });

  const p = Bun.spawnSync(['sh', patched], {
    env: { PATH: `${dir}:${process.env.PATH}`, MESH_CA_FILE: caFile },
  });
  expect(p.exitCode).toBe(0);
  expect(p.stdout.toString()).toContain(`SSL_CERT_FILE=${bundle}`);
  expect(readFileSync(bundle, 'utf8')).toContain('FAKECA-for-test');
});

test('entrypoint still works without MESH_CA_FILE', () => {
  const dir = mkdtempSync(join(tmpdir(), 'ca-'));
  const bundle = join(dir, 'ca-bundle.crt');
  writeFileSync(join(dir, 'bun'), '#!/bin/sh\nexit 0\n', { mode: 0o755 });
  const script = readFileSync(ENTRYPOINT, 'utf8').replaceAll('/tmp/ca-bundle.crt', bundle);
  const patched = join(dir, 'entrypoint.sh');
  writeFileSync(patched, script, { mode: 0o755 });
  const p = Bun.spawnSync(['sh', patched], { env: { PATH: `${dir}:${process.env.PATH}` } });
  expect(p.exitCode).toBe(0);
});
