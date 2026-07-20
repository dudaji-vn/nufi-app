/**
 * Thin wrapper around the LiteLLM admin API. The master key never leaves
 * the server process — every call goes out from this module.
 */

const BASE = process.env.LITELLM_BASE_URL ?? 'http://litellm-proxy:4000';
const KEY = process.env.LITELLM_MASTER_KEY ?? '';

export class LiteLLMError extends Error {
  constructor(
    public status: number,
    public bodyText: string,
  ) {
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

// --- End-user / Customer (tracked separately from Internal User) ------------
// LibreChat uses the master key for auth and puts each LibreChat user's id
// in the `user` field of the OpenAI request body. LiteLLM auto-creates a
// Customer row for that id and accumulates spend there — NOT on the
// Internal-User row of the same id. So we always need to fetch both.

export type LiteLLMCustomer = {
  user_id: string; // = end_user_id (the LibreChat _id)
  spend: number;
  blocked?: boolean;
  alias?: string | null;
  litellm_budget_table?: { max_budget?: number | null; budget_duration?: string | null } | null;
};

export async function getCustomer(endUserId: string): Promise<LiteLLMCustomer | null> {
  try {
    return await call<LiteLLMCustomer>(
      'GET',
      `/customer/info?end_user_id=${encodeURIComponent(endUserId)}`,
    );
  } catch (err) {
    if (err instanceof LiteLLMError && err.status === 404) return null;
    if (err instanceof LiteLLMError && err.status === 400 && /not found/i.test(err.bodyText)) {
      return null;
    }
    throw err;
  }
}

// --- Spend logs -------------------------------------------------------------

export type SpendLog = {
  startTime: string;
  spend: number;
  model: string | null;
  api_key: string | null;
  user?: string | null; // either master-key owner OR a key holder
  end_user?: string | null; // OpenAI `user` field from the request body
  metadata?: {
    user_api_key_user_id?: string | null;
    user_api_key_alias?: string | null;
  } | null;
};

type SpendLogResponse = SpendLog[] | { data: SpendLog[] };

/**
 * Fetch spend logs for a user. LiteLLM's `?end_user_id=` and `?customer_id=`
 * query params are silently ignored on this version, so we fetch with only
 * the date filter and match client-side on:
 *
 *   - log.end_user === userId             — chat traffic (master key + user field)
 *   - log.metadata.user_api_key_user_id   — issued-key traffic
 *
 * TODO: if log volume grows, switch to a /spend/end_users/info-style endpoint
 * or per-user materialised view. At current scale (low thousands per user)
 * the client-side filter is fine.
 */
export async function spendLogsForUser(userId: string, startDate?: string): Promise<SpendLog[]> {
  const params = new URLSearchParams();
  if (startDate) params.set('start_date', startDate);
  const url = `/spend/logs${params.toString() ? `?${params}` : ''}`;
  const raw = await call<SpendLogResponse>('GET', url);
  const all = Array.isArray(raw) ? raw : (raw?.data ?? []);
  return all.filter((log) => {
    if (log.end_user && log.end_user === userId) return true;
    if (log.metadata?.user_api_key_user_id === userId) return true;
    return false;
  });
}

// --- Keys -------------------------------------------------------------------

export type LiteLLMKey = {
  key_alias: string | null;
  token: string; // hashed/short identifier — safe to expose
  user_id: string | null;
  team_id: string | null;
  max_budget: number | null;
  spend: number;
  budget_duration: string | null;
  tpm_limit: number | null;
  rpm_limit: number | null;
  created_at: string | null;
  expires: string | null;
};

export type GeneratedKey = LiteLLMKey & {
  /** Full `sk-…` value — only returned by /key/generate, shown to user once. */
  key: string;
};

type KeyListResponse = { keys: LiteLLMKey[] } | LiteLLMKey[];

export async function listKeysForUser(userId: string): Promise<LiteLLMKey[]> {
  // LiteLLM /key/list signature varies between versions; some return an array,
  // others {keys: [...]}. Normalise.
  const raw = await call<KeyListResponse>(
    'GET',
    `/key/list?user_id=${encodeURIComponent(userId)}&return_full_object=true`,
  );
  return Array.isArray(raw) ? raw : (raw?.keys ?? []);
}

export async function listAllKeys(): Promise<LiteLLMKey[]> {
  const raw = await call<KeyListResponse>('GET', '/key/list?return_full_object=true');
  return Array.isArray(raw) ? raw : (raw?.keys ?? []);
}

export async function generateKey(input: {
  user_id: string;
  key_alias?: string;
  team_id?: string;
  max_budget?: number;
  budget_duration?: string;
  tpm_limit?: number;
  rpm_limit?: number;
  duration?: string;
}): Promise<GeneratedKey> {
  return await call<GeneratedKey>('POST', '/key/generate', input);
}

export async function deleteKey(token: string): Promise<void> {
  // POST /key/delete accepts {keys: [...]} of either tokens or full sk-...
  await call<unknown>('POST', '/key/delete', { keys: [token] });
}

// --- Models -----------------------------------------------------------------

export type LiteLLMModel = { id: string };
type ModelListResponse = { data?: Array<{ id: string }> } | Array<{ id: string }>;

export async function listModels(): Promise<LiteLLMModel[]> {
  const raw = await call<ModelListResponse>('GET', '/v1/models');
  const rows = Array.isArray(raw) ? raw : (raw?.data ?? []);
  return rows
    .filter((m): m is { id: string } => typeof m?.id === 'string')
    .map((m) => ({ id: m.id }));
}

export async function getKeyInfo(token: string): Promise<LiteLLMKey | null> {
  try {
    const res = await call<{ info?: LiteLLMKey } & LiteLLMKey>(
      'GET',
      `/key/info?key=${encodeURIComponent(token)}`,
    );
    return res.info ?? (res as LiteLLMKey);
  } catch (err) {
    if (err instanceof LiteLLMError && err.status === 404) return null;
    throw err;
  }
}
