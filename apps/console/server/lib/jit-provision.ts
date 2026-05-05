import type { AuthedUser } from '../middleware/auth.ts';
import { createUser, getUser, type LiteLLMUserInfo } from './litellm.ts';

const DEFAULT_USER_BUDGET = Number(process.env.DEFAULT_USER_BUDGET ?? 10);
const DEFAULT_BUDGET_DURATION = process.env.DEFAULT_BUDGET_DURATION ?? '30d';
const DEFAULT_TPM_LIMIT = Number(process.env.DEFAULT_TPM_LIMIT ?? 10_000);
const DEFAULT_RPM_LIMIT = Number(process.env.DEFAULT_RPM_LIMIT ?? 60);

/**
 * Look up the user in LiteLLM. If they don't exist yet (first console
 * visit), provision them with default budget + limits. Idempotent — safe
 * to call on every request.
 */
export async function ensureLiteLLMUser(authed: AuthedUser): Promise<LiteLLMUserInfo> {
  const existing = await getUser(authed.id);
  if (existing) return existing;

  return await createUser({
    user_id: authed.id,
    user_email: authed.email,
    user_role: authed.role === 'ADMIN' ? 'proxy_admin' : 'internal_user',
    max_budget: DEFAULT_USER_BUDGET,
    budget_duration: DEFAULT_BUDGET_DURATION,
    tpm_limit: DEFAULT_TPM_LIMIT,
    rpm_limit: DEFAULT_RPM_LIMIT,
  });
}
