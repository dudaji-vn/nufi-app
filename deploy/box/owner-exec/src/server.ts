import { appendFileSync, chmodSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';

import { createApp } from './handler';

const stateDir = process.env.NUFI_STATE_DIR || '/state';
const sock = process.env.EXEC_SOCK || '/sock/exec.sock';

const app = createApp({
  spawn: Bun.spawn,
  now: () => new Date(),
  auditAppend: (line) => {
    mkdirSync(stateDir, { recursive: true });
    appendFileSync(join(stateDir, 'audit.log'), line + '\n');
  },
});

mkdirSync(dirname(sock), { recursive: true });
rmSync(sock, { force: true }); // stale socket from a previous run
Bun.serve({ unix: sock, fetch: app.fetch, idleTimeout: 0 });
try {
  // The shared volume is the access boundary; the console runs as uid 1000.
  chmodSync(sock, 0o666);
} catch {}
console.log(`owner-exec listening on ${sock}`);
