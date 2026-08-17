import { ORPCError } from '@orpc/server';
import { z } from 'zod';
import { matchAllowedOrigin, parseAllowedOrigins } from '../lib/connect-origins.ts';
import { ensureLiteLLMUser } from '../lib/jit-provision.ts';
import { deleteKey, generateKey, listKeysForUser } from '../lib/litellm.ts';
import { o } from '../orpc.ts';

/**
 * `/connect` — hand a gateway key to another NUFI app the user is signed in to.
 *
 * NUFI Agents opens a popup here. Because that is a top-level navigation the
 * chat cookie rides along, so the console can identify the visitor without the
 * opener holding any credential of its own — and without depending on the two
 * apps sharing a site, which they do not on-prem or on a laptop.
 *
 * Everything security-relevant is decided here, not by the caller:
 *   - the origin is matched against an allow-list (see connect-origins.ts);
 *   - `begin` refuses an unlisted origin BEFORE any consent screen renders, so
 *     nobody can be talked through approving one;
 *   - `approve` re-checks rather than trusting that `begin` ran.
 */

const DEFAULT_USER_BUDGET = Number(process.env.DEFAULT_USER_BUDGET ?? 10);
const DEFAULT_BUDGET_DURATION = process.env.DEFAULT_BUDGET_DURATION ?? '30d';
const DEFAULT_TPM_LIMIT = Number(process.env.DEFAULT_TPM_LIMIT ?? 10_000);
const DEFAULT_RPM_LIMIT = Number(process.env.DEFAULT_RPM_LIMIT ?? 60);
const KEY_DEFAULT_DURATION = process.env.KEY_DEFAULT_DURATION ?? '90d';

/**
 * Read at call time, not module load, so a test or a restart-free config change
 * takes effect and so the smoke script can drive it.
 */
function allowedOrigins(): string[] {
  return parseAllowedOrigins(process.env.AGENTS_ALLOWED_ORIGINS);
}

/**
 * One key per (member, workspace). Scoping the alias by workspace means a member
 * connected to two Agents instances can reconnect one without silently cutting
 * off the other.
 */
function aliasFor(workspaceId: string): string {
  return `nufi-agents:${workspaceId}`;
}

/**
 * Untrusted — it only ever names a key, but it is echoed into LiteLLM, so keep
 * it to something that cannot be mistaken for structure.
 */
const WorkspaceId = z
  .string()
  .min(1)
  .max(64)
  .regex(/^[A-Za-z0-9_-]+$/, 'workspace id must be alphanumeric, dash, or underscore');

const Request = z.object({
  origin: z.string().min(1).max(2048),
  workspaceId: WorkspaceId,
});

/**
 * What the consent screen needs to describe the credential truthfully, and
 * whether it may be shown at all.
 *
 * Refusals are returned rather than thrown: the popup has to explain itself to a
 * person, and "the operator has not enabled this" and "this site is not allowed
 * to ask" are different problems with different owners.
 */
export const begin = o.input(Request).handler(async ({ context, input }) => {
  const allowed = allowedOrigins();
  if (allowed.length === 0) {
    return { ok: false as const, reason: 'disabled' as const };
  }

  const origin = matchAllowedOrigin(input.origin, allowed);
  if (!origin) {
    return { ok: false as const, reason: 'origin_not_allowed' as const };
  }

  const alias = aliasFor(input.workspaceId);
  const existing = await listKeysForUser(context.user.id);
  const replaces = existing.filter((k) => k.key_alias === alias).length;

  return {
    ok: true as const,
    origin,
    alias,
    replaces,
    email: context.user.email ?? null,
    terms: {
      maxBudget: DEFAULT_USER_BUDGET,
      budgetDuration: DEFAULT_BUDGET_DURATION,
      tpmLimit: DEFAULT_TPM_LIMIT,
      rpmLimit: DEFAULT_RPM_LIMIT,
      duration: KEY_DEFAULT_DURATION,
    },
  };
});

/**
 * Mint the key. Returns it once; the console never stores or re-shows it.
 *
 * The origin is validated again here. `begin` is a UI affordance, not a gate —
 * a caller can skip it, and this procedure must be safe on its own.
 */
export const approve = o.input(Request).handler(async ({ context, input }) => {
  const origin = matchAllowedOrigin(input.origin, allowedOrigins());
  if (!origin) {
    throw new ORPCError('FORBIDDEN', { message: 'This site is not allowed to request a key.' });
  }

  // Make sure the LiteLLM principal exists first, so the new key inherits the
  // member's budget and limits instead of landing on an implicit row.
  await ensureLiteLLMUser(context.user);

  const alias = aliasFor(input.workspaceId);

  /**
   * Reconnecting replaces rather than accumulates. Without this, every visit
   * leaves another live credential behind for the same workspace and revoking
   * access turns into an archaeology exercise.
   *
   * Revocation runs before minting so a failure here cannot leave the member
   * holding a key the console then fails to record — and so the count shown on
   * the consent screen is what actually gets revoked.
   */
  for (const key of await listKeysForUser(context.user.id)) {
    if (key.key_alias === alias) await deleteKey(key.token);
  }

  const generated = await generateKey({
    user_id: context.user.id,
    key_alias: alias,
    max_budget: DEFAULT_USER_BUDGET,
    budget_duration: DEFAULT_BUDGET_DURATION,
    tpm_limit: DEFAULT_TPM_LIMIT,
    rpm_limit: DEFAULT_RPM_LIMIT,
    duration: KEY_DEFAULT_DURATION,
  });

  return { origin, alias, key: generated.key };
});
