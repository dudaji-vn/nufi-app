import { ORPCError } from '@orpc/server';
import { o } from '../orpc.ts';
import { ensureLiteLLMUser } from '../lib/jit-provision.ts';
import { getCustomer, listKeysForUser } from '../lib/litellm.ts';

/**
 * me.get — return identity + an honest, combined spend picture.
 *
 * LiteLLM tracks spend in three places that all matter for one user:
 *   - Internal-User row: provisioned by us; carries default budget + limits.
 *   - Customer (End-User) row: chat traffic where LibreChat puts the user id
 *     in the OpenAI `user` field while authenticating with the master key.
 *   - The user's own issued keys: each key has its own spend column.
 *
 * `/user/info.spend` is unreliable for our case — in practice it ignores
 * spend on keys whose creator was the master-key user (which is all of
 * ours). Source of truth for issued-key spend is the sum across the
 * user's keys via /key/list?user_id=…
 */
export const get = o.handler(async ({ context }) => {
  if (!context.user) throw new ORPCError('UNAUTHORIZED');

  const [internalUser, customer, keys] = await Promise.all([
    ensureLiteLLMUser(context.user),
    getCustomer(context.user.id),
    listKeysForUser(context.user.id),
  ]);

  const issuedKeysSpend = keys.reduce((sum, k) => sum + (k.spend ?? 0), 0);
  const chatSpend = customer?.spend ?? 0;
  const totalSpend = chatSpend + issuedKeysSpend;

  const topKeys = keys
    .map((k) => ({
      alias: k.key_alias,
      token: k.token,
      spend: k.spend ?? 0,
      maxBudget: k.max_budget,
    }))
    .sort((a, b) => b.spend - a.spend)
    .slice(0, 5);

  return {
    id: context.user.id,
    email: context.user.email ?? null,
    role: context.user.role,
    spend: {
      total: totalSpend,
      chat: chatSpend,
      issuedKeys: issuedKeysSpend,
    },
    limits: {
      maxBudget: internalUser.max_budget ?? null,
      budgetDuration: internalUser.budget_duration ?? null,
      tpmLimit: internalUser.tpm_limit ?? null,
      rpmLimit: internalUser.rpm_limit ?? null,
    },
    keysCount: keys.length,
    topKeys,
  };
});
