import { o } from '../orpc.ts';

/** Smoke-test procedure — replaced by `me.get` etc. in W3 Day 2+. */
export const ping = o.handler(() => ({ message: 'pong', at: new Date().toISOString() }));
