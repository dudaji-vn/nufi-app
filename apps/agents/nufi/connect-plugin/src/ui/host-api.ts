/**
 * Thin client over the host's own REST API.
 *
 * Plugin UI is same-origin trusted code by Paperclip's model, so it can call
 * `/api/...` with the signed-in member's session exactly as the built-in
 * Settings → My secrets tab does. That matters here: the worker has no
 * secrets-write capability, and a user secret must be written *as that user*
 * anyway. Going through the browser is not a shortcut around the permission
 * model — it is the permission model.
 */

/** The env var name agents read, and the definition key members fill in. */
export const SECRET_KEY = "NUFI_MODEL_API_KEY";

export class HostApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "HostApiError";
    this.status = status;
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { error?: string } | null;
    throw new HostApiError(res.status, body?.error ?? `Request failed: ${res.status}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

/** This plugin's manifest id; the config endpoint is keyed by it. */
export const PLUGIN_ID = "nufi.connect";

export interface PluginConfig {
  configJson?: { consoleUrl?: unknown } | null;
}

/**
 * Turn whatever is stored in plugin config into a console URL we are willing to
 * open, or null.
 *
 * The value ends up in `window.open`, so the scheme check is not cosmetic: a
 * `javascript:` URL there executes in this origin. Config is admin-only to
 * write, but "only an admin can hurt you" is a weaker guarantee than not
 * accepting the shape at all.
 */
export function normaliseConsoleUrl(raw: unknown): string | null {
  if (typeof raw !== "string" || !raw.trim()) return null;
  const trimmed = raw.trim().replace(/\/+$/, "");
  try {
    const url = new URL(trimmed);
    if (url.protocol !== "https:" && url.protocol !== "http:") return null;
  } catch {
    return null;
  }
  return trimmed;
}

/**
 * Read the operator's config for this company.
 *
 * Any member may read it — an address is not a secret — and only an instance
 * admin can write it, enforced server side. That split is why the page reads
 * the console URL here rather than accepting one from its own query string: a
 * page that names its own credential issuer is the whole attack.
 */
export async function readConsoleUrl(companyId: string): Promise<string | null> {
  const config = await call<PluginConfig | null>(
    `/plugins/${encodeURIComponent(PLUGIN_ID)}/config?companyId=${encodeURIComponent(companyId)}`,
  );
  return normaliseConsoleUrl(config?.configJson?.consoleUrl);
}

export interface UserSecretEntry {
  definition: { id: string; key: string; name: string };
  secret: { id: string; lastRotatedAt: string | null; createdAt: string } | null;
}

export function listMyUserSecrets(companyId: string): Promise<UserSecretEntry[]> {
  return call<UserSecretEntry[]>(`/companies/${encodeURIComponent(companyId)}/me/user-secrets`);
}

/**
 * Declare the company-wide definition members fill in. Admin-only server side;
 * a non-admin gets a 403 the page turns into an explanation rather than a probe
 * of their permissions before showing the button.
 */
export function createDefinition(companyId: string): Promise<unknown> {
  return call(`/companies/${encodeURIComponent(companyId)}/user-secret-definitions`, {
    method: "POST",
    body: JSON.stringify({
      key: SECRET_KEY,
      name: "NUFI gateway key",
      description:
        "Each member's own key for the NUFI model gateway. Set it from Settings → NUFI; agents bound to it call the gateway as whoever the work belongs to.",
      usageGuidance: "Bind on an agent as env NUFI_MODEL_API_KEY with a user secret reference.",
    }),
  });
}

export function createMyUserSecret(companyId: string, value: string): Promise<{ id: string }> {
  return call<{ id: string }>(`/companies/${encodeURIComponent(companyId)}/me/user-secrets`, {
    method: "POST",
    body: JSON.stringify({ definitionKey: SECRET_KEY, value }),
  });
}

/**
 * Replace an existing value. Rotation rather than delete-and-recreate keeps the
 * secret id stable, so agents already bound to it keep working.
 */
export function rotateMyUserSecret(
  companyId: string,
  secretId: string,
  value: string,
): Promise<{ id: string }> {
  return call<{ id: string }>(
    `/companies/${encodeURIComponent(companyId)}/me/user-secrets/${encodeURIComponent(secretId)}/rotate`,
    { method: "POST", body: JSON.stringify({ definitionKey: SECRET_KEY, value }) },
  );
}
