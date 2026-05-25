import { listModels } from '../lib/litellm.ts';
import { o } from '../orpc.ts';

export const list = o.handler(async (): Promise<{ id: string }[]> => {
  return await listModels();
});
