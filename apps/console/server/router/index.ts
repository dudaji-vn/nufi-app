import * as keys from './keys.ts';
import * as me from './me.ts';
import * as models from './models.ts';
import { ping } from './ping.ts';
import * as usage from './usage.ts';

export const router = {
  ping,
  me,
  keys,
  models,
  usage,
};

export type AppRouter = typeof router;
