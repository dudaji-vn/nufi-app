# Agent products — entitlements, session continuity, and standing verification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four gaps deliberately deferred when NUFI Studio and NUFI Works went live — anyone with a chat account can enter both, a Studio session dies silently after eight hours, the deploy is only verified by hand, and the docs screenshots are only checked at build time — and produce the cluster decision that unblocks agents actually running in Works.

**Architecture:** The console stays the single identity authority: every door into a product already runs through `GET /enter/studio` or `GET /oidc/authorize`, so an entitlement check is one function called at two call sites plus a read-only endpoint the chooser uses to grey out what a member cannot open. Session continuity is the same door used a second time: the Studio frontend, on a terminal auth failure, sends the browser back through `/enter/studio?next=<path>` instead of showing a local login form. Verification and screenshot integrity become workflows so they hold without anyone remembering. The sandbox work is a written decision, not code — Works already ships a first-party Kubernetes sandbox provider, so what is missing is a cluster to point it at.

**Tech Stack:** Hono + `bun test` (console server), React 19 + Jest (Studio fork frontend), GitHub Actions, Playwright (docs screenshots), Fumadocs/Next (docs build).

**Spec:** `docs/superpowers/plans/2026-08-26-nufi-agents-cloud.md` — section "Not in this plan" (entitlements, silent token refresh, the sandbox cluster) and the "Blocked on a person" table. This plan implements exactly those deferrals plus the two standing-guard items that fell out of them.

## Global Constraints

- **The fork stays rebasable.** Any change under `apps/nufi-agent/` outside the allowlist in `apps/nufi-agent/nufi/check-fork-diff.sh` fails CI. A new file there — test files included — needs its path added to `ALLOWLIST` in that script, which is inside the NuFi-owned `nufi/` directory.
- **Fail closed on a malformed config, open on an absent one.** `OIDC_CLIENTS` already sets this precedent (`oidc.ts:43-52`): unparseable input disables the flow. An *unset* entitlement variable must leave the live products reachable — shipping this code must not lock every member out of production before ops sets a value.
- **A member with `role === 'ADMIN'` is always entitled.** Ops must keep a way in that does not depend on the list being right.
- **`deploy/railway/verify-agents.sh` must keep passing unchanged.** It asserts `GET /enter/studio` → `401` with no session. curl sends `Accept: */*`, so any HTML-navigation branch added in Task 2 must key on `text/html` and leave the scripted case at 401.
- **Console tests run with `bun test` from `apps/console/`; Studio frontend tests run with `npx jest` from `apps/nufi-agent/src/frontend/`.**
- **Product names in user-visible copy are "NUFI Studio" and "NUFI Works".** Never "Langflow", never "Paperclip" — `check-backend-brand.sh` and the white-label block of `verify-agents.sh` both enforce it.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/console/server/lib/entitlements.ts` *(new)* | Pure decision: may this member enter this product? Owns the env parsing and the fail-open/fail-closed rule. No HTTP, no I/O. |
| `apps/console/server/lib/entitlements.test.ts` *(new)* | The decision table, including malformed and unset config. |
| `apps/console/server/enter.ts` *(modify)* | Adds the Studio entitlement gate, `GET /enter/products`, `?next=` handling, and the HTML-navigation bounce. |
| `apps/console/server/oidc.ts` *(modify)* | Adds the Works entitlement gate to `/authorize` via an optional `product` field on a registered client. |
| `apps/console/src/routes/choose.tsx` *(modify)* | Asks `/enter/products` and disables the card a member cannot open. |
| `apps/nufi-agent/src/frontend/src/customization/config-constants.ts` *(modify)* | `NUFI_ENTER_URL` — where Studio sends a browser whose identity expired. |
| `apps/nufi-agent/src/frontend/src/customization/utils/urls.ts` *(modify)* | `getNufiEnterUrl()` + `shouldReenter()` — URL construction and the loop guard, kept pure so they are testable. |
| `apps/nufi-agent/src/frontend/src/controllers/API/api.tsx` *(modify)* | Calls the re-entry redirect on the terminal auth path instead of falling through to the local login page. |
| `apps/nufi-agent/src/frontend/src/customization/utils/__tests__/nufi-reentry.test.ts` *(new)* | Covers the URL shape and the cooldown. |
| `apps/nufi-agent/nufi/check-fork-diff.sh` *(modify)* | Allowlists the new test file. |
| `.github/workflows/verify-agents.yml` *(new)* | Runs the existing verification script on a schedule and on demand. |
| `apps/docs/scripts/check-screenshots.mjs` *(new)* | Fails when an MDX page references a screenshot that is not in `public/screenshots/`. |
| `.github/workflows/docs-ci.yml` *(modify)* | Runs the screenshot check before the build, so the failure names the missing file. |
| `docs/2026-09-05-works-sandbox-cluster-decision.md` *(new)* | The provider decision for the Kubernetes sandbox, with the requirements it was judged against. |

---

### Task 1: Entitlement gate for the agent products

Today every account that can sign in to `chat.nufi.me` can open NUFI Studio and NUFI Works. The console decides who enters, so the decision belongs there.

**Files:**
- Create: `apps/console/server/lib/entitlements.ts`
- Create: `apps/console/server/lib/entitlements.test.ts`
- Modify: `apps/console/server/enter.ts` (after the identity lookup, `enter.ts:34-40`)
- Modify: `apps/console/server/oidc.ts` (client type `oidc.ts:10-23`; `/authorize` after the identity lookup, `oidc.ts:90-96`)
- Modify: `apps/console/src/routes/choose.tsx`
- Modify: `deploy/railway/agents.md` (document `AGENT_ENTITLEMENTS`)

**Interfaces:**
- Consumes: `ChatIdentity` from `server/lib/chat-identity.ts` — `{ id, email, name, role: 'ADMIN' | 'USER', setCookies }`.
- Produces:
  - `type Product = 'studio' | 'works'`
  - `isEntitled(member: { email: string; role: 'ADMIN' | 'USER' }, product: Product): boolean`
  - `GET /enter/products` → `200 { studio: boolean, works: boolean }` or `401 { error: 'unauthorized' }`
  - `Client.product?: Product` on entries of `OIDC_CLIENTS`

- [ ] **Step 1: Write the failing test**

Create `apps/console/server/lib/entitlements.test.ts`:

```ts
import { afterEach, describe, expect, it } from 'bun:test';
import { isEntitled } from './entitlements.ts';

const member = { email: 'a@dudaji.vn', role: 'USER' as const };
const admin = { email: 'ops@dudaji.vn', role: 'ADMIN' as const };

afterEach(() => {
  delete process.env.AGENT_ENTITLEMENTS;
});

describe('isEntitled', () => {
  it('lets everyone in when the variable is unset', () => {
    expect(isEntitled(member, 'studio')).toBe(true);
    expect(isEntitled(member, 'works')).toBe(true);
  });

  it('lets nobody in when the variable is malformed', () => {
    process.env.AGENT_ENTITLEMENTS = '{not json';
    expect(isEntitled(member, 'studio')).toBe(false);
    // Not even an admin: a config nobody can read is a config nobody trusts.
    expect(isEntitled(admin, 'studio')).toBe(false);
  });

  it('matches a listed address exactly, case-insensitively', () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: ['A@Dudaji.VN'] });
    expect(isEntitled(member, 'studio')).toBe(true);
    expect(isEntitled({ email: 'b@dudaji.vn', role: 'USER' }, 'studio')).toBe(false);
  });

  it('matches a domain entry by suffix', () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ works: ['@dudaji.vn'] });
    expect(isEntitled(member, 'works')).toBe(true);
    expect(isEntitled({ email: 'x@example.com', role: 'USER' }, 'works')).toBe(false);
  });

  it('does not let a lookalike domain through', () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ works: ['@dudaji.vn'] });
    expect(isEntitled({ email: 'x@notdudaji.vn', role: 'USER' }, 'works')).toBe(false);
  });

  it('leaves a product open when its list is absent', () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: ['a@dudaji.vn'] });
    expect(isEntitled({ email: 'x@example.com', role: 'USER' }, 'works')).toBe(true);
  });

  it('always admits an admin against a well-formed list', () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: [] });
    expect(isEntitled(admin, 'studio')).toBe(true);
    expect(isEntitled(member, 'studio')).toBe(false);
  });

  it('treats "*" as everyone', () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: ['*'] });
    expect(isEntitled({ email: 'x@example.com', role: 'USER' }, 'studio')).toBe(true);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd apps/console && bun test server/lib/entitlements.test.ts`
Expected: FAIL — `Cannot find module './entitlements.ts'`.

- [ ] **Step 3: Write the implementation**

Create `apps/console/server/lib/entitlements.ts`:

```ts
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
```

- [ ] **Step 4: Run the test and watch it pass**

Run: `cd apps/console && bun test server/lib/entitlements.test.ts`
Expected: PASS, 8 tests.

- [ ] **Step 5: Write the failing route tests**

Append to `apps/console/server/enter.test.ts` (the file already stubs the chat lookup and builds an app via `as(member)`; reuse both):

```ts
describe('entitlement', () => {
  afterEach(() => {
    delete process.env.AGENT_ENTITLEMENTS;
  });

  it('refuses a member who is not on the Studio list', async () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: ['someone@else.com'] });
    const res = await as(member).request('/studio', WITH_SESSION);
    expect(res.status).toBe(403);
    // The door closes without minting anything.
    expect(res.headers.get('set-cookie') ?? '').not.toContain('nufi_id=');
  });

  it('still hands back the rotated chat session when it refuses', async () => {
    // Refusing entry must not sign the member out of chat as a side effect.
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: [] });
    const app = as(member);
    // after as(), which re-stubs and would otherwise clear this
    chatReply.setCookie = 'refreshToken=rotated; Path=/';
    const res = await app.request('/studio', WITH_SESSION);
    expect(res.status).toBe(403);
    expect(res.headers.get('set-cookie') ?? '').toContain('refreshToken=rotated');
  });

  it('reports per-product entitlement to the chooser', async () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: ['a@b.c'], works: [] });
    const res = await as(member).request('/products', WITH_SESSION);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ studio: true, works: false });
  });

  it('refuses to report entitlement without a session', async () => {
    const app = as(member);
    stubChat(null); // after as(), which re-stubs a valid member
    const res = await app.request('/products');
    expect(res.status).toBe(401);
  });
});
```

- [ ] **Step 6: Run them and watch them fail**

Run: `cd apps/console && bun test server/enter.test.ts`
Expected: FAIL — the Studio route still returns 302, and `/products` returns 404.

- [ ] **Step 7: Gate `/enter/studio` and add `/enter/products`**

In `apps/console/server/enter.ts`, add the import:

```ts
import { isEntitled } from './lib/entitlements.ts';
```

and insert the check immediately after the `for (const cookie of identity.setCookies)` loop in the `/studio` handler, before `signIdentity`:

```ts
  // Checked after the rotated session is handed back and before anything is
  // minted: a member who may not enter must still leave with a working chat
  // session, and must never receive an identity token.
  if (!isEntitled(identity, 'studio')) {
    return c.json({ error: 'forbidden', detail: 'not entitled to NUFI Studio' }, 403);
  }
```

Then append the read-only endpoint at the end of the file:

```ts
/**
 * What this member may open. The chooser at agents.nufi.me asks before it
 * renders, so a member sees a disabled card with a reason rather than
 * discovering the refusal by clicking into it.
 */
enter.get('/products', async (c) => {
  const refreshToken = getCookie(c, 'refreshToken');
  const identity = refreshToken ? await resolveChatIdentity(refreshToken) : null;
  if (!identity) {
    return c.json({ error: 'unauthorized', detail: 'could not resolve NUFI identity' }, 401);
  }
  for (const cookie of identity.setCookies) c.header('set-cookie', cookie, { append: true });

  return c.json({
    studio: isEntitled(identity, 'studio'),
    works: isEntitled(identity, 'works'),
  });
});
```

- [ ] **Step 8: Run the console tests**

Run: `cd apps/console && bun test`
Expected: PASS — the whole suite, including the pre-existing enter/oidc tests.

- [ ] **Step 9: Write the failing `/authorize` test**

Append to `apps/console/server/oidc.test.ts`, inside the `/authorize` describe block (reuse the file's existing client fixture; add `product: 'works'` to the registered `nufi-works` client in the fixture used by this test):

```ts
  it('refuses to issue a code to a member not entitled to the product', async () => {
    process.env.OIDC_CLIENTS = JSON.stringify([
      {
        clientId: 'nufi-works',
        clientSecret: 's3cret',
        redirectUris: [CALLBACK],
        product: 'works',
      },
    ]);
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ works: ['someone@else.com'] });

    const res = await as(member).request(
      `/authorize?client_id=nufi-works&redirect_uri=${encodeURIComponent(CALLBACK)}&state=x`,
      { headers: { cookie: 'refreshToken=rt-test' } },
    );

    expect(res.status).toBe(403);
    // The refusal must not travel as a redirect: a code must never reach the
    // client, not even one that would be rejected later.
    expect(res.headers.get('location')).toBeNull();
  });

  it('issues a code when the client declares no product', async () => {
    process.env.OIDC_CLIENTS = JSON.stringify([
      {
        clientId: 'nufi-works',
        clientSecret: 's3cret',
        redirectUris: [CALLBACK],
      },
    ]);
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ works: [] });

    const res = await as(member).request(
      `/authorize?client_id=nufi-works&redirect_uri=${encodeURIComponent(CALLBACK)}&state=x`,
      { headers: { cookie: 'refreshToken=rt-test' } },
    );

    expect(res.status).toBe(302);
  });
```

- [ ] **Step 10: Run it and watch it fail**

Run: `cd apps/console && bun test server/oidc.test.ts`
Expected: FAIL — the first case returns 302 with a `location` header.

- [ ] **Step 11: Gate `/authorize`**

In `apps/console/server/oidc.ts`, import the module:

```ts
import { isEntitled, type Product } from './lib/entitlements.ts';
```

Add the field to the `Client` type, after `audience?: string;`:

```ts
  /**
   * The product this client is the front door to. Present ⇒ the member must be
   * entitled to it before a code is issued. Absent ⇒ no entitlement check,
   * which is what a federation client (a server, not a member) needs.
   */
  product?: Product;
```

And in the `/authorize` handler, after the `for (const cookie of identity.setCookies)` line and before the code is minted:

```ts
  if (client.product && !isEntitled(identity, client.product)) {
    return c.json({ error: 'forbidden', detail: `not entitled to ${client.product}` }, 403);
  }
```

- [ ] **Step 12: Run the full console suite**

Run: `cd apps/console && bun test && bun run typecheck && bun run lint`
Expected: all PASS.

- [ ] **Step 13: Grey out what a member cannot open**

In `apps/console/src/routes/choose.tsx`, add the lookup and disable the card. Replace the `PRODUCTS.map(...)` anchor with a version that reads a `key` per product:

```tsx
import { useEffect, useState } from 'react';

type Entitlements = { studio: boolean; works: boolean };

// ...inside Choose():
  const [allowed, setAllowed] = useState<Entitlements>({ studio: true, works: true });

  useEffect(() => {
    // Same origin: the chooser is this console served on another hostname.
    // A failed lookup leaves both cards enabled -- the server refuses anyway,
    // and a network blip should not tell a member they have lost access.
    fetch('/enter/products', { credentials: 'same-origin' })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: Entitlements | null) => data && setAllowed(data))
      .catch(() => {});
  }, []);
```

Give each entry in `PRODUCTS` a `key: 'studio' | 'works'` field (`'studio'` for NUFI Studio, `'works'` for NUFI Works), then render:

```tsx
        {PRODUCTS.map((p) =>
          allowed[p.key] ? (
            <a
              key={p.name}
              href={p.href}
              {...(p.external ? {} : { rel: 'noreferrer' })}
              className="group rounded-xl border p-6 transition-colors hover:border-foreground/40 hover:bg-accent/40"
            >
              <h2 className="font-medium text-lg">{p.name}</h2>
              <p className="mt-2 text-muted-foreground text-sm leading-relaxed">{p.blurb}</p>
              <span className="mt-4 inline-block text-sm transition-colors group-hover:text-foreground text-muted-foreground">
                Open →
              </span>
            </a>
          ) : (
            <div key={p.name} className="rounded-xl border p-6 opacity-60">
              <h2 className="font-medium text-lg">{p.name}</h2>
              <p className="mt-2 text-muted-foreground text-sm leading-relaxed">{p.blurb}</p>
              <span className="mt-4 inline-block text-sm text-muted-foreground">
                Ask an admin for access
              </span>
            </div>
          ),
        )}
```

- [ ] **Step 14: Check it renders both states**

Run: `cd apps/console && bun run build && bun run typecheck`
Expected: build succeeds, no type errors.

- [ ] **Step 15: Document the variable**

In `deploy/railway/agents.md`, add to the console environment table:

```markdown
| `AGENT_ENTITLEMENTS` | Who may enter each agent product, as JSON: `{"studio":["@dudaji.vn"],"works":["a@b.c"]}`. An entry is a full address or an `@domain` suffix; `*` is everyone. **Unset ⇒ both products open to every member. Malformed ⇒ both closed.** A product with no list stays open. An `ADMIN` is always entitled. |
```

Also note there that the `nufi-works` entry in `OIDC_CLIENTS` needs `"product": "works"` for the gate to apply to it.

- [ ] **Step 16: Commit**

```bash
git add apps/console/server/lib/entitlements.ts apps/console/server/lib/entitlements.test.ts \
        apps/console/server/enter.ts apps/console/server/enter.test.ts \
        apps/console/server/oidc.ts apps/console/server/oidc.test.ts \
        apps/console/src/routes/choose.tsx deploy/railway/agents.md
git commit -m "feat(console): decide who may enter each agent product"
```

---

### Task 2: Studio session continuity

The `nufi_id` cookie lasts eight hours. When it expires, Studio drops the member on a login screen with a password field they do not have, and the only way back is to remember `agents.nufi.me`. The console door still works — Studio just never knocks on it.

**Files:**
- Modify: `apps/console/server/enter.ts` (`?next=`, HTML-navigation bounce)
- Modify: `apps/console/server/enter.test.ts`
- Modify: `apps/nufi-agent/src/frontend/src/customization/config-constants.ts`
- Modify: `apps/nufi-agent/src/frontend/src/customization/utils/urls.ts`
- Modify: `apps/nufi-agent/src/frontend/src/controllers/API/api.tsx` (the terminal auth path, `api.tsx:120-131`)
- Create: `apps/nufi-agent/src/frontend/src/customization/utils/__tests__/nufi-reentry.test.ts`
- Modify: `apps/nufi-agent/nufi/check-fork-diff.sh` (allowlist the new test)

**Interfaces:**
- Consumes: `isEntitled` from Task 1 (already wired into `/enter/studio` — a re-entry is a fresh entry and is gated the same way).
- Produces:
  - `GET /enter/studio?next=<path>` → redirects to `${STUDIO_URL}${next}` when `next` is a site-relative path, `${STUDIO_URL}/` otherwise.
  - `NUFI_ENTER_URL: string` in `config-constants.ts`
  - `getNufiEnterUrl(pathname: string, search: string): string` in `customization/utils/urls.ts`
  - `shouldReenter(now: number, stamp: string | null): boolean` in `customization/utils/urls.ts`

- [ ] **Step 1: Write the failing console test**

Append to `apps/console/server/enter.test.ts`:

```ts
describe('returning to where the member was', () => {
  it('sends the member back to the path they came from', async () => {
    const res = await as(member).request('/studio?next=%2Fflow%2Fabc', WITH_SESSION);
    expect(res.status).toBe(302);
    expect(res.headers.get('location')).toBe('https://studio.nufi.me/flow/abc');
  });

  it('ignores a next that leaves the site', async () => {
    // "//evil.com" is a protocol-relative URL: it starts with '/' and is
    // still off-site. Rejected outright rather than sanitised.
    const res = await as(member).request('/studio?next=%2F%2Fevil.com', WITH_SESSION);
    expect(res.headers.get('location')).toBe('https://studio.nufi.me/');
  });

  it('ignores an absolute next', async () => {
    const res = await as(member).request('/studio?next=https%3A%2F%2Fevil.com', WITH_SESSION);
    expect(res.headers.get('location')).toBe('https://studio.nufi.me/');
  });

  it('bounces a browser navigation to chat instead of answering JSON', async () => {
    const app = as(member);
    stubChat(null); // after as(), which re-stubs a valid member
    const res = await app.request('/studio', {
      headers: { accept: 'text/html,application/xhtml+xml' },
    });
    expect(res.status).toBe(302);
    expect(res.headers.get('location')).toBe('https://chat.nufi.me/login');
  });

  it('still answers 401 to a scripted caller', async () => {
    // verify-agents.sh asserts exactly this. curl sends Accept: */*.
    const app = as(member);
    stubChat(null); // after as(), which re-stubs a valid member
    const res = await app.request('/studio', { headers: { accept: '*/*' } });
    expect(res.status).toBe(401);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd apps/console && bun test server/enter.test.ts`
Expected: FAIL — `location` is `https://studio.nufi.me/` for the first case, and the HTML case returns 401.

- [ ] **Step 3: Implement both in `enter.ts`**

Add the constant next to the others at the top, and extend the Hono import to
carry the context type the helper below is typed with:

```ts
import { type Context, Hono } from 'hono';

const CHAT_URL = (process.env.CHAT_BASE_URL ?? 'https://chat.nufi.me').replace(/\/+$/, '');
```

Add the two helpers above the route:

```ts
/**
 * Where inside Studio to land. Only a site-relative path is honoured: a
 * protocol-relative "//host" and an absolute URL both start a redirect off
 * this site, so they are dropped rather than repaired -- a half-fixed
 * redirect target is how open redirects get shipped.
 */
function safeNext(next: string | undefined): string {
  if (!next || !next.startsWith('/')) return '/';
  if (next.startsWith('//') || next.startsWith('/\\')) return '/';
  return next;
}

/**
 * A member whose chat session is gone gets sent to sign in; a script gets a
 * status code. The split is on Accept, because `verify-agents.sh` asserts the
 * 401 and a browser must never be shown raw JSON as an answer to a click.
 */
function noSession(c: Context<Env>) {
  if ((c.req.header('accept') ?? '').includes('text/html')) {
    return c.redirect(`${CHAT_URL}/login`, 302);
  }
  return c.json({ error: 'unauthorized', detail: 'could not resolve NUFI identity' }, 401);
}
```

Replace the 401 return in the `/studio` handler with `return noSession(c);`, and the final redirect with:

```ts
  return c.redirect(`${STUDIO_URL}${safeNext(c.req.query('next'))}`, 302);
```

- [ ] **Step 4: Run the console tests**

Run: `cd apps/console && bun test && bun run typecheck`
Expected: PASS.

- [ ] **Step 5: Verify the script's assumption still holds**

Run: `cd apps/console && bun test server/enter.test.ts -t "scripted caller"`
Expected: PASS — this is the assertion `deploy/railway/verify-agents.sh` depends on.

- [ ] **Step 6: Commit the console half**

```bash
git add apps/console/server/enter.ts apps/console/server/enter.test.ts
git commit -m "feat(console): re-enter Studio at the page the member was on"
```

- [ ] **Step 7: Write the failing frontend test**

Create `apps/nufi-agent/src/frontend/src/customization/utils/__tests__/nufi-reentry.test.ts`:

```ts
import { getNufiEnterUrl, shouldReenter } from "../urls";

describe("getNufiEnterUrl", () => {
  it("carries the current location back as ?next=", () => {
    expect(getNufiEnterUrl("/flow/abc", "?tab=1")).toBe(
      "https://console.nufi.me/enter/studio?next=%2Fflow%2Fabc%3Ftab%3D1",
    );
  });

  it("works from the root with no query", () => {
    expect(getNufiEnterUrl("/", "")).toBe(
      "https://console.nufi.me/enter/studio?next=%2F",
    );
  });
});

describe("shouldReenter", () => {
  it("allows a first re-entry", () => {
    expect(shouldReenter(1_000_000, null)).toBe(true);
  });

  it("refuses a second one inside the cooldown", () => {
    // The loop this prevents: console mints a token, Studio rejects it, the
    // frontend bounces back to the console, forever.
    expect(shouldReenter(1_000_000, String(1_000_000 - 5_000))).toBe(false);
  });

  it("allows one again after the cooldown", () => {
    expect(shouldReenter(1_000_000, String(1_000_000 - 31_000))).toBe(true);
  });

  it("allows one when the stamp is garbage", () => {
    expect(shouldReenter(1_000_000, "not-a-number")).toBe(true);
  });
});
```

- [ ] **Step 8: Run it and watch it fail**

Run: `cd apps/nufi-agent/src/frontend && npx jest src/customization/utils/__tests__/nufi-reentry.test.ts`
Expected: FAIL — `getNufiEnterUrl is not a function`.

- [ ] **Step 9: Add the constant**

In `apps/nufi-agent/src/frontend/src/customization/config-constants.ts`, next to `DOCS_LINK`:

```ts
// NuFi: Studio does not own a login of its own -- the console mints the
// identity cookie Studio reads, and it lasts eight hours. When it expires the
// upstream frontend falls through to a local login form with a password field
// no NUFI member has. This is the door back. Baked at build time because the
// console's hostname is stable; override with VITE_NUFI_ENTER_URL for a
// deployment that is not nufi.me.
export const NUFI_ENTER_URL =
  import.meta.env.VITE_NUFI_ENTER_URL ?? "https://console.nufi.me/enter/studio";
```

- [ ] **Step 10: Add the helpers**

In `apps/nufi-agent/src/frontend/src/customization/utils/urls.ts`, extend the existing import from `@/customization/config-constants` with `NUFI_ENTER_URL`, then append:

```ts
const REENTRY_STAMP_KEY = "nufi_reentry_at";
const REENTRY_COOLDOWN_MS = 30_000;

/** The console door, carrying where to land once the identity is renewed. */
export function getNufiEnterUrl(pathname: string, search: string): string {
  return `${NUFI_ENTER_URL}?next=${encodeURIComponent(`${pathname}${search}`)}`;
}

/**
 * Pure so it can be tested without a browser. Guards the one failure mode a
 * redirect-on-auth-failure has: if the console hands back a token Studio still
 * rejects, the two would bounce the member between them without end.
 */
export function shouldReenter(now: number, stamp: string | null): boolean {
  if (!stamp) return true;
  const at = Number(stamp);
  if (!Number.isFinite(at)) return true;
  return now - at > REENTRY_COOLDOWN_MS;
}

/**
 * Send the browser back through the console. Returns false when the cooldown
 * says not to, so the caller can fall through to the normal failure path.
 */
export function redirectToNufiEntry(): boolean {
  let stamp: string | null = null;
  try {
    stamp = window.sessionStorage.getItem(REENTRY_STAMP_KEY);
  } catch {
    // Storage can throw outright in a locked-down browser. A missing stamp
    // means "allowed", which is the same as the first visit.
  }
  if (!shouldReenter(Date.now(), stamp)) return false;
  try {
    window.sessionStorage.setItem(REENTRY_STAMP_KEY, String(Date.now()));
  } catch {
    // Without a stamp the cooldown cannot hold, but a member who cannot store
    // one still deserves the redirect they came for.
  }
  window.location.assign(
    getNufiEnterUrl(window.location.pathname, window.location.search),
  );
  return true;
}
```

- [ ] **Step 11: Run the test and watch it pass**

Run: `cd apps/nufi-agent/src/frontend && npx jest src/customization/utils/__tests__/nufi-reentry.test.ts`
Expected: PASS, 6 tests.

- [ ] **Step 12: Call it from the interceptor**

In `apps/nufi-agent/src/frontend/src/controllers/API/api.tsx`, add to the imports:

```tsx
import { redirectToNufiEntry } from "@/customization/utils/urls";
```

In the `catch` block that follows `await tryToRenewAccessToken(error);` — the branch whose comment reads "Refresh failed (already logged + logout dispatched in the helper)" — insert the redirect before the existing cleanup:

```tsx
          } catch {
            // NuFi: the local refresh is not the only credential here. Studio's
            // session is minted by the console from the member's chat session,
            // so an expired one is renewable without a password -- send the
            // browser back through the door it came in by. The cooldown inside
            // guards against a console that keeps handing back a token Studio
            // rejects.
            if (redirectToNufiEntry()) {
              return Promise.reject(error);
            }
            await clearBuildVerticesState(error);
            return Promise.reject(error);
          }
```

- [ ] **Step 13: Run the API tests**

Run: `cd apps/nufi-agent/src/frontend && npx jest src/controllers/API`
Expected: PASS — including the pre-existing `api-auth-maintenance.test.ts`.

- [ ] **Step 14: Allowlist the new test file in the fork guard**

In `apps/nufi-agent/nufi/check-fork-diff.sh`, add to the `ALLOWLIST` array, next to the other `customization/` entries:

```bash
  "src/frontend/src/customization/utils/__tests__/nufi-reentry.test.ts"
```

- [ ] **Step 15: Run the fork guard**

Run: `apps/nufi-agent/nufi/check-fork-diff.sh`
Expected: exit 0. A non-zero exit naming a path means that path is a fork drift the allowlist does not cover — add it if it is genuinely NuFi-owned, revert it otherwise.

- [ ] **Step 16: Commit the Studio half**

```bash
git add apps/nufi-agent/src/frontend/src/customization/config-constants.ts \
        apps/nufi-agent/src/frontend/src/customization/utils/urls.ts \
        apps/nufi-agent/src/frontend/src/customization/utils/__tests__/nufi-reentry.test.ts \
        apps/nufi-agent/src/frontend/src/controllers/API/api.tsx \
        apps/nufi-agent/nufi/check-fork-diff.sh
git commit -m "fix(studio): renew an expired session instead of asking for a password"
```

---

### Task 3: Verification that runs without being remembered

`deploy/railway/verify-agents.sh` asserts the properties that matter — both products up, carrying the NuFi name, and shut to anonymous callers — and it only runs when someone types it. Every `401` in it is a claim that could quietly become a `200`.

**Files:**
- Create: `.github/workflows/verify-agents.yml`

**Interfaces:**
- Consumes: `deploy/railway/verify-agents.sh` unchanged; it exits non-zero when any check fails (`exit "$fail"`).
- Produces: a scheduled workflow named `verify-agents`, also runnable via `workflow_dispatch`.

- [ ] **Step 1: Run the script against the live surface first**

Run: `deploy/railway/verify-agents.sh`
Expected: every line `OK`, exit 0. If a line already FAILs, fix that before scheduling it — a workflow that is red on its first run gets muted, and a muted alarm is worse than none.

- [ ] **Step 2: Write the workflow**

Create `.github/workflows/verify-agents.yml`:

```yaml
name: verify-agents

# Both agent products are public surfaces held up by properties nothing else
# checks: the white-label build, and three endpoints that must refuse an
# anonymous caller. A refactor can turn any of those 401s into a 200 without
# failing a single unit test, so this runs on a clock rather than on a diff.
on:
  schedule:
    # Every six hours, off the hour: GitHub queues scheduled jobs and a job on
    # the hour waits behind everyone else's.
    - cron: '17 */6 * * *'
  workflow_dispatch:

concurrency:
  group: verify-agents
  cancel-in-progress: true

jobs:
  verify:
    name: Public surface
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Check the script parses
        run: bash -n deploy/railway/verify-agents.sh
      - name: Verify both products
        run: bash deploy/railway/verify-agents.sh
```

- [ ] **Step 3: Check the workflow parses**

Run: `bash -n deploy/railway/verify-agents.sh && yq '.on' .github/workflows/verify-agents.yml`
Expected: the script parses silently, and yq prints the `schedule`/`workflow_dispatch` block — which is also the proof the YAML parses. Do not pipe yq into `grep -q`: under `set -o pipefail` a match exits 141.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/verify-agents.yml
git commit -m "test(deploy): check the agent products on a clock, not on memory"
```

- [ ] **Step 5: Dispatch it once on `main` and read the log**

After the branch merges: Actions → `verify-agents` → *Run workflow*.
Expected: green, with the same `OK` lines the local run produced. A scheduled workflow only becomes active from the default branch, so this run is also the proof it is wired.

---

### Task 4: A screenshot guard, and a refresh

The docs build fails when a page references a screenshot that is not there — but only at build time, with an error that names the page rather than the missing file. The screenshots themselves drift as the products change.

**Files:**
- Create: `apps/docs/scripts/check-screenshots.mjs`
- Modify: `apps/docs/package.json` (add `check:screenshots`)
- Modify: `.github/workflows/docs-ci.yml`
- Modify: `apps/docs/public/screenshots/*.png` (whatever the refresh actually changes)

**Interfaces:**
- Produces: `bun run check:screenshots` in `apps/docs/` — exit 0 when every referenced screenshot exists, exit 1 with one line per missing file.

- [ ] **Step 1: Write the checker**

Create `apps/docs/scripts/check-screenshots.mjs`:

```js
/**
 * Every /screenshots/... a page references must exist.
 *
 * The Next build already fails on a missing image, but it fails deep inside a
 * render with a message that names the page and not the file. This says which
 * file, in one line, before the build starts.
 */
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const CONTENT = join(root, 'content', 'docs');
const SHOTS = join(root, 'public', 'screenshots');

function mdxFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return mdxFiles(full);
    return entry.name.endsWith('.mdx') ? [full] : [];
  });
}

const missing = [];
for (const file of mdxFiles(CONTENT)) {
  const body = readFileSync(file, 'utf8');
  for (const [, name] of body.matchAll(/\/screenshots\/([A-Za-z0-9._-]+)/g)) {
    if (!existsSync(join(SHOTS, name))) {
      missing.push(`${file.slice(root.length + 1)} -> /screenshots/${name}`);
    }
  }
}

if (missing.length > 0) {
  console.error('Missing screenshots:');
  for (const line of new Set(missing)) console.error(`  ${line}`);
  console.error(`\n${missing.length} reference(s) with no file. Run \`bun run screenshots\`.`);
  process.exit(1);
}

console.log('All referenced screenshots exist.');
```

- [ ] **Step 2: Prove it catches a missing file**

Run:
```bash
cd apps/docs
node scripts/check-screenshots.mjs                       # expect: all exist
printf '\n![probe](/screenshots/does-not-exist.png)\n' >> content/docs/index.mdx
node scripts/check-screenshots.mjs                       # expect: exit 1, names the file
git checkout content/docs/index.mdx
```
Expected: the second run prints `content/docs/index.mdx -> /screenshots/does-not-exist.png` and exits 1.

- [ ] **Step 3: Add the script entry**

In `apps/docs/package.json`, add to `scripts`:

```json
    "check:screenshots": "node scripts/check-screenshots.mjs",
```

- [ ] **Step 4: Run it through the package script**

Run: `cd apps/docs && bun run check:screenshots`
Expected: `All referenced screenshots exist.`

- [ ] **Step 5: Wire it into CI ahead of the build**

In `.github/workflows/docs-ci.yml`, insert a step between *Install dependencies* and *Build*:

```yaml
      # Named before the build so a missing image reads as "this file, from
      # this page" rather than as a render stack trace.
      - name: Check screenshots
        run: bun run check:screenshots
```

- [ ] **Step 6: Refresh the screenshots**

Run: `cd apps/docs && bun run screenshots`
(Requires the capture credentials and the live surfaces — see the `screenshots-playwright.md` note; the script signs in and drives the real products.)

Then review every changed file before staging:

```bash
git status --short apps/docs/public/screenshots/
```

Keep a changed shot only when the product genuinely changed. Discard churn — a re-render with a different cursor position or a one-pixel scroll offset is noise in the diff and in every future review:

```bash
git checkout -- apps/docs/public/screenshots/<unchanged-looking-file>.png
```

- [ ] **Step 7: Build the docs**

Run: `cd apps/docs && bun run build`
Expected: build succeeds.

- [ ] **Step 8: Commit**

```bash
git add apps/docs/scripts/check-screenshots.mjs apps/docs/package.json \
        .github/workflows/docs-ci.yml apps/docs/public/screenshots
git commit -m "test(docs): name the missing screenshot before the build trips over it"
```

---

### Task 5: The sandbox cluster decision

Agents in NUFI Works cannot run for real yet. This is not a missing sandbox: `apps/agents/server/src/services/environments.ts` already ships a first-party Kubernetes sandbox provider (`KUBERNETES_PROVIDER_KEY = "kubernetes"`), and `execution-policy-bootstrap.ts` already forces a policy with a gVisor `runtimeClass` and `PAPERCLIP_K8S_EGRESS_MODE=cilium`. What is missing is a cluster that can honour those two words. That is a provider decision, and it is the last thing standing between Works being a signed-in demo and Works doing work.

This task produces a document, not a diff. It ends with a recommendation someone can act on, not a survey.

**Files:**
- Create: `docs/2026-09-05-works-sandbox-cluster-decision.md`

**Interfaces:**
- Consumes: `apps/agents/server/src/services/execution-policy-bootstrap.ts` (the `PAPERCLIP_K8S_*` contract), `apps/agents/server/src/services/environments.ts:35-60`, and `docs/2026-08-04-nufi-agents-spike-findings.md`.
- Produces: a decision doc whose "Recommendation" section names one provider, with the numbers it was chosen on.

- [ ] **Step 1: Extract the requirements from the code, not from memory**

Run:
```bash
cd apps/agents/server/src
grep -n "PAPERCLIP_K8S_[A-Z_]*" services/execution-policy-bootstrap.ts
sed -n '35,80p' services/environments.ts
grep -rn "gvisor\|runtimeClass\|egressMode" services/ __tests__/ | grep -v node_modules
```

Write down, verbatim, what the cluster must provide. Expect at least: a `runtimeClass` the operator can name (gVisor), Cilium as the CNI so `egressMode: "cilium"` is enforceable rather than decorative, per-tenant namespaces (`PAPERCLIP_K8S_NAMESPACE_PREFIX`), a reachable image registry (`PAPERCLIP_K8S_IMAGE_REGISTRY`), and in-cluster credentials (`PAPERCLIP_K8S_IN_CLUSTER`).

- [ ] **Step 2: Write the requirements section**

Create `docs/2026-09-05-works-sandbox-cluster-decision.md` and open it with what the code demands, each line citing the file it came from:

```markdown
# Where the NUFI Works sandbox runs

NUFI Works ships a Kubernetes sandbox provider and a forced execution policy;
neither has a cluster to run on. This picks one.

## What the cluster must provide

| Requirement | Where it comes from | Why it is not negotiable |
|---|---|---|
| A named `runtimeClass` (gVisor) | `execution-policy-bootstrap.ts` (`PAPERCLIP_K8S_RUNTIME_CLASS_NAME`) | Agent code is untrusted; a shared kernel is the boundary being defended. |
| Cilium as the CNI | `execution-policy-bootstrap.ts` (`PAPERCLIP_K8S_EGRESS_MODE=cilium`) | The gateway-only egress invariant is enforced by network policy or it is enforced by nothing. |
| Per-tenant namespaces | `environments.ts` (`PAPERCLIP_K8S_NAMESPACE_PREFIX`) | One company's run must not see another's. |
| A reachable image registry | `execution-policy-bootstrap.ts` (`PAPERCLIP_K8S_IMAGE_REGISTRY`) | Runs pull an image per environment. |
```

- [ ] **Step 3: Score the candidates against those rows**

Add a comparison table. Candidates to cover, each judged on whether it can run gVisor and Cilium at all, then on idle cost, ops burden, and time to a first agent run:

- **Managed with a custom CNI** (GKE Standard with Cilium / Dataplane V2, EKS with the Cilium chart)
- **Managed but locked** (GKE Autopilot, Railway) — record explicitly whether a custom `runtimeClass` and CNI are even possible; if not, that is a disqualification, not a low score
- **Self-managed on rented metal** (Hetzner or equivalent + k3s + Cilium + gVisor)
- **A sandbox-as-a-service** (Firecracker microVM vendors) — note that using one means not using the shipped Kubernetes provider, so it costs code as well as money

For each: idle cost per month at zero runs, cost at a realistic weekly demo load, and who operates it.

- [ ] **Step 4: Write the recommendation**

One provider. State the two runners-up and the specific number or capability that lost them the decision. Then the shape of the follow-up work: which `PAPERCLIP_K8S_*` values the deployment sets, how the cluster gets its Cilium egress policy, and what the first end-to-end agent run has to demonstrate before this is called done.

Do not hedge. A comparison table with no choice at the bottom is the same as not having written it.

- [ ] **Step 5: Check it against the constraint it exists to protect**

Re-read `docs/2026-08-04-nufi-agents-spike-findings.md` §1 ("the traffic is not merely routed, it is inspected"). If the recommended provider cannot enforce gateway-only egress, the recommendation is wrong regardless of price — say so in the doc and pick again.

- [ ] **Step 6: Commit**

```bash
git add docs/2026-09-05-works-sandbox-cluster-decision.md
git commit -m "docs: where the NUFI Works sandbox runs, and what it costs"
```

---

## Sequencing

Three working days, in this order:

| Day | Tasks | Why this order |
|---|---|---|
| 1 | Task 1 | Everything else is smaller; the gate touches two routes and the chooser and deserves the fresh day. Task 2's console half reuses its test scaffolding. |
| 2 | Task 2, then 3, then 4 | Task 2 spans two apps and the fork guard, so it goes first while there is room to be wrong. Tasks 3 and 4 are guards — they are quick, and having them running before the week ends is the point of them. |
| 3 | Task 5 | Reading and deciding, which does not interleave well with a test cycle. |

Tasks 1 and 2 both touch `apps/console/server/enter.ts`. If they are given to parallel workers, isolate each in its own worktree; otherwise do them in sequence on one branch.

---

## Self-review

**Spec coverage.** The five items from the report table map to Tasks 1–5 one for one. The two deferrals named in `2026-08-26-nufi-agents-cloud.md` §"Not in this plan" that this plan does *not* close are stated there and remain open: **entitlements beyond an allowlist** (no invite flow, no admin UI — this plan gives ops an env var, not a screen) and **the sandbox cluster itself** (Task 5 decides the provider; building it is the next plan).

**Placeholders.** None. Every code step carries the code; every run step carries the command and what it should print.

**Type consistency.** `Product` is declared once in `entitlements.ts` and imported by `oidc.ts`; `isEntitled` takes `{ email, role }`, which `ChatIdentity` structurally satisfies. `getNufiEnterUrl(pathname, search)` is called with exactly two arguments in `redirectToNufiEntry`, and `shouldReenter(now, stamp)` matches its test. `safeNext` and `noSession` are local to `enter.ts` and used only there.

**One risk worth naming.** Task 2's redirect fires on the terminal auth path in a file the fork shares with upstream (`api.tsx`). If a resync changes that branch, the redirect is the first thing to re-verify — the failure mode is silent (a member sees the old login form again), not loud.
