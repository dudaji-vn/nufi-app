/**
 * Leading HTTP status code that provider SDKs prepend to `err.message`
 * (e.g. `400 This request was blocked by a security policy...`). The status is
 * already carried by the transport; repeating it in front of a sentence written
 * for a human is noise.
 */
const LEADING_HTTP_STATUS = /^\s*[1-5]\d{2}\s+/;

/** Shown only when the underlying error carries nothing a user can act on. */
export const GENERIC_RUN_ERROR = 'An error occurred while processing the request';

/**
 * User-facing text for an error that aborted an agent run.
 *
 * Upstream refusals (security policy blocks, content filters, quota notices)
 * arrive as complete sentences addressed to the user and often carry the only
 * copy of a reference id. Prefixing them with a generic wrapper buries that
 * signal — and, because the renderer truncates at 512 characters, a long enough
 * prefix can push a trailing reference id off the end entirely. So a usable
 * message is surfaced on its own, and the wrapper is kept only when there is
 * nothing else to show.
 */
export function formatRunErrorText(message?: string | null): string {
  if (typeof message !== 'string') {
    return GENERIC_RUN_ERROR;
  }

  const detail = message.replace(LEADING_HTTP_STATUS, '').trim();
  if (!detail) {
    return GENERIC_RUN_ERROR;
  }

  return detail;
}
