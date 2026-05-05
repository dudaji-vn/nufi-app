import * as keys from './keys.ts';
import * as me from './me.ts';
import { ping } from './ping.ts';

export const router = {
  ping,
  me,
  keys,
};

export type AppRouter = typeof router;
