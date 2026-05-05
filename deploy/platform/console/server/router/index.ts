import * as me from './me.ts';
import { ping } from './ping.ts';

export const router = {
  ping,
  me,
};

export type AppRouter = typeof router;
