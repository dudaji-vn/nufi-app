# Screenshot recapture run log — 2026-09-07

Branch `docs/audit-screenshots` from origin/main 84c0fa682 (after lane 5
merged). Captured with `bun run screenshots` against the hosted
surfaces, signed in as the shared test account (credentials passed as
`NUFI_EMAIL` / `NUFI_PASSWORD`; not recorded anywhere).

## What the run taught

| # | Observation | Consequence |
|---|---|---|
| 1 | The test account's original 6-character password could not sign in: the login schema requires 8 (`api/strategies/validators.js:33-36`) and is checked before the account is looked up, while `config/create-user.js` never enforces it | **F30**; password reset by Sun before the run |
| 2 | Every fresh browser context starts in Basic, so the script now writes the same `localStorage` key the Interface switch writes and reloads before photographing the menus | script: `enableAdvancedMode()` |
| 3 | The Tools menu and the Parameters panel render for **plain models only** (`ChatForm.tsx:357`: not agents, not assistants); the previous run failed on them because the account's last conversation was the agent *Public* | script: `selectPlainModel()`; docs corrected on every page that said the Tools menu belongs to agents |
| 4 | On `chat.nufi.me` the Agent Builder offers **File Search** alone, and the Tools menu of a plain model lists File Search alone; no Web Search, Run Code, Artifacts or Skills, and no Skills panel in the rail | **F29** rewritten (production matches `deploy/railway/librechat.yaml`); web-search, data-analysis and agents pages now say so; `chat-skills.png` removed |
| 5 | The model picker is identical in Basic and Advanced (My Agents, Nufi, Nufi-lab); the "curated list in Basic" claim was wrong for this deployment | models page corrected |
| 6 | The Parameters panel has a **Web Search** toggle that is the provider's native option, not NUFI's tool | models page warns about it |
| 7 | Settings has a **Personalization** tab and no font-size control on General | sign-in page corrected |
| 8 | The account menu order is My Files, Help & FAQ, Console, Agents, Settings, Advanced/Basic, Log out | sign-in page corrected |
| 9 | Works opened the `dudaji` company with *"User does not have access to this company"* on every page | **F31**; capture refused, old `works-dashboard.png` kept |
| 10 | The console's 7-day usage chart stayed a loading skeleton for 20 s in two captures | not diagnosed; `console-home.png` shows the skeleton |
| 11 | The default `admin` URL in the script was the Railway-generated host; the custom domain is `admin.app.nufi.me` | script corrected |
| 12 | The `chat` surface's account-menu capture shows the signed-in email unredacted | capture dropped; the `chatmenu` surface (redacted) covers it |

## Recaptured

`chat-sign-in`, `chat-home`, `chat-agents-menu`, `chat-model-menu`,
`chat-presets-menu`, `chat-attach-menu`, `chat-tools-menu`,
`chat-parameters`, `chat-conversation`, `chat-settings-general` (new),
`chat-agent-new`, `chat-agent-knowledge`, `chat-teams-list`,
`chat-team-create`, `chat-team-members`, `chat-team-invite`,
`chat-team-knowledge`, `chat-team-shared`, `chat-team-groups`,
`console-home`, `agents-chooser`, `studio-home`, `studio-api-keys`,
`studio-variables`, `admin-sign-in`, `admin-home`, `admin-configuration`,
`admin-access`, `admin-grants`, `admin-role-detail`.

## Kept from earlier runs

The Works set (`works-dashboard`, `works-signin`, `works-onboarding`,
`works-agents`, `works-org`, `works-costs`) because of F31, and the four
`security-*` shots, which come from the local stack.

## Removed

`chat-skills.png` (no Skills panel on production), `chat-account-menu.png`
(real email, unreferenced), `works-home.png` and `chat-model-menu-basic.png`
(captured, judged not useful, never committed).
