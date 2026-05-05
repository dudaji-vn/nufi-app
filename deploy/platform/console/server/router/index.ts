import { ping } from './ping.ts';

export const router = {
  ping,
};

export type AppRouter = typeof router;
