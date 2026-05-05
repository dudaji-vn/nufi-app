import { ORPCError } from '@orpc/server';
import { o } from '../orpc.ts';
import { ensureLiteLLMUser } from '../lib/jit-provision.ts';

/**
 * me.get — return the current user's identity + LiteLLM record.
 * JIT-provisions the LiteLLM user on first visit so downstream key/usage
 * routes always have a record to attach to.
 */
export const get = o.handler(async ({ context }) => {
  if (!context.user) {
    throw new ORPCError('UNAUTHORIZED');
  }

  const litellm = await ensureLiteLLMUser(context.user);

  return {
    id: context.user.id,
    email: context.user.email ?? null,
    role: context.user.role,
    litellm: {
      maxBudget: litellm.max_budget ?? null,
      spend: litellm.spend ?? 0,
      budgetDuration: litellm.budget_duration ?? null,
      tpmLimit: litellm.tpm_limit ?? null,
      rpmLimit: litellm.rpm_limit ?? null,
    },
  };
});
