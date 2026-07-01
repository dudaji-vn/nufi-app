# Guardrail security events → admin audit log + Security page

**Date:** 2026-07-01
**Status:** Approved (design)
**Repos touched:** `dudaji-vn/nufichat` (backend + data-schemas), `dudaji-vn/nufichat-admin-panel` (UI)
**Follows:** [2026-06-29-app-layer-guardrails-design.md](./2026-06-29-app-layer-guardrails-design.md)

## Problem

The app-layer LLM guardrails (nufi-v0.1.2/0.1.3) block prompt injection and redact
PII, but they are **invisible**: an admin has no way to see what the guardrails
stopped. For an enterprise/compliance demo this is the missing half — a security
feature you cannot observe cannot be trusted or sold.

## Goal

Make guardrail *enforcement* observable in the admin panel: every time the
guardrail actually blocks or redacts, record a structured audit event, and surface
those events on a dedicated **Security** page (counts + filterable table + CSV).

**Non-goals:** logging normal chat, logging PII-input *warnings* (default mode),
logging injection near-misses (heuristic hit that the AI judge cleared), storing
prompt/response content or PII values, end-user chat/WORM auditing.

## Key decisions (approved)

1. **Storage:** reuse the existing `auditlogs` collection — new `action` keys, actor
   `system:guardrail`. No new collection, no new read route. Read route, CSV export,
   and `ACCESS_ADMIN` gating are reused.
2. **Payload = metadata only.** Never store the prompt, the response, or PII values.
   Store type + count (e.g. `{email: 2, phone: 1}`), injection source/mode/language,
   and the model. This is the point of the feature: *we don't even log the thing we
   protect.*
3. **Scope = enforcement events only.** Three: injection blocked, PII-input blocked
   (only when `GUARDRAIL_PII_INPUT_MODE=block`), PII-output redacted. PII-input warn
   is NOT logged (fires on normal usage → noise).
4. **UI = dedicated Security page** (not a filter on the Audit Log page), with a
   summary strip + guardrail-specific columns.

## Data model

Reuse `auditlogs`. Three new `action` keys (the schema `action` is a free string, no
enum — no schema change needed for the keys themselves):

- `guardrail_injection_blocked`
- `guardrail_pii_input_blocked`
- `guardrail_pii_output_redacted`

Per-entry field mapping:

| field | value |
|---|---|
| `action` | one of the three keys |
| `actorName` | `system:guardrail` |
| `actorId` | (unset — no admin actor) |
| `targetType` / `targetId` | `user` / the guarded user's id |
| `targetName` | the guarded user's name/email — **accountability metadata**, identifies *who* was guarded; this is NOT the content-PII the feature protects |
| `details` | human-readable one-liner (drives the shared CSV + quick scan), e.g. `Blocked prompt injection (hybrid, ai)`, `Redacted 2 email, 1 phone from response` |
| `metadata` | structured object (new optional schema field): `{ model, source, language, mode, piiTypes: { email: 2, phone: 1 } }` |
| `status` | `success` |

**Privacy invariant:** no field ever contains raw prompt text, raw response text, or
any PII *value*. Only types, counts, and detector provenance.

### Schema change (data-schemas)

Add one optional field `metadata` (Mongoose `Schema.Types.Mixed`, `default undefined`)
to `packages/data-schemas/src/schema/auditLog.ts`, mirror it on `IAuditLog`
(`packages/data-schemas/src/types/auditLog.ts`), and have the read converter
(`toAuditLogEntry` in `~/server/services/Audit`) pass it through. No migration —
Mongo tolerates the new field on existing docs. Rebuild with `npm run build` (the
package builds to gitignored `dist/`). The admin panel keeps its own local
`AuditLogEntry`/`SecurityEvent` type, so it does not wait on a published
`@librechat/data-schemas` bump.

## Backend — emission

New module `api/server/middleware/guardrails/audit.js`:

```
recordGuardrailEvent({ type, req, model, source, language, mode, piiTypes })
```

- Gated by `GUARDRAIL_AUDIT_ENABLED` (default: on when `GUARDRAIL_ENABLED` is on).
- Maps `type` → action key, builds the entry above, calls `createAuditLog`.
- Fully best-effort: wrapped in try/catch, and `createAuditLog` itself never throws.
  **A guardrail audit failure must never affect the chat.**

Three call sites:

1. **Injection block** — `inputGuard.js` at the `verdict.injection` branch
   (currently ~L59-72). Has `userId` (`req.user?.id`), `model` (`req.body.model`),
   `source`, `mode`, `language`. The specific matched rule is **best-effort**: only
   captured if `detectInjection` is extended to surface the matched pattern id;
   otherwise omit `rule` and keep `source`/`mode`.
2. **PII-input block** — `inputGuard.js` at the `piiMode === 'block'` branch
   (currently ~L84-90). Compute `piiTypes` counts from the `pii` array.
3. **PII-output redaction** — emitted from `runOutputGuard` (`request.js` ~L32),
   where `userId`, `conversationId`, and `model` are in scope. Requires
   `applyOutputGuard` to return what it did.

### `applyOutputGuard` return-shape change

Today `applyOutputGuard(response, ctx)` redacts in place and returns only
`response`. Change it to return `{ response, redacted, piiTypes }` (piiTypes counts
gathered from the same `detectPII`/`redactOutput` pass it already runs at the
detection gate). Update the single caller `runOutputGuard`; when `redacted === true`
it calls `recordGuardrailEvent`.

## Backend — read

Extend `getAuditLogs`/`countAuditLogs` (data-schemas methods) and the
`GET /api/admin/audit-log` route with a `category` param:

- `category=admin` (**default**) → `action` NOT starting with `guardrail_`
  (`$nin`/`$not` regex). Keeps the existing Audit Log page clean — guardrail rows
  do not leak into the admin-action log.
- `category=security` → only `action` starting with `guardrail_`.

When `category=security`, the list response also returns `countsByAction` (one
aggregation grouped by `action` over the same filter) so the Security page's summary
strip is accurate across the whole range, not just the current page. `/export` CSV
honors `category` unchanged otherwise.

## Admin panel — Security page

- **Route:** `src/routes/_app/security.tsx`, gated `SystemCapabilities.ACCESS_ADMIN`
  (mirror `audit-log.tsx`). Register title in `_app.tsx` `ROUTE_TITLE_KEYS`.
- **Nav:** add an item to `Sidebar.tsx` navItems — `ShieldAlert` icon, path
  `/security`, capability `ACCESS_ADMIN`.
- **Component:** `src/components/security/SecurityPage.tsx`:
  - summary strip: counts per event type over the selected range (from
    `countsByAction`);
  - table columns: Event type (badge), User (`targetName`), Model, Source
    (ai/heuristic), Detection summary, Timestamp;
  - filters: event-type dropdown (3 keys), date from/to, search; Export CSV button.
  - Follows the existing native-`<table>` + shared `SearchInput`/`LoadingState`/
    `EmptyState` pattern used by the other list pages.
- **Server fn:** `src/server/securityEvents.ts` → calls
  `/api/admin/audit-log?category=security&...` (list, incl. `countsByAction`) and
  `/api/admin/audit-log/export?category=security&...`.
- **Type:** `src/types/securityEvent.ts` (local; extends the audit shape with typed
  `metadata`).
- **i18n:** `com_nav_security`, `com_security_*` keys.
- **Existing Audit Log page:** change its server fn to pass `category=admin`
  (harmless: it's the route default too).

## Testing

- **Backend unit:** `recordGuardrailEvent` maps each `type` to the right action +
  builds the metadata-only payload; it swallows a thrown `createAuditLog` without
  propagating. `getAuditLogs` honors `category=admin|security`. `applyOutputGuard`
  returns `{ redacted, piiTypes }` on a redaction and `{ redacted: false }`
  otherwise. Add to the existing `guardrails/*.spec` suites.
- **Manual QA (Argent / staging):** send one prompt-injection and one prompt that
  provokes a PII leak; confirm both appear on the Security page with correct type,
  model, and counts, and that the Audit Log page does NOT show them.

## Rollout

- Rebuild `@librechat/data-schemas` (`npm run build`) after the schema field.
- Backend release: cut `nufi-v0.1.4` via the `/nufi-release` flow (develop →
  fork/main, tag, verify GHCR build).
- Admin panel: branch off `main`, PR, merge → image rebuild, then bump the Railway
  admin service, and cut a `nufi-admin-v*` tag if a versioned image is wanted.
- Railway chat service: set `GUARDRAIL_AUDIT_ENABLED=true` (document in
  `nufi-chat/.env.example`).

## Risks / notes

- Guardrail events share the `auditlogs` collection; if guardrail volume ever grows
  large it could dominate the collection. Acceptable for the demo; if it becomes a
  problem, split to a dedicated collection later (the `category` seam already
  isolates reads).
- `targetName` stores the guarded user's identity. If fully-anonymous auditing is
  ever required, drop `targetName` and keep `targetId` only — the Security page
  already tolerates a missing name.
