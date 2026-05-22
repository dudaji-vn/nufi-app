const { shouldUseSecureCookie } = require('@librechat/api');

/**
 * Cookie options for session-level cookies (refreshToken, token_provider,
 * openid_*). Honours COOKIE_DOMAIN and COOKIE_SAMESITE so the cookies can be
 * shared with sibling subdomain apps — e.g. the NUFI console at
 * console.nufi.me reading auth set by chat.nufi.me. Defaults preserve the
 * original LibreChat behaviour (sameSite=strict, no domain).
 *
 * @param {Record<string, unknown>} [extras] Extra options merged last (e.g. `expires`).
 */
function getSessionCookieOptions(extras = {}) {
  const opts = {
    httpOnly: true,
    secure: shouldUseSecureCookie(),
    sameSite: normalizeSameSite(process.env.COOKIE_SAMESITE) || 'strict',
    ...extras,
  };
  if (process.env.COOKIE_DOMAIN) {
    opts.domain = process.env.COOKIE_DOMAIN;
  }
  return opts;
}

/**
 * clearCookie must echo the same domain / sameSite / secure that the set()
 * used — otherwise the browser keeps the original cookie around.
 */
function getClearCookieOptions() {
  return getSessionCookieOptions();
}

function normalizeSameSite(value) {
  if (!value) return undefined;
  const v = String(value).toLowerCase();
  if (v === 'strict' || v === 'lax' || v === 'none') return v;
  return undefined;
}

module.exports = { getSessionCookieOptions, getClearCookieOptions };
