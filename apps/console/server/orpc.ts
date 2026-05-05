import { os } from '@orpc/server';
import type { AuthedUser } from './middleware/auth.ts';

/**
 * Per-request context for every procedure. The Hono `auth` middleware
 * verifies the JWT and puts the user here before oRPC dispatches.
 */
export type Context = {
  user: AuthedUser;
};

/** Base builder. All procedures branch off this. */
export const o = os.$context<Context>();
