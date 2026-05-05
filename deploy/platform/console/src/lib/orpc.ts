import { createORPCClient, ORPCError } from '@orpc/client';
import { RPCLink } from '@orpc/client/fetch';
import type { RouterClient } from '@orpc/server';
import { createTanstackQueryUtils } from '@orpc/tanstack-query';
import type { AppRouter } from '@server/router';

const link = new RPCLink({
  url: () => new URL('/rpc', window.location.href).toString(),
  fetch: (request, init) => fetch(request, { ...init, credentials: 'include' }),
});

export const client: RouterClient<AppRouter> = createORPCClient(link);

/** Use as `useQuery(api.me.get.queryOptions())`, `useMutation(api.keys.create.mutationOptions())`. */
export const api = createTanstackQueryUtils(client);

export function isUnauthorized(err: unknown): boolean {
  return err instanceof ORPCError && err.code === 'UNAUTHORIZED';
}
