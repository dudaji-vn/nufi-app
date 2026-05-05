import { o } from '../orpc.ts';

/**
 * Smoke-test procedure. Auth is required (handled by Hono middleware
 * upstream of the oRPC mount), so the handler can rely on context.user.
 */
export const ping = o.handler(({ context }) => ({
  message: 'pong',
  at: new Date().toISOString(),
  user: { id: context.user.id, role: context.user.role },
}));
