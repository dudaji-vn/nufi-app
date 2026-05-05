import { ORPCError } from '@orpc/server';
import { z } from 'zod';
import { o } from '../orpc.ts';
import {
  deleteKey as litellmDeleteKey,
  generateKey,
  getKeyInfo,
  listAllKeys,
  listKeysForUser,
  type LiteLLMKey,
} from '../lib/litellm.ts';

// --- Shared shapes ----------------------------------------------------------

const BUDGET_DURATIONS = ['24h', '7d', '30d'] as const;
const KEY_DURATIONS = ['7d', '30d', '90d', '180d', '365d', 'never'] as const;

const KeyView = z.object({
  alias: z.string().nullable(),
  token: z.string(), // safe identifier for delete / info — never the raw sk-...
  userId: z.string().nullable(),
  teamId: z.string().nullable(),
  maxBudget: z.number().nullable(),
  spend: z.number(),
  budgetDuration: z.string().nullable(),
  tpmLimit: z.number().nullable(),
  rpmLimit: z.number().nullable(),
  createdAt: z.string().nullable(),
  expires: z.string().nullable(),
});
type KeyView = z.infer<typeof KeyView>;

function toView(k: LiteLLMKey): KeyView {
  return {
    alias: k.key_alias,
    token: k.token,
    userId: k.user_id,
    teamId: k.team_id,
    maxBudget: k.max_budget,
    spend: k.spend ?? 0,
    budgetDuration: k.budget_duration,
    tpmLimit: k.tpm_limit,
    rpmLimit: k.rpm_limit,
    createdAt: k.created_at,
    expires: k.expires,
  };
}

// --- list -------------------------------------------------------------------

export const list = o.handler(async ({ context }): Promise<KeyView[]> => {
  const keys =
    context.user.role === 'ADMIN' ? await listAllKeys() : await listKeysForUser(context.user.id);
  return keys.map(toView);
});

// --- create -----------------------------------------------------------------

const DEFAULT_USER_BUDGET = Number(process.env.DEFAULT_USER_BUDGET ?? 10);
const DEFAULT_BUDGET_DURATION = process.env.DEFAULT_BUDGET_DURATION ?? '30d';
const DEFAULT_TPM_LIMIT = Number(process.env.DEFAULT_TPM_LIMIT ?? 10_000);
const DEFAULT_RPM_LIMIT = Number(process.env.DEFAULT_RPM_LIMIT ?? 60);
const KEY_DEFAULT_DURATION = process.env.KEY_DEFAULT_DURATION ?? '90d';

export const create = o
  .input(
    z.object({
      alias: z.string().min(1).max(64),
      maxBudget: z.number().positive().max(10_000).optional(),
      budgetDuration: z.enum(BUDGET_DURATIONS).optional(),
      tpmLimit: z.number().int().positive().max(10_000_000).optional(),
      rpmLimit: z.number().int().positive().max(100_000).optional(),
      duration: z.enum(KEY_DURATIONS).optional(),
    }),
  )
  .handler(async ({ context, input }) => {
    const generated = await generateKey({
      user_id: context.user.id,
      key_alias: input.alias,
      max_budget: input.maxBudget ?? DEFAULT_USER_BUDGET,
      budget_duration: input.budgetDuration ?? DEFAULT_BUDGET_DURATION,
      tpm_limit: input.tpmLimit ?? DEFAULT_TPM_LIMIT,
      rpm_limit: input.rpmLimit ?? DEFAULT_RPM_LIMIT,
      duration: input.duration === 'never' ? undefined : (input.duration ?? KEY_DEFAULT_DURATION),
    });

    return {
      key: generated.key, // full sk-... — shown to user ONCE
      view: toView(generated),
    };
  });

// --- delete -----------------------------------------------------------------

export const remove = o
  .input(z.object({ token: z.string().min(1) }))
  .handler(async ({ context, input }) => {
    // Authorisation: USER can only delete keys they own; ADMIN can delete any.
    if (context.user.role !== 'ADMIN') {
      const info = await getKeyInfo(input.token);
      if (!info) throw new ORPCError('NOT_FOUND', { message: 'Key not found' });
      if (info.user_id !== context.user.id) {
        throw new ORPCError('FORBIDDEN', { message: 'Cannot delete another user’s key' });
      }
    }
    await litellmDeleteKey(input.token);
    return { ok: true } as const;
  });

// --- info -------------------------------------------------------------------

export const info = o
  .input(z.object({ token: z.string().min(1) }))
  .handler(async ({ context, input }): Promise<KeyView> => {
    const k = await getKeyInfo(input.token);
    if (!k) throw new ORPCError('NOT_FOUND', { message: 'Key not found' });
    if (context.user.role !== 'ADMIN' && k.user_id !== context.user.id) {
      throw new ORPCError('FORBIDDEN', { message: 'Cannot inspect another user’s key' });
    }
    return toView(k);
  });
