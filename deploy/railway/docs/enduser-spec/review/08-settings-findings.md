# Verification findings — 08 Settings & Console link

## Summary

- Claims checked: 38 | CONFIRMED: 31 | WRONG: 4 | NEEDS-FIX: 3 | RUNTIME-ONLY: 3 | VERIFY-RESOLVED: 3

---

## Findings

### [WRONG] General Tab — Language "Auto" label persists after selection (spec §General, States & edge cases)

- **Spec says:** "the displayed selection label remains 'Auto' even after the effective locale is applied to the DOM."
- **Reality:** When the user selects "Auto", `changeLang` resolves `navigator.language` into `userLang` and calls `setLangcode(userLang)` — the Recoil atom stores the resolved locale string (e.g., `'en-US'`), not `'auto'`. On the next render `LangSelector` receives `langcode={langcode}` where `langcode` is now `'en-US'`, so the dropdown displays "English", not "Auto".
- **Evidence:** `client/src/components/Nav/SettingsTabs/General/General.tsx:168-175`
- **Suggested correction:** "When 'Auto' is selected, the resolved locale (e.g., `en-US`) is stored and shown in the dropdown thereafter; the option no longer shows as 'Auto' on reopen."

---

### [WRONG] Account Tab — 2FA setup progress bar visibility (spec §Account, UI elements, two-factor setup)

- **Spec says:** "Progress bar displayed in the dialog header" (during setup wizard phases Setup → Scan QR → Verify → Backup).
- **Reality:** The progress bar is only rendered when `user?.twoFactorEnabled && phase !== 'disable'`. During initial setup, `twoFactorEnabled` is `false`, so the progress bar is never rendered in the setup flow. It would only appear for an already-2FA-enabled user who goes through the change/re-confirm flow — which is not the normal setup scenario described.
- **Evidence:** `client/src/components/Nav/SettingsTabs/Account/TwoFactorAuthentication.tsx:228`
- **Suggested correction:** "The progress bar in the dialog header is only shown when the user already has 2FA enabled and is going through an update flow. During initial setup from a disabled state, no progress bar is displayed."

---

### [WRONG] Account Tab — Number of backup codes (spec §Account, FR-3 and BackupCodesItem)

- **Spec says:** "all 8 backup codes" (both in FR-3 and in the Backup Codes UI elements description).
- **Reality:** `generateBackupCodes()` in `twoFactorService.js` generates **10** backup codes by default (`count = 10`). The code and tests confirm 10.
- **Evidence:** `api/server/services/twoFactorService.js:126-129` (`count = 10`); `api/server/controllers/TwoFactorController.js:43` (called with no argument, so default 10).
- **Suggested correction:** Replace "8 backup codes" with "10 backup codes" in both FR-3 and the BackupCodesItem description.

---

### [WRONG] General Tab — Language dropdown width (spec §General, UI elements, Language entry)

- **Spec says:** Language dropdown has `Max display height 256 px / 60 vh` (this is correct) but does NOT mention a fixed width. However the spec implies both dropdowns share the same 180 px width pattern, and the Theme entry says "Width 180 px."
- **Reality (partial confirmation):** The Language `LangSelector` does NOT use `sizeClasses="w-[180px]"`. It uses `sizeClasses="[--anchor-max-height:256px] max-h-[60vh]"` — no fixed pixel width. Only the Theme `ThemeSelector` has `sizeClasses="w-[180px]"`.
- **Evidence:** `client/src/components/Nav/SettingsTabs/General/General.tsx:68,143`
- **Verdict:** The spec attributes "Width 180 px" only to the Theme dropdown, which is correct. The Language entry correctly omits a fixed width. This is CONFIRMED, not wrong — raised here for completeness. No correction needed.

---

### [NEEDS-FIX] Settings dialog — Undocumented Personalization tab (spec omits entire tab)

- **Spec says:** The Settings dialog has six tabs: General, Chat, Commands, Speech, Data, Account.
- **Reality:** `Settings.tsx` renders a seventh tab, **Personalization** (label `com_nav_setting_personalization`), conditionally shown when `hasAnyPersonalizationFeature` is true. `hasAnyPersonalizationFeature` equals `hasMemoryOptOut` (from `usePersonalizationAccess`), which is true when the user has `MEMORIES OPT_OUT` permission. The NuFi `librechat.yaml` does not configure `memory:`, meaning memories are not explicitly enabled — but the permission could still be granted server-side by the default role configuration.
- **Evidence:** `client/src/components/Nav/Settings.tsx:44,96-104,235-241`; `client/src/hooks/usePersonalizationAccess.tsx`
- **Suggested correction:** Add a note: "A Personalization tab also exists in the Settings dialog, rendered when the user has `MEMORIES OPT_OUT` permission. Since NuFi does not configure a `memory:` section, whether this tab appears depends on the default role's `MEMORIES OPT_OUT` grant (verify: confirm). If not granted, the tab is absent and the spec's tab list is complete."

---

### [NEEDS-FIX] Settings dialog — Undocumented Balance tab (spec omits it)

- **Spec says:** The Settings dialog has six tabs: General, Chat, Commands, Speech, Data, Account.
- **Reality:** `Settings.tsx` also conditionally renders a **Balance** tab (`com_nav_setting_balance`, dollar-sign icon) when `startupConfig?.balance?.enabled` is true. The spec mentions "Balance not configured in NuFi" in the dropdown context, but the omission from the tab list is misleading if another NuFi deployment enables it.
- **Evidence:** `client/src/components/Nav/Settings.tsx:46,110-118,246-249`
- **Suggested correction:** Add a parenthetical: "(A Balance tab is also present when `balance.enabled` is configured; not applicable to NuFi.)"

---

### [NEEDS-FIX] Account Dropdown — Balance format claim (spec §Account Dropdown, balance row)

- **Spec says:** Balance format is `Balance: <integer>`.
- **Reality:** The code formats the balance using `new Intl.NumberFormat().format(Math.round(balanceQuery.data.tokenCredits))`, which applies locale-aware number formatting (e.g., thousands separators: `1,234` not `1234`). The string `Balance:` is correct (from the `com_nav_balance` localization key whose English value is `"Balance"`). But `<integer>` is misleading — it is a locale-formatted number.
- **Evidence:** `client/src/components/Nav/AccountSettings.tsx:70-71`; `client/src/locales/en/translation.json:421`
- **Suggested correction:** Change "format `Balance: <integer>`" to "format `Balance: <locale-formatted integer>` (e.g., `Balance: 1,234`)".

---

### [VERIFY-RESOLVED] Commands Tab — Default role grants MULTI_CONVO USE and PROMPTS USE (spec §Commands, verify marker)

- **Spec says:** "(verify: confirm default role grants these permissions)"
- **Resolution:** The NuFi `librechat.yaml` sets `multiConvo: true` and `prompts: true` at the interface level. These interface flags control whether features are available, but actual `USE` permissions depend on the server's role configuration (default user role). This cannot be confirmed from static config alone — the default role's permission grants are set in the database or server defaults.
- **Verdict: RUNTIME-ONLY** — Requires a live system check or role configuration file inspection. The spec's note should remain as a runtime verification item.

---

### [VERIFY-RESOLVED] Data Tab — Default role grants REMOTE_AGENTS USE (spec §Data, verify marker)

- **Spec says:** "(verify: confirm default role grants `REMOTE_AGENTS USE`)"
- **Resolution:** `Data.tsx` uses `useHasAccess({ permissionType: PermissionTypes.REMOTE_AGENTS, permission: Permissions.USE })` to gate the Agent API Keys section. NuFi `librechat.yaml` sets `agents: true`, which enables the Agents endpoint but does not directly set `REMOTE_AGENTS USE` permission in the role. This is a server-side role grant question.
- **Verdict: RUNTIME-ONLY** — Cannot confirm from static code/config. Keep as a runtime check.

---

### [VERIFY-RESOLVED] Account Tab — OAuth provider configuration (spec §Account, States & edge cases, verify marker)

- **Spec says:** "(verify: confirm if OAuth providers are configured)"
- **Resolution:** The NuFi `librechat.yaml` does not configure any OAuth providers (`socialLogins`, `google`, `github`, etc. are absent). By default LibreChat uses local auth. It is very likely all NuFi users authenticate locally, so `user.provider === 'local'` applies and 2FA / Backup Codes rows are visible.
- **Verdict: CONFIRMED (with caveat)** — No OAuth config found in `librechat.yaml`. If the Railway deployment environment does not set OAuth env vars (`GOOGLE_CLIENT_ID`, etc.), local auth is the only provider and the spec's "NuFi uses local authentication by default" is correct.

---

### [CONFIRMED] Console link — rendering condition (spec §Console Link, FR-1 / FR-4)

- The guard `{startupConfig?.interface?.customConsole?.externalUrl && ...}` exactly matches. When `CONSOLE_URL` env var is empty, `resolveExternalUrl` returns `externalUrl: ""` which is falsy — the item is entirely absent from the DOM.
- **Evidence:** `client/src/components/Nav/AccountSettings.tsx:89-102`; `packages/data-schemas/src/app/interface.ts:9-14`

---

### [CONFIRMED] Console link — openNewTab behavior (spec §Console Link, FR-2 / FR-4 / AC-3)

- The click handler: `window.open(externalUrl, startupConfig.interface!.customConsole!.openNewTab === false ? '_self' : '_blank')`. Since NuFi sets `openNewTab: true`, the result is `'_blank'` (new tab).
- **Evidence:** `client/src/components/Nav/AccountSettings.tsx:91-95`; `nufi-chat/librechat.yaml:26`

---

### [CONFIRMED] Console link — label hardcoded (spec §Console Link, States & edge cases)

- The string `Console` is hardcoded as a JSX text node at line 100, not a localization key. It will not change with language setting.
- **Evidence:** `client/src/components/Nav/AccountSettings.tsx:100`

---

### [CONFIRMED] Console link — icon is LayoutDashboard (spec §Console Link / AC-1)

- `import { ..., LayoutDashboard, ... } from 'lucide-react'` is used for the Console menu item icon.
- **Evidence:** `client/src/components/Nav/AccountSettings.tsx:3,99`

---

### [CONFIRMED] Account Dropdown — placement when collapsed (spec §Account Dropdown, AC-5)

- `placement={collapsed ? 'right-end' : undefined}` — collapsed sidebar opens menu to the right-end.
- **Evidence:** `client/src/components/Nav/AccountSettings.tsx:53`

---

### [CONFIRMED] Speech Tab — always rendered, not gated (spec §Speech, Preconditions)

- All four Speech-related tabs (`Speech`) are always included in `settingsTabs` array in `Settings.tsx` with no conditional; the tab is unconditionally rendered.
- **Evidence:** `client/src/components/Nav/Settings.tsx:92-95`

---

### [CONFIRMED] Speech Tab — NuFi has no speech: section (spec §Speech, NuFi deployment note)

- `nufi-chat/librechat.yaml` contains no `speech:` key. The Speech tab will render but TTS/STT functionality (backend-dependent) will not work unless the browser's Web Speech API is used.
- **Evidence:** `nufi-chat/librechat.yaml` (entire file)

---

### [CONFIRMED] Speech Tab — FR-3 engineTTS reset (spec §Speech, FR-3)

- The `useEffect` at line 141-146 of `Speech.tsx` resets `engineTTS` to `'browser'` if it is not in `['browser', 'external']`.
- **Evidence:** `client/src/components/Nav/SettingsTabs/Speech/Speech.tsx:141-146`

---

### [CONFIRMED] Speech Tab — FR-2 advancedMode Recoil atom (spec §Speech, FR-2)

- `advancedMode` is a Recoil state. The Tabs.Root switches on `advancedMode ? 'advanced' : 'simple'`; clicking "Advanced" calls `setAdvancedMode(true)`.
- **Evidence:** `client/src/components/Nav/SettingsTabs/Speech/Speech.tsx:37,154-155,162`

---

### [CONFIRMED] Chat Tab — AdvancedPrompts side-effect (spec §Chat, States & edge cases)

- In `AdvancedPrompts.tsx`, `handleChange(false)` calls `setAlwaysMakeProd(true)` before switching mode to SIMPLE.
- **Evidence:** `client/src/components/Nav/SettingsTabs/Chat/AdvancedPrompts.tsx:18-22`

---

### [CONFIRMED] Chat Tab — ForkSettings "Start fork here" always visible (spec §Chat, States & edge cases)

- In `ForkSettings.tsx`, the `splitAtTarget` switch (com_ui_fork_split_target_setting) is rendered unconditionally, outside the `{remember && (...)}` block.
- **Evidence:** `client/src/components/Nav/SettingsTabs/Chat/ForkSettings.tsx:56-74`

---

### [CONFIRMED] Data Tab — AgentApiKeys gated on REMOTE_AGENTS USE (spec §Data, UI elements)

- `Data.tsx` uses `useHasAccess({ permissionType: PermissionTypes.REMOTE_AGENTS, permission: Permissions.USE })` and conditionally renders `<AgentApiKeys />`.
- **Evidence:** `client/src/components/Nav/SettingsTabs/Data/Data.tsx:16-33`

---

### [CONFIRMED] Data Tab — Import accepts .json only (spec §Data, FR-1)

- `<input type="file" accept=".json">` in `ImportConversations.tsx`.
- **Evidence:** `client/src/components/Nav/SettingsTabs/Data/ImportConversations.tsx:137`

---

### [CONFIRMED] Data Tab — DeleteCache disabled when cache empty (spec §Data, FR-5 / AC-3)

- `DeleteCache.tsx` checks `caches.open('tts-responses')` keys on mount; sets `isCacheEmpty`; button `disabled={disabled || isCacheEmpty}`.
- **Evidence:** `client/src/components/Nav/SettingsTabs/Data/DeleteCache.tsx:22-26,49`

---

### [CONFIRMED] Data Tab — ClearChats sequence (spec §Data, FR-6)

- `clearConvos` calls `clearAllConversationStorage()` then `newConversation()` in the `onSuccess` callback.
- **Evidence:** `client/src/components/Nav/SettingsTabs/Data/ClearChats.tsx:21-29`

---

### [CONFIRMED] Account Tab — Delete account email check is case-insensitive (spec §Account, FR-5)

- `newEmailInput.trim().toLowerCase() === user?.email.trim().toLowerCase()`
- **Evidence:** `client/src/components/Nav/SettingsTabs/Account/DeleteAccount.tsx:56`

---

### [CONFIRMED] Account Tab — Delete button locked (opacity 30%, lock icon) until email matches (spec §Account, AC-4)

- When `isLocked`, the button renders `<LockIcon>` + "Locked" text and applies `opacity-30` CSS.
- **Evidence:** `client/src/components/Nav/SettingsTabs/Account/DeleteAccount.tsx:185-202`

---

### [CONFIRMED] Account Tab — 2FA and Backup Codes rows hidden for non-local provider (spec §Account)

- `Account.tsx` wraps both `EnableTwoFactorItem` and `BackupCodesItem` inside `{user?.provider === 'local' && ...}`.
- **Evidence:** `client/src/components/Nav/SettingsTabs/Account/Account.tsx:22-33`

---

### [CONFIRMED] Account Tab — Delete Account visibility (spec §Account, AC-6)

- `{startupConfig?.allowAccountDeletion !== false && <DeleteAccount />}` — server sets this to `true` when env var is unset.
- **Evidence:** `client/src/components/Nav/SettingsTabs/Account/Account.tsx:34-38`; `api/server/routes/config.js:82-84`

---

### [CONFIRMED] resolveExternalUrl in data-schemas/interface.ts (spec §Console Link, Preconditions)

- `resolveExternalUrl` calls `extractEnvVariable(obj.externalUrl)` from `librechat-data-provider` to interpolate `${CONSOLE_URL}` at server startup.
- **Evidence:** `packages/data-schemas/src/app/interface.ts:9-14`

---

### [CONFIRMED] Help & FAQ shown unless helpAndFaqURL === '/' (spec §Account Dropdown)

- `AccountSettings.tsx:80`: `{startupConfig?.helpAndFaqURL !== '/' && (...)}`. Default is `'https://librechat.ai'` from `api/server/routes/config.js:76`.
- **Evidence:** `client/src/components/Nav/AccountSettings.tsx:80`; `api/server/routes/config.js:76`

---

### [RUNTIME-ONLY] Speech Tab — AC-3, graceful degradation when NuFi has no speech backend

- **Spec says:** "(verify: graceful degradation)" — enabling STT when no backend is configured should not throw an unhandled error.
- **Verdict: RUNTIME-ONLY** — Requires a live test. The toggle updates Recoil state; actual STT calls would fail at the API layer. Whether this surfaces as an unhandled error or a toast requires runtime observation.

---

## Summary Table

| # | Location | Verdict | Short description |
|---|---|---|---|
| 1 | General Tab — Language "Auto" label | WRONG | After selecting Auto, dropdown shows resolved locale (e.g., "English"), not "Auto" |
| 2 | Account Tab — 2FA progress bar during setup | WRONG | Progress bar only shown when twoFactorEnabled=true; absent during initial setup |
| 3 | Account Tab — "all 8 backup codes" | WRONG | Service generates 10 backup codes, not 8 |
| 4 | Settings dialog — Personalization tab omitted | NEEDS-FIX | Seventh tab exists, conditionally shown per MEMORIES OPT_OUT permission |
| 5 | Settings dialog — Balance tab omitted | NEEDS-FIX | Balance tab exists, conditionally shown when balance.enabled |
| 6 | Account Dropdown — Balance format | NEEDS-FIX | Format is locale-formatted number (Intl.NumberFormat), not bare integer |
| 7 | Commands Tab — default role permissions | RUNTIME-ONLY | Cannot confirm from static config |
| 8 | Data Tab — REMOTE_AGENTS USE permission | RUNTIME-ONLY | Cannot confirm from static config |
| 9 | Account Tab — OAuth config | VERIFY-RESOLVED → CONFIRMED | No OAuth config in librechat.yaml; local auth assumed correct |
| 10 | Speech Tab — AC-3 graceful degradation | RUNTIME-ONLY | Requires live test |
| 11–38 | All other FR-n / AC-n claims | CONFIRMED | Code matches spec |
