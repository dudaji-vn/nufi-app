import { createApp } from '../src/app';
import { signSession } from '../src/auth';

export const TEST_ENV = { BOX_OWNER_PASSWORD: 'hunter2', BOX_OWNER_SESSION_SECRET: 'x'.repeat(64) };

export function makeApp(env: Record<string, string | undefined> = {}, deps = {}) {
  return createApp({ ...TEST_ENV, ...env }, deps);
}

// A valid signed owner session, as a Cookie request-header value.
export const ownerCookie = (secret = TEST_ENV.BOX_OWNER_SESSION_SECRET) =>
  `nufi_owner=${signSession(secret)}`;
