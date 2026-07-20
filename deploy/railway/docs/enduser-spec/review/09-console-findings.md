# Verification findings — 09 Console

## Summary

- Claims checked: 68 | CONFIRMED: 59 | WRONG: 4 | NEEDS-FIX: 3 | RUNTIME-ONLY: 2

---

## Findings

### [WRONG] API Keys — List / Table · AC-2 (progress bar colour at 80%)

- **Spec says:** "Given a key with `spend = 8`, `max_budget = 10`, when the table row renders, then the Usage column shows '$8.00 of $10.00' and the progress bar is **red** (≥80%)."
- **Reality:** The threshold logic in both `key-table.tsx:57` and `available-hero.tsx:34` is `pct >= 90 → destructive (red); pct >= 70 → amber-500; else → primary`. At 80% the bar is **amber**, not red.
- **Evidence:** `src/components/key-table.tsx:57` — `const tone = pct >= 90 ? 'bg-destructive' : pct >= 70 ? 'bg-amber-500' : 'bg-primary';`
- **Suggested correction:** Change AC-2 to say "amber (≥70%)" for 80%, or change the example to `spend = 9.5` (95%) to demonstrate the red/destructive threshold.

---

### [WRONG] Create / Generate API Key · Edge case "Budget or limit fields left blank"

- **Spec says:** "Budget or limit fields left blank: `Number('')` evaluates to `0`, which fails server validation (`positive()`); a toast error is shown."
- **Reality:** All three fields (`budget`, `tpm`, `rpm`) carry the HTML5 `required` attribute (`key-generate-modal.tsx:110, 143, 155`). The browser blocks form submission before any `Number('')` conversion occurs; the toast path is never reached for this specific edge case via normal UI interaction. The server validation is still correct, but the described *mechanism* (server rejection) is not the path the UI takes.
- **Evidence:** `src/components/key-generate-modal.tsx:110` — `required` on budget input; `143` — `required` on tpm; `155` — `required` on rpm.
- **Suggested correction:** Rephrase edge case to: "Budget or limit fields cannot be left blank in the browser (HTML5 `required`); the form will not submit."

---

### [WRONG] Usage Dashboard · FR-2 (verify: resolved incorrectly — Langfuse error type)

- **Spec says (verify marker):** "…the procedure throws `LangfuseError` which propagates as an oRPC error to the client."
- **Reality:** When Langfuse keys are not configured, `langfuse.ts:45–46` throws a plain `new Error('LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not configured')`, **not** a `LangfuseError`. `LangfuseError` is only raised for non-OK HTTP responses from an otherwise reachable Langfuse server (`langfuse.ts:53`). Both error types propagate uncaught through `usage.ts` and surface as generic oRPC errors on the client — the endpoint-level behaviour is the same, but the type is wrong.
- **Evidence:** `server/lib/langfuse.ts:45–46` — `throw new Error('LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not configured');` vs `langfuse.ts:9–15` for the `LangfuseError` class definition.
- **Suggested correction:** Change to: "…the procedure throws a plain `Error` (not `LangfuseError`) when credentials are absent, or `LangfuseError` when the Langfuse server returns a non-OK response; both propagate as oRPC errors to the client."

---

### [WRONG] Profile Page (TopKeysCard) — unnamed key label differs from KeyTable

- **Spec says (Profile Page, "Your Keys card"):** "alias (or 'unnamed')" in muted color.
- **Reality:** `top-keys-card.tsx:50` renders `unnamed` (no parentheses) while `key-table.tsx:63` renders `(unnamed)` (with parentheses). The spec uses `(unnamed)` (with parens) in the Keys Table section (correct for that component) but says just `unnamed` (no parens) in the Profile page section, which accidentally matches the TopKeysCard. The spec is internally consistent for each location, but the two components intentionally differ — neither is wrong, but the spec should make the discrepancy explicit.
- **Evidence:** `src/components/top-keys-card.tsx:50` — `unnamed`; `src/components/key-table.tsx:63` — `(unnamed)`.
- **Suggested correction:** Explicitly note that TopKeysCard renders `unnamed` (no parentheses) while the Key Table renders `(unnamed)` (with parentheses).

---

### [NEEDS-FIX] Create / Generate API Key · FR-2 — server-side `maxBudget` is optional, not required

- **Spec says:** "Server-side validation enforces: …`maxBudget` positive, max 10 000…"
- **Reality:** The Zod schema at `server/router/keys.ts:69` declares `maxBudget: z.number().positive().max(10_000).optional()`. If the client omits `maxBudget`, the server silently substitutes `DEFAULT_USER_BUDGET` ($10). The validation only applies when the field is present. Same is true for `budgetDuration`, `tpmLimit`, `rpmLimit`, and `duration` — all `.optional()`.
- **Evidence:** `server/router/keys.ts:65–74` — all fields except `alias` are `.optional()`.
- **Suggested correction:** Add "All fields except `alias` are optional on the wire; if omitted, server defaults are applied (same defaults as JIT provisioning)." to FR-2.

---

### [NEEDS-FIX] Revoke — FR-5 references wrong FR number

- **Spec says (Revoke FR-5):** "For an `ADMIN`, ownership check is skipped and any key may be deleted."
- **Reality:** The code is correct (`keys.ts:99` — `if (context.user.role !== 'ADMIN')` guards the ownership check), but the spec paragraph numbering conflicts: FR-5 in the Revoke section appears after FR-4 describes the server-side USER flow. No code bug, but the spec labels FR-4 and FR-5 overlap in meaning with `keys.remove` logic and never mention that `keys.info` is called inside `keys.remove` for the ownership check (it is: `server/router/keys.ts:100` calls `getKeyInfo` to fetch ownership before deleting).
- **Suggested correction:** Update FR-4 to read: "Server-side for a USER: calls `getKeyInfo(token)` first (LiteLLM `GET /key/info`); returns `NOT_FOUND` if absent; returns `FORBIDDEN` if `key.user_id !== context.user.id`; then calls `POST /key/delete`."

---

### [NEEDS-FIX] Budget & Usage Display · FR-4 `formatUsd` — sub-dollar threshold description

- **Spec says:** "sub-dollar as 3 decimal places" (applies to amounts < $1).
- **Reality:** The code has two sub-dollar branches: `n < 0.01 → toFixed(4)` (sub-cent) and `n < 1 → toFixed(3)` (sub-dollar, ≥1 cent). A value of `$0.005` is sub-dollar but sub-cent, so it gets **4** decimal places (`$0.0050`), not 3. The spec's wording implies 3dp for all amounts < $1, which is only correct for the $0.01–$0.99 band.
- **Evidence:** `src/lib/format.ts:11–12` — `if (n < 0.01) return \`$\${n.toFixed(4)}\`; if (n < 1) return \`$\${n.toFixed(3)}\`;`
- **Suggested correction:** Clarify: "sub-cent (< $0.01) → 4 decimal places; $0.01 to $0.99 → 3 decimal places; ≥ $1.00 → 2 decimal places."

---

### [RUNTIME-ONLY] Authentication — isUnauthorized detection via oRPC error code

- **Spec says (FR-6):** "The SPA detects 401 responses via `isUnauthorized` and navigates to `/unauthorized`."
- **Reality:** `isUnauthorized` (`src/lib/orpc.ts:17–18`) checks `err instanceof ORPCError && err.code === 'UNAUTHORIZED'`. The Hono middleware returns a raw HTTP 401 JSON body **before** the oRPC layer runs. Whether the `RPCLink` client translates a bare HTTP 401 into an `ORPCError` with code `'UNAUTHORIZED'` — or wraps it differently — depends on the `@orpc/client` fetch adapter's error-mapping behaviour and cannot be confirmed from source alone. For the server-side `throw new ORPCError('UNAUTHORIZED')` path (inside oRPC handlers), the mapping is direct and confirmed. For the Hono-level 401, it is runtime-only.
- **Suggested correction:** Add a note: "The Hono middleware 401 path requires runtime testing to confirm that `@orpc/client` maps it to `ORPCError.code === 'UNAUTHORIZED'`."

---

### [RUNTIME-ONLY] Production URL — console.nufi.me

- **Spec says:** "In production it is served at **https://console.nufi.me**."
- **Reality:** The codebase contains no hardcoded `console.nufi.me` — the URL is a deployment/infrastructure configuration (`docker-compose.yml:33` references the pattern, but the actual hostname binding is a runtime/platform concern). The code is correct and URL-agnostic; the claim is infrastructure-level and cannot be verified from source code alone.
- **Evidence:** `nufi-console/Dockerfile` — no hostname; `docker-compose.yml:33` comment — references the intended domain conceptually.
- **Suggested correction:** Mark as deployment-verified, not code-verified.

---

### [VERIFY-RESOLVED] Usage Dashboard · FR-5 — `byHardware` unknown grouping

- **Spec says:** "An unknown `hardware_id` (no tag) is grouped under `'unknown'`."
- **Reality:** `server/router/usage.ts:216` — `const hw = tagValue(trace, 'hardware_id') ?? 'unknown';` — CONFIRMED. Missing hardware_id tag results in the trace being bucketed under the key `"unknown"`.

---

### [VERIFY-RESOLVED] Usage Dashboard · FR-2 — `usage.summary` Langfuse error handling on client

- **Spec says (verify):** "the SPA currently renders a generic error paragraph for non-401 query errors — there is no dedicated 'Langfuse not connected' message."
- **Reality:** CONFIRMED. `usage.tsx` renders no special Langfuse error UI. Each card independently shows its skeleton/empty state when pending, but there is no error boundary or Langfuse-specific error message in the current SPA code.

---

## Claims confirmed without issue (representative list)

| Area | Claim |
|---|---|
| Auth · FR-1–FR-5 | Bearer → JWT_SECRET then refreshToken → JWT_REFRESH_SECRET; claim extraction order `id/userId/_id/sub`; role logic; 500 for missing secrets |
| Auth · FR-6 | `isUnauthorized` used on Profile, Keys, and Usage pages |
| Auth · FR-7 | "Open chat" uses `VITE_LIBRECHAT_URL ?? 'http://localhost:3080'` |
| JIT · FR-2 | 404 and 400+"not found" both treated as new user |
| JIT · FR-3 | Defaults: $10 / 30d / 10,000 TPM / 60 RPM; proxy_admin for ADMIN |
| JIT · FR-1 | `Promise.all([ensureLiteLLMUser, getCustomer, listKeysForUser])` |
| Profile · FR-1 | Two parallel queries: `me.get` + `usage.daily` with `days: 7` |
| Profile · FR-2 | Total spend = customer.spend + sum(key.spend); internal-user spend not used |
| Profile · FR-3 | Thresholds: ≥90% red / ≥70% amber / else primary |
| Keys list · FR-1 | USER → `listKeysForUser`; ADMIN → `listAllKeys` |
| Keys list · FR-2 | `maskKey` on `token` field (first 3 + last 4, unchanged if ≤8 chars) |
| Keys list · FR-6 | "Expiring this week" excludes already-past dates (`ms > 0`) |
| Key create · FR-1 | `duration='never'` sent as `undefined` to LiteLLM |
| Key create · FR-3 | Success: `showRevealedKey` sets `revealedKey` and closes generate modal |
| Key create · FR-5 | Cancel calls `setOpen(false)`; form state not reset; reset only on success |
| Reveal modal · FR-2 | `Dialog onOpenChange` + Escape call `clear()`; "I've saved it" calls `clear()` |
| Reveal modal · FR-5 | `models.list` fetched with `enabled: !!revealed` and 5 min stale time |
| Reveal modal · FR-6 | `defaultValue="curl"` |
| Revoke · FR-4 | USER: `getKeyInfo` → NOT_FOUND / FORBIDDEN → `deleteKey` |
| Revoke · FR-5 | ADMIN bypasses ownership check |
| Revoke · FR-6 | Toast uses `alias ?? token` |
| Usage · FR-3 | `daily`: pre-fills every UTC day with $0 bucket |
| Usage · FR-4 | `byModel`: strips `openai/` prefix |
| Usage · FR-5 | `byHardware`: reads `hardware_id:` / `backend_type:` tags; missing grouped as `unknown` |
| Usage · FR-6 | `recent`: 30-day window, sorted descending, sliced to limit; `via` logic matches `user_api_key_user_id` |
| Budget display · FR-3 | `pctSpent` clamps [0,100]; null or zero max → 0% |
| Budget display · FR-5 | `compactNumber(null)` → `∞` |
| Chart rendering | 0-spend days: `bg-muted` at `4px`; non-zero: `Math.max(15, sqrt-scaled %)`; peak: `bg-primary`; others: `bg-primary/55` |
| Truncation note | Exact text: "(recent traces only — ask for older with a longer period)"; 500 trace cap (MAX_PAGES=5 × PAGE_LIMIT=100) |
