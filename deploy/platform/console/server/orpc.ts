import { os } from '@orpc/server';

/**
 * Per-request context for every procedure. Filled in by Hono middleware
 * (auth, role) on the way in. Empty for now — populated in W3 Day 2.
 */
export type Context = {
  user?: { id: string; email: string; role: 'USER' | 'ADMIN' };
};

/** Base builder. All procedures branch off this. */
export const o = os.$context<Context>();
