import { createApp } from './app';

const app = createApp();
export default { port: Number(process.env.PORT ?? 8890), fetch: app.fetch };
