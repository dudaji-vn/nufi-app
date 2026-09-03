/**
 * Who may open which agent product.
 *
 * Every door into NUFI Studio and NUFI Works passes through this console, so
 * the answer lives here rather than in each product. The rules are read from
 * the environment on every call: an entitlement change is an ops action, and
 * making it a restart would tempt someone to keep the list in code.
 *
 * The two defaults are deliberately asymmetric. An UNSET variable admits
 * everyone, because shipping this code to a live deployment must not lock out
 * the members already using it. A MALFORMED variable admits nobody, matching
 * `OIDC_CLIENTS`: a rule nobody can parse is not a rule to guess at.
 */

export type Product = 'studio' | 'works';

type Rules = Partial<Record<Product, string[]>>;

function rules(): Rules | null {
  const raw = process.env.AGENT_ENTITLEMENTS;
  if (raw === undefined || raw.trim() === '') return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    return parsed as Rules;
  } catch {
    return null;
  }
}

export function isEntitled(
  member: { email: string; role: 'ADMIN' | 'USER' },
  product: Product,
): boolean {
  const parsed = rules();
  if (parsed === null) return false;

  // An admin keeps a way in against any well-formed list -- otherwise a typo in
  // the list is unrecoverable without a redeploy.
  if (member.role === 'ADMIN') return true;

  const list = parsed[product];
  if (list === undefined) return true;
  if (!Array.isArray(list)) return false;

  const email = member.email.trim().toLowerCase();
  return list.some((entry) => {
    if (typeof entry !== 'string') return false;
    const rule = entry.trim().toLowerCase();
    if (rule === '*') return true;
    // A domain rule starts with '@', so "@dudaji.vn" cannot be satisfied by
    // "x@notdudaji.vn" -- the '@' is part of the compared suffix.
    if (rule.startsWith('@')) return email.endsWith(rule);
    return email === rule;
  });
}
