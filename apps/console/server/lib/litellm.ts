/**
 * Thin wrapper around the LiteLLM admin API. The master key never leaves
 * the server process — every call goes out from this module.
 */

const BASE = process.env.LITELLM_BASE_URL ?? 'http://litellm-proxy:4000';
const KEY = process.env.LITELLM_MASTER_KEY ?? '';

export class LiteLLMError extends Error {
  constructor(public status: number, public bodyText: string) {
    super(`LiteLLM ${status}: ${bodyText.slice(0, 200)}`);
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (!KEY) throw new Error('LITELLM_MASTER_KEY not configured');
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${KEY}`,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) throw new LiteLLMError(res.status, text);
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

// --- User -------------------------------------------------------------------

export type LiteLLMUserInfo = {
  user_id: string;
  user_email?: string;
  user_role?: string;
  max_budget?: number | null;
  spend?: number;
  budget_duration?: string | null;
  tpm_limit?: number | null;
  rpm_limit?: number | null;
};

export async function getUser(userId: string): Promise<LiteLLMUserInfo | null> {
  try {
    return await call<LiteLLMUserInfo>('GET', `/user/info?user_id=${encodeURIComponent(userId)}`);
  } catch (err) {
    if (err instanceof LiteLLMError && err.status === 404) return null;
    // LiteLLM also signals "not found" via 400 + body text in some versions
    if (err instanceof LiteLLMError && err.status === 400 && /not found/i.test(err.bodyText)) {
      return null;
    }
    throw err;
  }
}

export async function createUser(input: {
  user_id: string;
  user_email?: string;
  user_role?: 'internal_user' | 'proxy_admin';
  max_budget?: number;
  budget_duration?: string;
  tpm_limit?: number;
  rpm_limit?: number;
}): Promise<LiteLLMUserInfo> {
  return await call<LiteLLMUserInfo>('POST', '/user/new', input);
}
