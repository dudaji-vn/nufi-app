/**
 * How a door refuses.
 *
 * Three endpoints can turn a member away -- `/enter/studio`, `/enter/products`
 * and `/oidc/authorize` -- and two of them are reached by a top-level browser
 * navigation, not by a script. A member who clicks "NUFI Studio" and lands on
 * `{"error":"unauthorized"}` has been given a status code where a page was
 * needed. So the refusal is shaped by who asked, and every refusal site shares
 * one implementation: three doors that behave differently for a member in the
 * same state is the defect this file exists to prevent.
 */

import type { Context } from 'hono';

// CHAT_BASE_URL (used by chat-identity.ts's fetch()) only needs to be
// reachable from the console -- on a deploy with private networking that can
// be an internal-only host like chat.railway.internal. A redirect sends the
// member's own browser to chat instead, which needs a host the browser can
// resolve, so it is not always the same address. CHAT_PUBLIC_URL is that
// address; it defaults to CHAT_BASE_URL so a deployment with one public chat
// host needs to set nothing new.
const CHAT_URL = (
  process.env.CHAT_PUBLIC_URL ??
  process.env.CHAT_BASE_URL ??
  'https://chat.nufi.me'
).replace(/\/+$/, '');

/**
 * Where a member with no NUFI session is sent.
 *
 * No return parameter is attached. Chat's login page does read one --
 * `client/src/utils/redirect.ts` exports `REDIRECT_PARAM = 'redirect_to'` and
 * `Auth/Login.tsx` persists it -- but its `isSafeRedirect()` accepts only a
 * site-relative path (`if (!url.startsWith('/') || url.startsWith('//')) return
 * false`), so a console URL is dropped on arrival. Sending one would ship a
 * parameter that silently does nothing.
 */
export const CHAT_LOGIN_URL = `${CHAT_URL}/login`;

/** Where a member without an entitlement is sent: the chooser explains itself. */
export const CHOOSER_URL = `https://${process.env.CHOOSER_HOST ?? 'agents.nufi.me'}/choose`;

/**
 * A browser navigation gets sent somewhere it can act on; a script gets a
 * status code. The split is on Accept, because `verify-agents.sh` asserts a
 * status code -- anonymous `curl` sends a wildcard Accept and must keep
 * receiving 401 -- and a browser must never be shown raw JSON as an answer to
 * a click.
 */
export function refuse(
  c: Context,
  redirectTo: string,
  body: Record<string, string>,
  status: 401 | 403,
): Response {
  if (wantsHtml(c)) {
    return c.redirect(redirectTo, 302);
  }
  return c.json(body, status);
}

/** A member whose chat session is gone gets sent to sign back in. */
export function noSession(c: Context, detail = 'could not resolve NUFI identity'): Response {
  return refuse(c, CHAT_LOGIN_URL, { error: 'unauthorized', detail }, 401);
}

function wantsHtml(c: Context): boolean {
  return (c.req.header('accept') ?? '').includes('text/html');
}
