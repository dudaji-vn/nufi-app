import { ORPCError } from '@orpc/server';
import { o } from '../orpc.ts';
import { ensureLiteLLMUser } from '../lib/jit-provision.ts';
import { getCustomer } from '../lib/litellm.ts';

/**
 * me.get — return the current user's identity + combined LiteLLM spend.
 *
 * LiteLLM tracks spend in two places:
 *   - Internal User row: spend from issued keys (the W3 self-service flow).
 *   - Customer (End User) row: spend from chat traffic where LibreChat
 *     puts the user id in the OpenAI `user` field while authenticating
 *     with the master key.
 *
 * We fetch both and surface the sum so users see what they actually consumed.
 */
export const get = o.handler(async ({ context }) => {
  if (!context.user) throw new ORPCError('UNAUTHORIZED');

  const [internalUser, customer] = await Promise.all([
    ensureLiteLLMUser(context.user),
    getCustomer(context.user.id),
  ]);

  const issuedKeysSpend = internalUser.spend ?? 0;
  const chatSpend = customer?.spend ?? 0;

  return {
    id: context.user.id,
    email: context.user.email ?? null,
    role: context.user.role,
    spend: {
      total: issuedKeysSpend + chatSpend,
      chat: chatSpend,         // master-key auth + user field in body
      issuedKeys: issuedKeysSpend, // user's own /key/generate keys
    },
    limits: {
      maxBudget: internalUser.max_budget ?? null,
      budgetDuration: internalUser.budget_duration ?? null,
      tpmLimit: internalUser.tpm_limit ?? null,
      rpmLimit: internalUser.rpm_limit ?? null,
    },
  };
});
