import { createORPCClient } from '@orpc/client';
import { RPCLink } from '@orpc/client/fetch';
import { createTanstackQueryUtils } from '@orpc/tanstack-query';
import type { RouterClient } from '@orpc/server';
import type { AppRouter } from '~server/router';

const link = new RPCLink({
  url: () => new URL('/rpc', window.location.href).toString(),
  fetch: (request, init) => fetch(request, { ...init, credentials: 'include' }),
});

export const client: RouterClient<AppRouter> = createORPCClient(link);

/** Use as `useQuery(api.ping.queryOptions(...))`, `useMutation(api.keys.create.mutationOptions(...))`. */
export const api = createTanstackQueryUtils(client);
