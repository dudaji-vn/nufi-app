import { createApp } from './app';

// Entry point: serves ./dist (see app.ts).
const app = createApp('./dist');

const port = Number(process.env.PORT ?? 3000);
console.log(`nufi-landing listening on :${port}`);

export default { port, fetch: app.fetch };
