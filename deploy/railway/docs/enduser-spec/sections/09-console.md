## NuFi Console

### Overview & access

The NuFi Console is a self-service developer portal, separate from the chat application, that lets end users manage their own LiteLLM API keys, monitor their spend, and view usage analytics. In production it is served at **https://console.nufi.me** (requires manual verification on the running product: deployment-level hostname binding, not hardcoded in source). (Internally it is a single-container service — Hono + Vite SPA — deployed alongside NuFi Chat; testers only need the public URL.)

**How users reach it:** A "Console" link in the LibreChat account menu deep-links the browser to the console origin. Because LibreChat sets the `refreshToken` cookie on the shared parent domain (e.g. `localhost`), the cookie is automatically present on the console port — no extra sign-in step is needed for authenticated chat users.

**Authentication model:** The console trusts the LibreChat-issued JWT. It accepts two token sources in order: (1) `Authorization: Bearer <access_token>` header verified with `JWT_SECRET` (HS256) — used by service clients; (2) the `refreshToken` cookie verified with `JWT_REFRESH_SECRET` (HS256) — the normal browser path. The user's LibreChat `id` extracted from the JWT payload becomes the canonical identity across LiteLLM and Langfuse records. A valid token produces an `AuthedUser` object with `id`, optional `email`, and `role` (`USER` or `ADMIN`).

**JIT provisioning:** On the first API call the console makes on behalf of a newly-authenticated user, it calls `ensureLiteLLMUser`, which checks for a matching LiteLLM Internal-User record via `GET /user/info?user_id=…`. If none exists, it issues `POST /user/new` to create one with default caps: `max_budget = $10`, `budget_duration = 30d`, `tpm_limit = 10 000`, `rpm_limit = 60` (all overridable via environment variables). This is idempotent — safe to call on every request.

**Unauthorized flow:** When any API call returns HTTP 401, the SPA redirects to the `/unauthorized` route, which shows the message "Sign in required" with explanatory copy and an "Open chat" button that deep-links to the LibreChat URL (configured via `VITE_LIBRECHAT_URL`, defaulting to `http://localhost:3080`).

**Navigation:** A persistent header bar contains the NUFI logo, the app name "NUFI Console", and three nav links: **Profile**, **Usage**, and **API keys**. A theme toggle (light/dark) appears on the right. Toast notifications appear bottom-right.

---

### Authentication & Session

**Purpose:** Verify that the user has an active LibreChat session before granting access to any console feature. Prevent cross-user data access.

**Preconditions / access:** The user must have previously signed in to LibreChat, which sets the `refreshToken` cookie on the shared domain.

**UI elements:** No explicit login form in the console itself. The `/unauthorized` page shows: heading "Sign in required"; paragraph "The console reuses your chat session. Sign in there first, then come back to this tab."; button "Open chat".

**Functional behavior:**

- FR-1. On every `/rpc/*` request, the server middleware reads the `Authorization` header first. If a valid Bearer token is present and verifiable with `JWT_SECRET`, the request is authenticated via the access-token path.
- FR-2. If no valid Bearer token is found, the middleware reads the `refreshToken` cookie and verifies it with `JWT_REFRESH_SECRET`. If valid, the request is authenticated via the refresh-token path.
- FR-3. If neither token is present or both fail cryptographic verification, the server returns HTTP 401 `{"error":"unauthorized"}`.
- FR-4. The server extracts the user `id` from JWT claim keys `id`, `userId`, `_id`, or `sub` (checked in that order). If none resolves to a non-empty string, a 401 is returned.
- FR-5. The user's `role` is set to `ADMIN` only if the JWT claim `role` equals `"ADMIN"`; all other values (including missing) default to `USER`.
- FR-6. The SPA detects 401 responses via `isUnauthorized` (checks `err instanceof ORPCError && err.code === 'UNAUTHORIZED'`) and navigates to `/unauthorized`. The check applies on every page: Profile, API Keys, and Usage. For 401s thrown inside oRPC handlers the mapping is direct; whether the Hono middleware's bare HTTP 401 JSON response is also mapped to `ORPCError.code === 'UNAUTHORIZED'` by the `@orpc/client` fetch adapter (requires manual verification on the running product: confirm the Hono-level 401 path surfaces as `isUnauthorized === true` in the SPA).
- FR-7. On the `/unauthorized` page, clicking "Open chat" navigates the browser (full page load) to the LibreChat URL. After signing in the user may return to the console tab, which will retry using the newly set cookie.

**States & edge cases:**

- Missing JWT secrets on the server: returns HTTP 500 `{"error":"server_misconfigured","detail":"JWT secrets missing"}` — the user sees a generic error, not the unauthorized page.
- Access token expired but refresh token valid: refresh path authenticates the session normally. (Note: the refresh token is not rotated or re-validated against LibreChat's session store in this version — revocation lag is a known limitation.)
- Both tokens missing (completely fresh browser / incognito with no prior LibreChat login): immediate redirect to `/unauthorized`.

**Acceptance criteria:**

- AC-1. Given a browser that has previously signed in to LibreChat (cookie present), when the user opens the console, then the Profile page loads without redirect.
- AC-2. Given no `refreshToken` cookie and no Authorization header, when the user opens any console page, then the browser is redirected to `/unauthorized` and the "Open chat" button is visible.
- AC-3. Given `JWT_SECRET` is not set on the server, when the console makes any API call, then the server returns HTTP 500 and no user data is exposed.
- AC-4. Given an `ADMIN` role in the JWT, when the user loads any page, then their `role` badge on the Profile page reads "ADMIN".

---

### First-Open Provisioning (JIT)

**Purpose:** Automatically create a LiteLLM user account for every LibreChat user on their first console visit, without requiring manual admin setup.

**Preconditions / access:** User is authenticated. A LiteLLM record for this user does not yet exist.

**UI elements:** No dedicated UI — provisioning is invisible. The Profile page loads with the provisioned values reflected immediately.

**Functional behavior:**

- FR-1. The `me.get` procedure calls `ensureLiteLLMUser` synchronously (alongside parallel calls to `getCustomer` and `listKeysForUser`) on every Profile page load.
- FR-2. `ensureLiteLLMUser` calls `GET /user/info?user_id=<id>`. If the LiteLLM API returns HTTP 404, or HTTP 400 with a body containing the word "not found" (variant seen in some LiteLLM versions), the user is considered new.
- FR-3. For a new user, `POST /user/new` is called with: `user_id` = LibreChat `id`; `user_email` = email from JWT (if present); `user_role` = `proxy_admin` for ADMIN-role users, `internal_user` for USER-role users; `max_budget = $10` (env: `DEFAULT_USER_BUDGET`); `budget_duration = 30d` (env: `DEFAULT_BUDGET_DURATION`); `tpm_limit = 10 000` (env: `DEFAULT_TPM_LIMIT`); `rpm_limit = 60` (env: `DEFAULT_RPM_LIMIT`).
- FR-4. The returned `LiteLLMUserInfo` is used directly for `limits.*` fields in the `me.get` response; no second round-trip is made.
- FR-5. The call is idempotent: if the user already exists in LiteLLM, `getUser` returns the existing record and `createUser` is never called.

**States & edge cases:**

- LiteLLM unreachable during provisioning: the `me.get` call throws; the Profile page shows "Error: \<message\>". No partial state is written.
- Provisioning succeeds but `user_email` is absent from the JWT: the LiteLLM record is created without an email; the Profile page displays the user ID as the identity string.
- Re-entrant provisioning (two tabs opened simultaneously on first visit): both calls hit `getUser` before either `createUser` completes; one may create a duplicate. LiteLLM's `POST /user/new` idempotency behavior determines the outcome (verify: behavior depends on LiteLLM version).

**Acceptance criteria:**

- AC-1. Given a LibreChat user who has never opened the console, when they navigate to the Profile page, then no error is shown and the budget/limits section displays the default values (`$10` max budget, `30d` period, `10K` tok/min, `60` req/min).
- AC-2. Given a user who already has a LiteLLM account, when they open the Profile page, then their existing budget and spend values are displayed (not reset to defaults).
- AC-3. Given LiteLLM is down, when the Profile page loads, then an error message is displayed and no budget card is shown.

---

### Profile Page

**Purpose:** Give the user a high-level overview of their identity, remaining budget, spend breakdown, key inventory summary, and a 7-day daily spend chart — the "dashboard at a glance".

**Preconditions / access:** User is authenticated. JIT provisioning has completed. Reached via the "Profile" nav link or the root URL `/`.

**UI elements:**

- Heading: `Hi 👋` (h1, `text-3xl font-semibold`)
- Identity line: monospace email address (or user ID if email absent), followed by a `Badge` showing the user's role (`USER` or `ADMIN`).
- **Available Hero card** (full-width, rounded): displays either:
  - With budget: heading "Available · next \<period\>" (period resolved from `budgetDuration`: `24h` → "24 hours", `7d` → "7 days", `30d` → "30 days"); large monospace remaining-balance figure; sub-label "of \<maxBudget\>"; a horizontal progress bar; footer row with "\<spent\> used (\<pct\>%)" on the left and a status label ("Healthy" / "Running low" / "Almost out") on the right.
  - Without budget (`max_budget = null`): heading "You have unlimited usage"; large monospace total spend; sub-label "used so far".
- **Usage Chart card**: heading "Last 7 days"; request count and total cost in the header right. A bar chart with one column per UTC day (square-root-scaled heights, non-zero days floored at 15% height). Peak day highlighted in a stronger color. Footer shows "Peak day: \<day\> · \<amount\>" and "Last request: \<relative time\>".
- **Spend Breakdown card** ("Where it goes"): two rows — "Chat conversations" (primary color swatch) and "Direct API calls" (blue swatch) — each showing USD amount and percentage of total. If total spend is $0.00: "You haven't used anything yet this period."
- **Your Keys card**: up to 5 top-spending keys shown as a ranked horizontal-bar list. Each row: alias (or `unnamed` — no parentheses, as rendered by `top-keys-card.tsx`), masked token (first 3 + last 4 chars), and USD spend. "View all (N) →" link to the API Keys page. If no keys exist: "You don't have any API keys yet. Generate one." Note: the Key Table (separate component) renders unnamed keys as `(unnamed)` with parentheses — the two components intentionally differ.
- **Per-minute limits card** ("Per-minute limits"): two stat rows — "tokens / minute" (TPM limit) and "requests / minute" (RPM limit), formatted with compact notation (e.g. `10K`). A `null` limit renders as `∞`.
- **Skeleton loaders** are displayed for all sections while `me.get` is pending.

**Functional behavior:**

- FR-1. On mount, the SPA issues two parallel queries: `me.get` (returns identity + spend + limits + top keys) and `usage.daily` with `{ days: 7 }` (returns daily spend series).
- FR-2. `me.get` aggregates spend from three LiteLLM sources: the Customer (End-User) row for chat traffic (`customer.spend`), and the sum of `spend` across all the user's issued keys. Total spend = chat spend + issued-keys spend.
- FR-3. Budget progress thresholds: ≥ 90% spend → destructive (red) bar + "Almost out" label; ≥ 70% → amber bar + "Running low"; below 70% → primary bar + "Healthy".
- FR-4. When `limits.maxBudget` is `null`, the Available Hero renders the unlimited variant.
- FR-5. If `me.get` fails with a non-401 error, a paragraph `"Error: <message>"` is rendered in destructive color; all cards are hidden.
- FR-6. If `me.get` fails with 401, the SPA navigates to `/unauthorized`.
- FR-7. The 7-day chart uses `usage.daily` data; it renders the skeleton while pending and falls back to empty series / zero values if the query has not yet resolved.

**States & edge cases:**

- Zero total spend: AvailableHero shows "$0.00 used (0%)", bar is empty, SpendBreakdown shows the zero-state message.
- Budget exactly at 100%: bar is full red, status "Almost out", remaining balance "$0.00".
- No keys: TopKeysCard shows the "Generate one" prompt; `keysCount = 0`.
- Email missing from JWT: identity line displays the user ID in monospace.
- LiteLLM `budget_duration` value not in the display map: rendered literally (e.g. `90d` displays as `90d`).

**Acceptance criteria:**

- AC-1. Given a user with `max_budget = 10`, `spend = 3.50`, `budget_duration = 30d`, when the Profile page loads, then the hero card shows "Available · next 30 days", remaining balance "$6.50", "of $10.00", bar at 35%, status "Healthy".
- AC-2. Given spend ≥ 90% of budget, when the Profile page loads, then the progress bar is red (destructive) and the status label reads "Almost out". (At 80% the bar is amber, not red — red only triggers at ≥ 90%.)
- AC-3. Given `max_budget = null`, when the Profile page loads, then the hero card shows "You have unlimited usage" with total spend displayed.
- AC-4. Given `usage.daily` resolves with data, when the chart renders, then each day column appears and the peak day column is visually distinct (full-opacity primary color).
- AC-5. Given the user has issued keys, when the Profile page loads, then the "Your keys" card lists up to 5 keys ranked by spend (highest first) with masked tokens.
- AC-6. Given the user is pending provisioning, when the profile skeleton is shown, then no real data values are displayed and no error is shown.

---

### API Keys — List / Table

**Purpose:** Show the user all their active LiteLLM API keys in a sortable table with per-key spend, budget, rate limits, creation date, and expiry, plus aggregate summary statistics.

**Preconditions / access:** User is authenticated. Reached via the "API keys" nav link (`/keys`).

**UI elements:**

- Page heading: "API keys" (h1, `text-3xl font-semibold`).
- Sub-heading: "Each key has its own budget and rate limits. Use them to call the API from your code."
- **"Generate Key" button** (visible only when at least one key exists): `Plus` icon + label "Generate Key", top-right of the header row.
- **Keys Summary bar** (4 stat cards, visible when keys exist):
  - "Active keys" — total count.
  - "Used across keys" — sum of all key spend in USD.
  - "Total budget" — sum of all `max_budget` values in USD (or "—" if all are null); hint shows "\<spent\> of \<total\>".
  - "Expiring this week" — count of keys with an expiry within 7 days; displayed in amber when > 0.
- **Key Table** (visible when keys exist): columns:
  - **Name** — alias (bold) on first line; masked token (`first 3 chars…last 4 chars` of the `token` field) in `font-mono text-[11px]` on second line. If alias is null, `(unnamed)` in muted color.
  - **Usage** — current spend in USD; "of \<maxBudget\> · \<budgetDuration\>" when a budget is set. A 32 px-wide mini progress bar below (color: primary ≤70%, amber 70–89%, destructive ≥90%).
  - **Limits** (hidden on small screens, visible at md): two `Badge` elements — TPM limit in compact notation with "tok/min" label; RPM limit with "req/min" label.
  - **Created** (hidden below lg): formatted date (e.g. "Jun 10, 2026").
  - **Expires** (hidden below lg): formatted date, or italic "never" if `expires` is null.
  - Unnamed action column: a ghost `Trash2` icon button with `aria-label="Revoke key"`.
- **Empty state** (shown when the user has no keys): full-width card with centered content — icon, heading "Welcome — let's create your first key", descriptive paragraph, a 3-step explainer ("Generate", "Use it", "Track usage"), a sample `curl` snippet using `VITE_LITELLM_URL` and the first available model name, and a large "Generate your first key" button.
- **Skeleton** displayed while the list query is pending.

**Functional behavior:**

- FR-1. On mount, `keys.list` is queried. For `USER` role, only keys belonging to the authenticated user (`/key/list?user_id=…`) are returned. For `ADMIN` role, all keys from `/key/list` are returned.
- FR-2. The masked token value is derived from the `token` field (the hashed key identifier safe to expose), not the raw `sk-…` secret.
- FR-3. Budget progress bar colors: primary (blue) below 70%, amber 70–89%, destructive (red) at 90%+.
- FR-4. If `max_budget` is null, no budget string and no progress bar are rendered for that row.
- FR-5. If `expires` is null, the Expires column renders italic "never".
- FR-6. "Expiring this week" counts keys where `expires` is set and the expiry timestamp is within 7 days from now (but not already past).
- FR-7. On a 401 error from `keys.list`, the SPA navigates to `/unauthorized`.
- FR-8. On a non-401 error, an inline error paragraph `"Error: <message>"` is rendered.

**States & edge cases:**

- No keys: empty-state card is shown; "Generate Key" button is absent from the header (the empty-state card has its own "Generate your first key" button instead).
- All keys have null budget: "Total budget" summary card shows "—" with hint "No caps set".
- Key with spend exactly at `max_budget`: progress bar at 100% width in destructive color.
- `token` field shorter than 8 characters: mask function returns the value unchanged.
- ADMIN user: sees all users' keys in the table (verify: admin-specific display treatment such as showing `userId` per row is not implemented in the current table — only the data scope differs).

**Acceptance criteria:**

- AC-1. Given a user with 2 keys, when the Keys page loads, then the table shows 2 rows and the "Active keys" summary card shows "2".
- AC-2. Given a key with `spend = 8`, `max_budget = 10`, when the table row renders, then the Usage column shows "$8.00 of $10.00" and the progress bar is amber (80% falls in the ≥70% amber band; the bar only turns red/destructive at ≥90%).
- AC-3. Given a key with `expires` = null, when the table row renders, then the Expires column shows "never" in italic.
- AC-4. Given no keys exist, when the Keys page loads, then the empty-state card is shown, the summary bar is absent, the table is absent, and the "Generate Key" button in the header is absent.
- AC-5. Given the `keys.list` call returns 401, when the Keys page loads, then the browser navigates to `/unauthorized`.
- AC-6. Given a key expiring in 3 days, when the Keys page loads, then the "Expiring this week" summary card shows "1" in amber.

---

### Create / Generate API Key

**Purpose:** Allow the user to generate a new LiteLLM API key with a custom alias, budget, rate limits, and expiry duration.

**Preconditions / access:** User is authenticated. User opens the "Generate Key" modal from either the header button (when keys exist) or the "Generate your first key" button in the empty state. Modal is controlled by the `generateOpen` flag in the Zustand UI store.

**UI elements (dialog "Generate API key"):**

- Dialog title: "Generate API key".
- Dialog description: "Use this key to call the LiteLLM proxy directly. The full value is shown once after creation."
- **Alias** field (`Label` "Alias", `Input` id="alias", placeholder "e.g. my-laptop", `required`, `maxLength=64`). Default: empty.
- **Max budget (USD)** field (`Label` "Max budget (USD)", `Input` id="budget", `type="number"`, `min=0.01`, `step=0.01`). Default: `10`.
- **Budget period** selector (`Label` "Budget period", `Select`). Options: `24h`, `7d`, `30d`. Default: `30d`.
- **TPM limit** field (`Label` "TPM limit", `Input` id="tpm", `type="number"`, `min=1`, `step=1`). Default: `10000`.
- **RPM limit** field (`Label` "RPM limit", `Input` id="rpm", `type="number"`, `min=1`, `step=1`). Default: `60`.
- **Expires** selector (`Label` "Expires", `Select`). Options: `in 7d`, `in 30d`, `in 90d`, `in 180d`, `in 365d`, `Never`. Default: `90d`.
- Footer buttons: ghost "Cancel" (closes modal, no mutation) and primary "Generate" (submits). "Generate" is disabled when the `alias` field is empty or the mutation is in-flight; label changes to "Generating…" while pending.

**Functional behavior:**

- FR-1. Clicking "Generate" submits the form, calling the `keys.create` mutation with: `alias` (trimmed), `maxBudget` (parsed float), `budgetDuration`, `tpmLimit` (parsed int), `rpmLimit` (parsed int), `duration` (the key lifetime; the value `never` is sent as `undefined` to LiteLLM so no expiry is set).
- FR-2. Server-side validation enforces: `alias` 1–64 chars (required). All other fields are optional on the wire — if omitted the server applies the same defaults as JIT provisioning: `maxBudget` positive ≤ 10 000 (default $10); `budgetDuration` one of `24h|7d|30d` (default `30d`); `tpmLimit` positive integer ≤ 10 000 000 (default 10 000); `rpmLimit` positive integer ≤ 100 000 (default 60); `duration` one of `7d|30d|90d|180d|365d|never`. Validation rules apply only when the field is present; absent fields use server defaults.
- FR-3. On success, the server returns `{ key: "sk-…", view: KeyView }`. The SPA: (a) stores `{ alias, key }` in the Zustand `revealedKey` state, which closes the generate modal and opens the reveal-once modal; (b) invalidates the `keys.list` query so the table refreshes; (c) shows a success toast `Key "<alias>" generated`; (d) resets all form fields to defaults.
- FR-4. On error, a toast `"Could not generate key: <message>"` is shown; the modal remains open.
- FR-5. The "Cancel" button closes the modal without mutation and without resetting form state (state resets only on successful creation).

**States & edge cases:**

- Empty alias: "Generate" button is disabled; form submission cannot proceed.
- Alias of only whitespace: after `.trim()`, the alias is empty and the server rejects it with a validation error.
- Budget or limit fields left blank: the browser blocks submission before the form reaches JavaScript — all three fields (`budget`, `tpm`, `rpm`) carry the HTML5 `required` attribute so the browser prevents an empty submit natively. The `Number("")` → `0` / server `positive()` rejection path is not reached via normal UI interaction.
- LiteLLM returns an error (e.g. budget exceeds admin cap): toast shows the server error message.
- Concurrent generate: the button is disabled while pending so duplicate submissions are prevented.

**Acceptance criteria:**

- AC-1. Given the Generate dialog is open, when the user leaves the Alias field empty, then the "Generate" button is disabled and cannot be clicked.
- AC-2. Given valid form values, when the user clicks "Generate", then the button label becomes "Generating…", the button is disabled, and on success the dialog closes and the reveal modal opens.
- AC-3. Given a successful key creation, when the keys page re-renders, then the new key appears in the table.
- AC-4. Given a server validation error, when the create call returns, then a toast "Could not generate key: …" is shown and the dialog stays open.
- AC-5. Given the "Cancel" button is clicked, when the dialog closes, then no key is created and the keys list is unchanged.

---

### Reveal-Once Secret Modal

**Purpose:** Display the full `sk-…` API key value immediately after generation — the only time the secret is accessible. After the modal is dismissed, the secret cannot be retrieved.

**Preconditions / access:** The `revealedKey` Zustand state is populated (set by a successful `keys.create` call). This modal renders at the `/keys` route level and is visible over the key table.

**UI elements (dialog "Save your new key"):**

- Dialog title: "Save your new key".
- Dialog description: "Copy it now — you won't see the full value again. Treat it like a password."
- **Key alias label**: small uppercase monospace label showing the key alias.
- **Key display box**: a muted bordered container with the full `sk-…` value in `font-mono text-sm` (truncated if overflowing). A "Copy" button with a `Copy` icon on the right; icon and label change to a `Check` + "Copied" for 2 seconds after a successful clipboard write.
- **"How to use it" section**: a `Tabs` component with three tabs:
  - **curl** — a `curl` snippet using `VITE_LITELLM_URL` (env, default `http://localhost:4000`) and the first model ID from the `models.list` query (falling back to `qwen2.5-3b` if the query has not resolved).
  - **Python** — an `openai`-SDK Python snippet.
  - **JavaScript** — an `openai`-SDK JavaScript/ESM snippet.
  - Each tab has a "Copy" button (top-right of the code block) that copies the full snippet text and shows "Copied" for 2 seconds.
- **"I've saved it" button** (footer, primary): dismisses the modal and clears `revealedKey` from the store.

**Functional behavior:**

- FR-1. The modal renders as soon as `revealedKey` is non-null in the Zustand store; it is not re-openable after it is cleared.
- FR-2. Closing the dialog via the `×` button or pressing Escape calls `clear()`, which sets `revealedKey` to `null`. The key is gone from the store and cannot be retrieved.
- FR-3. Copying the key text calls `navigator.clipboard.writeText`. On success, a toast "Key copied to clipboard" is shown. On clipboard API failure, a toast "Clipboard write failed — copy manually" is shown.
- FR-4. Copying a code snippet calls `navigator.clipboard.writeText` with the full snippet string. On success, a toast "Snippet copied" is shown.
- FR-5. The `models.list` query is fetched (with a 5-minute stale time) only when the modal is visible (`enabled: !!revealed`). The first returned model ID is inserted into all three snippets.
- FR-6. The tab active by default is "curl".

**States & edge cases:**

- Clipboard API unavailable (insecure context / denied permission): toast "Clipboard write failed — copy manually" appears; the key text remains visible for manual selection and copy.
- `models.list` query not yet resolved: snippets use the fallback model name `qwen2.5-3b`.
- User dismisses immediately without copying: the key is lost. No recovery path exists in the UI.
- Page refresh while modal is open: the Zustand store is in-memory; a refresh clears it, so the key is irrecoverable.

**Acceptance criteria:**

- AC-1. Given a key was just generated, when the reveal modal appears, then the full `sk-…` value is visible in the key display box.
- AC-2. Given the modal is open, when the user clicks "Copy" next to the key, then the clipboard contains the full key value, the button label becomes "Copied", and a success toast is shown.
- AC-3. Given the user clicks "I've saved it", when the modal closes, then the key is no longer accessible in the UI and the key table is visible.
- AC-4. Given the user presses Escape or clicks the dialog close button, then the modal closes and the key is cleared from state.
- AC-5. Given the modal is open and `models.list` has resolved, when the user switches to the Python tab, then the snippet contains the first model's ID (not the fallback string).
- AC-6. Given a successful copy, when 2 seconds elapse, then the "Copy" button reverts to its default icon and label.

---

### Key Info / Usage Details

**Purpose:** Return the full detail record for a specific key (alias, token, spend, budget, rate limits, created date, expiry) for display inline in the table or for future detail views.

**Preconditions / access:** Requires an authenticated session. The key's `token` field (safe identifier) is required. A `USER` can only inspect keys they own; an `ADMIN` can inspect any key.

**UI elements:** No dedicated full-page key-detail view exists in the current SPA. Key details are surfaced inline in the Key Table rows (see API Keys — List / Table section). The `keys.info` procedure is available as an API endpoint for programmatic use.

**Functional behavior:**

- FR-1. `keys.info` accepts `{ token: string }` (minimum 1 character). It calls `GET /key/info?key=<token>` on LiteLLM.
- FR-2. If the key is not found (LiteLLM returns 404), the server returns an `NOT_FOUND` oRPC error.
- FR-3. If the authenticated user's role is `USER` and `key.user_id` does not match `context.user.id`, the server returns a `FORBIDDEN` error.
- FR-4. The returned `KeyView` shape is: `alias`, `token`, `userId`, `teamId`, `maxBudget`, `spend`, `budgetDuration`, `tpmLimit`, `rpmLimit`, `createdAt`, `expires`.

**States & edge cases:**

- Key deleted between list load and info request: `NOT_FOUND` is returned.
- USER attempting to inspect another user's key: `FORBIDDEN` prevents cross-user data leakage.

**Acceptance criteria:**

- AC-1. Given a USER calls `keys.info` with a token belonging to their own key, then the full `KeyView` record is returned.
- AC-2. Given a USER calls `keys.info` with a token belonging to another user, then a `FORBIDDEN` error is returned.
- AC-3. Given an ADMIN calls `keys.info` with any valid token, then the record is returned regardless of which user owns it.
- AC-4. Given a non-existent token, then a `NOT_FOUND` error is returned.

---

### Revoke / Delete Key

**Purpose:** Permanently delete an API key, immediately revoking its ability to authenticate requests to the LiteLLM proxy.

**Preconditions / access:** User is authenticated. Revoke is initiated from the trash icon button in the Key Table row. A confirmation dialog must be accepted before deletion proceeds.

**UI elements (ConfirmDialog):**

- Dialog title: `Revoke "<alias>"?` (uses key alias if set, otherwise `"this key"`).
- Dialog description: "This is immediate and irreversible. Anything using this key will start receiving 401 errors."
- Footer buttons:
  - Ghost "Cancel" — dismisses dialog, no mutation.
  - Destructive "Revoke" — triggers the delete mutation; label changes to "Working…" while in-flight and the button is disabled.
- During the mutation, the "Cancel" button is also disabled.

**Functional behavior:**

- FR-1. Clicking the trash icon sets `pendingRevoke` to the key's row data in local component state, which opens the ConfirmDialog.
- FR-2. On "Cancel" click or dialog dismiss, `pendingRevoke` is set to `null`; no mutation is triggered.
- FR-3. On "Revoke" confirm, `keys.remove` is called with `{ token: pendingRevoke.token }`.
- FR-4. Server-side for a `USER`: `keys.remove` calls `getKeyInfo(token)` first (LiteLLM `GET /key/info`) for an ownership check. If the key does not exist (`NOT_FOUND` from LiteLLM), it returns `NOT_FOUND`. If `key.user_id !== context.user.id`, it returns `FORBIDDEN`. Only then does it call `POST /key/delete` with `{ keys: [token] }` on LiteLLM.
- FR-5. For an `ADMIN`, ownership check is skipped and any key may be deleted.
- FR-6. On success: toast `Key "<alias|token>" revoked`; `pendingRevoke` set to `null` (dialog closes); `keys.list` query is invalidated so the table refreshes.
- FR-7. On error: toast `"Revoke failed: <message>"`; dialog remains open; `pendingRevoke` is unchanged.

**States & edge cases:**

- Key already deleted before confirmation (concurrent session): `NOT_FOUND` error from the server; toast shows the error; table remains stale until next invalidation.
- User attempts to revoke another user's key via direct API call: `FORBIDDEN` is returned.
- Network failure during deletion: error toast is shown; key remains listed in the table.
- Revoking the last remaining key: table transitions to empty state after `keys.list` re-fetches.
- Revoking a key actively in use by code: LiteLLM immediately rejects subsequent requests with 401; there is no grace period.

**Acceptance criteria:**

- AC-1. Given a key row in the table, when the user clicks the trash icon, then the ConfirmDialog appears with the key's alias in the title and the irreversibility warning.
- AC-2. Given the ConfirmDialog is open, when the user clicks "Cancel", then the dialog closes and the key remains in the table.
- AC-3. Given the user clicks "Revoke", when the mutation is in-flight, then both dialog buttons are disabled and the "Revoke" label reads "Working…".
- AC-4. Given a successful revoke, when the mutation completes, then the dialog closes, a success toast appears with the key alias, and the key is no longer in the table.
- AC-5. Given the key was already deleted, when the revoke mutation returns NOT_FOUND, then an error toast is shown and the dialog stays open.
- AC-6. Given a USER clicks revoke on a key they own, then deletion succeeds. Given a USER attempts API-level deletion of another user's key, then FORBIDDEN is returned.

---

### Usage Dashboard

**Purpose:** Provide a comprehensive view of the user's API usage across a selectable time period (7, 30, or 90 days), covering total cost, request count, model breakdown, hardware breakdown, a daily spend chart, and a recent-requests log.

**Preconditions / access:** User is authenticated. Reached via the "Usage" nav link (`/usage`). All usage data is filtered server-side to the authenticated user's traffic, matched on either `end_user === userId` (chat traffic) or `metadata.user_api_key_user_id === userId` (issued-key traffic).

**UI elements:**

- Page heading: "Usage" (h1, `text-3xl font-semibold`).
- Sub-heading: "Tokens, cost, and recent requests across chat and your API keys."
- **Period selector** (top-right of header): segmented button group with three options: "7 days" / "30 days" / "90 days". Active period has default (filled) variant; inactive periods are ghost. Default: 7 days.
- **Summary Cards** (4 cards in a responsive grid, re-fetched on period change):
  - "Total cost" — formatted USD.
  - "Requests" — integer count, locale-formatted.
  - "Models used" — count of distinct model names; hint "No traffic in this period" when 0.
  - "Primary hardware" — the `hardware_id` tag of the device with the most requests in the period, in monospace. A `Badge` showing the backend type (`npu` → default variant / filled; other → secondary variant). Displays "—" when no hardware data is available. (Requires Langfuse integration; see note below.)
- **Daily spend chart** ("Last \<N\> days"): same component as on the Profile page — bar chart with request count and total cost in the header, peak day highlighted, relative-time "Last request" footer stat.
- **By model card** ("By model"): ranked list of models by spend. Each row: model name in monospace; USD spend + request count on the right; horizontal bar (relative to highest-spend model). "No usage in this period." when empty.
- **By hardware card** ("By hardware"): ranked list of `hardware_id` values by spend. Each row: hardware ID in monospace; backend-type badge; USD spend + request count. Bar color: primary (full) for NPU backends, primary/55 (dimmer) for others. When the Langfuse trace page cap is hit (500 traces over `MAX_PAGES = 5` pages × 100), a truncation note "(recent traces only — ask for older with a longer period)" is shown. Card is hidden entirely when no hardware data is returned (the component returns `null`).
- **Recent requests table** ("Recent requests"): shows up to 50 requests from the last 30 days, most-recent first. Columns: **When** (relative time, e.g. "5 min ago", "3 hr ago"), **Model** (monospace), **Source** (badge: secondary variant with key alias for `via='key'` traffic; outline "chat" badge for `via='chat'` traffic), **Cost** (right-aligned monospace USD). "No requests yet — usage will appear here as you chat or call the API." when empty.
- **Skeleton loaders** are shown independently for each card while its query is pending.

**Functional behavior:**

- FR-1. On mount and on period change, the SPA issues four parallel queries: `usage.summary`, `usage.daily`, `usage.byModel`, `usage.byHardware` — all with the current `days` value. `usage.recent` is always fetched with `{ limit: 50 }` (independent of period selector).
- FR-2. `usage.summary` joins LiteLLM spend logs (for cost + request count + model diversity) with Langfuse traces (for `hardware_id` and `backend_type` tags). If Langfuse credentials are not configured, the procedure throws a plain `Error` (not `LangfuseError`) — specifically `new Error('LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not configured')`. `LangfuseError` is only raised when the Langfuse server is reachable but returns a non-OK HTTP response. Both error types propagate as generic oRPC errors to the client; the "Primary hardware" card shows an error state.
- FR-3. `usage.daily` pre-fills every calendar day in the period with $0.00 spend so the chart always has `days` columns, even if there are gaps in the logs.
- FR-4. `usage.byModel` normalizes model names by stripping the `openai/` prefix (e.g. `openai/qwen2.5:3b` → `qwen2.5:3b`).
- FR-5. `usage.byHardware` reads the `hardware_id:` and `backend_type:` tags stamped on Langfuse traces by the LiteLLM pre-call hook. An unknown `hardware_id` (no tag) is grouped under `"unknown"`.
- FR-6. `usage.recent` fetches the last 30 days of logs, sorts descending by `startTime`, and slices to `limit`. The "Source" badge displays the key alias if the log carries `metadata.user_api_key_alias`; otherwise it shows "key" for API-key traffic or "chat" for chat traffic.
- FR-7. If any query returns 401, the SPA navigates to `/unauthorized`.
- FR-8. Period changes reuse cached data within TanStack Query's stale time; the charts re-render immediately with the new query's data when available.

**States & edge cases:**

- No usage in the selected period: all spend values are $0.00, bar chart shows empty bars (4px grey bars for zero days), "By model" shows "No usage in this period.", "By hardware" card is hidden.
- Langfuse not configured: `usage.summary` and `usage.byHardware` throw server errors; "Primary hardware" card shows an error. The SPA renders a generic error paragraph for non-401 query errors — there is no dedicated "Langfuse not connected" message in the current SPA code.
- Trace page cap hit: "By hardware" card shows the truncation note; the data shown is the most recent 500 traces only.
- Very small spend amounts (sub-cent): `formatUsd` renders four decimal places (e.g. `$0.0001`).
- Chart with only one non-zero day: that day renders at full height (100%); all others at 0 height (4px grey bar).

**Acceptance criteria:**

- AC-1. Given the Usage page loads for a user with activity in the last 7 days, when the page renders, then the "Total cost" stat card shows a non-zero USD amount and the daily chart has 7 columns.
- AC-2. Given the user changes the period to "30 days", when the selector is clicked, then all four summary-dependent cards and the chart re-fetch and re-render with 30-day data.
- AC-3. Given the user has made API-key requests, when the Recent Requests table renders, then those rows show a secondary badge containing the key alias (or "key" if no alias).
- AC-4. Given Langfuse traces exist with `hardware_id:npu-01` and `backend_type:npu` tags, when the "By hardware" card renders, then `npu-01` appears with a filled "npu" badge.
- AC-5. Given no activity in the selected period, when the "By model" card renders, then it shows "No usage in this period." and the "By hardware" card is not visible.
- AC-6. Given the "Recent requests" table has no data, when the card renders, then the empty-state message is shown: "No requests yet — usage will appear here as you chat or call the API."
- AC-7. Given all usage queries return 401, when the page renders, then the browser navigates to `/unauthorized`.

---

### Budget & Usage Display (Cross-cutting)

**Purpose:** Surface consistent budget and spend information throughout the console so users can at a glance understand their remaining allowance and historical consumption.

**Preconditions / access:** All budget and spend figures require an authenticated session and a successfully provisioned LiteLLM account.

**UI elements:** Budget and spend data appears in three locations: the Available Hero card (Profile page), the inline budget bar per key (Key Table), and the Keys Summary "Total budget" and "Used across keys" stats (Keys page). Spend totals are also shown on the Usage page summary cards.

**Functional behavior:**

- FR-1. `me.get` computes `spend.total = spend.chat + spend.issuedKeys`. `spend.chat` is sourced from the LiteLLM Customer (End-User) row; `spend.issuedKeys` is the sum of `spend` across `keys.list` results. The Internal-User `spend` field is not used because it does not capture chat traffic in the current LiteLLM version.
- FR-2. `limits.maxBudget` and `limits.budgetDuration` come from the Internal-User row (provisioned at JIT time).
- FR-3. `pctSpent(spend, max)` clamps to [0, 100] and rounds to the nearest integer. A null or zero `max` returns 0%.
- FR-4. `formatUsd` formats amounts in three tiers: exactly $0.00 → `$0.00`; sub-cent (< $0.01) → 4 decimal places (e.g. `$0.0050`); $0.01 to $0.99 → 3 decimal places (e.g. `$0.125`); ≥ $1.00 → 2 decimal places (e.g. `$1.50`). Note: a value of $0.005 is sub-dollar but also sub-cent, so it receives 4 dp, not 3.
- FR-5. `compactNumber` formats large integers with Intl compact notation (e.g. `10000` → `10K`). A null value renders as `∞`.
- FR-6. The per-key budget bar and the Available Hero bar share the same threshold logic (FR-3 in the Profile Page section above).

**States & edge cases:**

- `max_budget = null` (unlimited): Available Hero renders the unlimited variant; per-key usage bars are not shown for keys with null budget; `compactNumber(null)` = `∞` for rate limit display.
- Spend exceeds budget (e.g. due to a rate-limit burst before LiteLLM enforced the cap): `pctSpent` clamps to 100%; the bar is fully red; remaining balance shows $0.00.
- Negative spend: not expected; `Math.max(0, maxBudget - spent)` prevents negative remaining values.

**Acceptance criteria:**

- AC-1. Given `spend = 0.00005`, when the USD formatter is applied, then the displayed value is `$0.0001` (4 decimal places).
- AC-2. Given `max_budget = null`, when the Available Hero renders, then the unlimited variant is shown (no progress bar, no "of" line).
- AC-3. Given `spend = 12`, `max_budget = 10` (over-budget), when the Available Hero renders, then remaining shows "$0.00" and the bar is fully red.
- AC-4. Given `tpm_limit = null`, when the Per-minute limits card renders, then the tokens/min value shows "∞".
