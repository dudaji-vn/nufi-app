/**
 * The allow-list that decides who may receive a gateway key from `/connect`.
 *
 * This is the security boundary of the whole connect flow. Any page on the
 * internet can open a popup at `console.nufi.me/connect`; the visitor's chat
 * cookie rides along on that top-level navigation and the console will
 * correctly recognise them. Nothing about *being asked* is suspicious. The one
 * thing that must not happen is the console handing the minted key back to
 * whoever asked.
 *
 * So matching is exact equality between canonical origins. Not `includes`, not
 * `startsWith`, not `endsWith`, and no wildcards — every one of those admits a
 * hostname an attacker can register (`evil-agents.nufi.me`,
 * `agents.nufi.me.evil.com`). See the tests, which encode each attack.
 */

/**
 * Canonicalise one origin, or return null if it is not a usable http(s) origin.
 *
 * `URL.origin` does the normalising that makes exact comparison safe: it
 * lowercases the scheme and host, drops the default port, and discards path,
 * query, and fragment. So `https://Agents.NUFI.me:443/x` and
 * `https://agents.nufi.me` compare equal, while nothing else does.
 */
function canonicalise(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  // A wildcard is an operator asking for exactly the hole this file closes.
  // Refusing beats matching it literally and letting them believe it worked.
  if (trimmed.includes('*')) return null;
  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    return null;
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return null;
  // "null" is the serialisation of an opaque origin (sandboxed frame, some
  // file:// contexts). `new URL` never produces it, but a client can send it.
  if (url.origin === 'null') return null;
  return url.origin;
}

/**
 * Parse `AGENTS_ALLOWED_ORIGINS` — a comma-separated list of origins permitted
 * to receive a key.
 *
 * Unparseable entries are dropped rather than thrown, so one bad character in
 * an environment variable cannot stop the console from booting. An empty result
 * means the endpoint is off; it never means "allow everything".
 */
export function parseAllowedOrigins(raw: string | undefined): string[] {
  if (!raw) return [];
  const seen = new Set<string>();
  for (const entry of raw.split(',')) {
    const origin = canonicalise(entry);
    if (origin) seen.add(origin);
  }
  return [...seen];
}

/**
 * Return the canonical form of `candidate` when it is allowed, else null.
 *
 * Callers must use the returned value — not the one the client sent — as the
 * `postMessage` target, so the delivery address is always one the server chose.
 */
export function matchAllowedOrigin(
  candidate: string | undefined | null,
  allowed: readonly string[],
): string | null {
  if (!candidate) return null;
  const origin = canonicalise(candidate);
  if (!origin) return null;
  return allowed.includes(origin) ? origin : null;
}
