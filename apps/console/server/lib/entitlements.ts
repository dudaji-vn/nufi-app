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
 * the members already using it. A MALFORMED variable admits nobody but an
 * admin, matching `OIDC_CLIENTS`: a rule nobody can parse is not a rule to
 * guess at -- except that a typo in one Railway variable must not lock ops
 * out of the whole agent surface, including whoever has to diagnose it.
 */

export type Product = 'studio' | 'works';

/**
 * What a member is told the product is called. The internal key ('works') is
 * not a name anyone outside this codebase has seen, so every refusal a member
 * can read maps through here rather than interpolating the key.
 */
export const PRODUCT_NAMES: Readonly<Record<Product, string>> = {
  studio: 'NUFI Studio',
  works: 'NUFI Works',
};

/** The products a member-facing OIDC client may be the front door to. */
export const PRODUCTS: readonly Product[] = ['studio', 'works'];

type Rules = Partial<Record<Product, string[]>>;

function rules(): Rules | null {
  const raw = process.env.AGENT_ENTITLEMENTS;
  if (raw === undefined || raw.trim() === '') return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      console.warn(
        '[entitlements] AGENT_ENTITLEMENTS is not a JSON object; refusing every product to non-admins',
      );
      return null;
    }
    return parsed as Rules;
  } catch {
    console.warn(
      '[entitlements] AGENT_ENTITLEMENTS is not parseable JSON; refusing every product to non-admins',
    );
    return null;
  }
}

export function isEntitled(
  member: { email: string; role: 'ADMIN' | 'USER' },
  product: Product,
): boolean {
  // Checked before the variable is even parsed. `role` comes from the chat
  // identity, verified independently of this list, so admitting an admin here
  // does not mean trusting the unparseable variable -- it means a typo in one
  // Railway variable does not close the whole agent surface to the person who
  // has to fix it.
  if (member.role === 'ADMIN') return true;

  const parsed = rules();
  if (parsed === null) return false;

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
