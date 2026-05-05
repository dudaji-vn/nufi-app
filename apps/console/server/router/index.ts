import * as keys from './keys.ts';
import * as me from './me.ts';
import { ping } from './ping.ts';
import * as usage from './usage.ts';

export const router = {
  ping,
  me,
  keys,
  usage,
};

export type AppRouter = typeof router;
