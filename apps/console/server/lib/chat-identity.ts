/**
 * Resolve who a member actually is, by asking the chat app.
 *
 * The chat session cookie is the only thing a browser brings to this console,
 * and it carries almost nothing: `{ id, sessionId, iat, exp }`. No email, no
 * role. Minting an identity from those claims alone produces a token with
 * `email: undefined`, which is not a small gap:
 *
 *   - NUFI Works refuses the sign-in outright (`email_is_missing`).
 *   - NUFI Studio accepts it and provisions a user named `external-<hash>`,
 *     which looks like a real account and belongs to nobody.
 *   - Every member arrives as an editor, because `role` is absent too, so the
 *     admin mapping silently never applies.
 *
 * So the id in the cookie is treated as a pointer, not as the identity, and the
 * record is fetched from the app that owns it.
 */

const CHAT_BASE_URL = (process.env.CHAT_BASE_URL ?? 'https://chat.nufi.me').replace(/\/+$/, '');

// LibreChat runs requests through a user-agent parser that rejects callers it
// cannot identify as a browser. This string is load-bearing: without it the
// call fails and every handoff breaks.
const BROWSER_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

export type ChatIdentity = {
  id: string;
  email: string;
  /**
   * Required, not decorative: better-auth refuses a sign-in whose profile has
   * no name (`name_is_missing`), the same way it refuses one with no email.
   * Chat records a display name, but it is not guaranteed to be set, so this
   * falls back rather than letting an empty one through.
   */
  name: string;
  role: 'ADMIN' | 'USER';
  /**
   * The refresh endpoint rotates the session token, so the browser must be
   * given the replacement. Dropping these logs the member out of chat as a
   * side effect of entering another product.
   */
  setCookies: string[];
};

export async function resolveChatIdentity(refreshToken: string): Promise<ChatIdentity | null> {
  let res: Response;
  try {
    res = await fetch(`${CHAT_BASE_URL}/api/auth/refresh`, {
      method: 'POST',
      headers: {
        cookie: `refreshToken=${refreshToken}`,
        'user-agent': BROWSER_UA,
        accept: 'application/json',
      },
    });
  } catch {
    return null;
  }

  if (!res.ok) return null;

  const body = (await res.json().catch(() => null)) as { user?: Record<string, unknown> } | null;
  const user = body?.user;
  const email = typeof user?.email === 'string' ? user.email : undefined;
  const named = [user?.name, user?.username].find(
    (v): v is string => typeof v === 'string' && v.trim().length > 0,
  );
  const id =
    typeof user?.id === 'string' ? user.id : typeof user?._id === 'string' ? user._id : undefined;

  // Fail closed. An identity without an email is the exact defect this exists
  // to prevent, so it is better to refuse the handoff than to mint one.
  if (!email || !id) return null;

  return {
    id,
    email,
    // The local part is a poor display name but a real one; an empty string
    // would fail at the far end after a redirect that looks successful.
    name: named ?? email.split('@')[0],
    role: user?.role === 'ADMIN' ? 'ADMIN' : 'USER',
    setCookies: res.headers.getSetCookie?.() ?? [],
  };
}
